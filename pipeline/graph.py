"""Orchestrator (PLAN items 4 and 9).

Dispatch: the Orchestrator LLM proposes a DispatchPlan; a deterministic
floor validator (pipeline/dispatch.py::enforce_floor) guarantees Mandate
and KYA always run, and Log/Drift run whenever there's enough transaction
history for each to say anything (different minimums per agent — see
pipeline/dispatch.py's module docstring). The LLM can propose running
*more* than the floor requires, never less.

Escalation: after the dispatched specialists run, if any produced an
unresolved Observation, the graph loops back — capped at exactly one extra
round — and re-dispatches only the agent(s) each observation actually
targets (pipeline/escalation.py). A re-dispatched agent on the escalation
round only contributes to `observations`, never `findings`: its rule-
backed verdicts were already decided in round 0, so nothing calls
`.run()` again or re-emits those findings a second time.

Every specialist node calls `.review()`, not `.run()` — the orchestrator's
default path needs a live ANTHROPIC_API_KEY, since dispatch and escalation
are both fundamentally about deciding which LLM-capable analysis to
invoke. Every node is `async` and every agent call is `await`ed — this is
what lets LangGraph's `.astream_events()` (and CopilotKit's AG-UI adapter
on top of it) capture thinking/reasoning content as it streams from
`langchain_anthropic.ChatAnthropic`; that capture only fires on the async
callback path, not sync `.invoke()` (agents/llm.py's module docstring).
`build_graph(model=...)` accepts an injectable model (threaded into every
node as a closure) specifically so tests can run the entire graph against
a fake — see tests/test_pipeline.py — without either a live key or,
worse, silently making real paid API calls on every `pytest` run.
"""
from __future__ import annotations

from datetime import datetime, timezone

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt
from pydantic import ValidationError

from agents.drafting import draft_case_report
from agents.drift import DriftAgent
from agents.grounding import check_grounding
from agents.kya import KYAAgent
from agents.log import LogAgent
from agents.mandate import MandateAgent
from ingestion.normalize import normalize_case
from pipeline.dispatch import enforce_floor, propose_dispatch_plan
from pipeline.escalation import escalation_targets, observations_for
from pipeline.scoring import score_findings
from pipeline.state import SupervisionState
from registry.loader import (
    load_drift_ruleset,
    load_kya_ruleset,
    load_log_ruleset,
    load_mandate_ruleset,
    load_scoring_config,
)
from schemas import ReviewerDecision

_SPECIALIST_NODES = ("mandate", "kya", "log", "drift")
_MAX_ESCALATION_ROUNDS = 1
# Grounding-retry cap per CLAUDE.md's orchestration table ("grounding-retry
# (capped at 2) on the drafting agent"): 1 initial draft + at most 2
# regenerations, then the report is blocked rather than shipped ungrounded.
_MAX_GROUNDING_RETRIES = 2
# The human-directed re-analysis loop (PLAN item 13) is bounded by the
# human — every iteration costs an explicit reviewer decision, so it cannot
# run away on its own. This cap is belt-and-braces on top of that, not the
# real control.
_MAX_REVIEWER_ROUNDS = 3


def build_graph(*, model=None, checkpointer=None) -> CompiledStateGraph:
    mandate_agent = MandateAgent()
    kya_agent = KYAAgent()
    log_agent = LogAgent()
    drift_agent = DriftAgent()

    async def _ingest_node(state: SupervisionState) -> dict:
        ingested = normalize_case(state["case_path"])
        return {"case": ingested, "ingestion_findings": ingested.findings}

    async def _dispatch_node(state: SupervisionState) -> dict:
        plan = await propose_dispatch_plan(state["case"], model=model)
        plan = enforce_floor(plan, state["case"])
        return {"dispatch_plan": plan, "escalation_round": 0}

    def _route_from_dispatch(state: SupervisionState) -> list[str]:
        plan = state["dispatch_plan"]
        targets = []
        if plan.run_mandate:
            targets.append("mandate")
        if plan.run_kya:
            targets.append("kya")
        if plan.run_log:
            targets.append("log")
        if plan.run_drift:
            targets.append("drift")
        return targets or ["escalate_check"]  # floor guarantees this never happens in practice

    def _directive_for(state: SupervisionState, agent_name: str) -> str | None:
        """The reviewer's instruction text, iff this agent is one of the
        directive's targets. A directed pass (PLAN item 13) takes precedence
        over escalation semantics: the human asked a specific question, and
        the answer may legitimately include *new findings* — safe because
        pipeline/state.py's dedup reducer drops re-emitted identical ids,
        while a genuinely changed judgment arrives under a new id."""
        directive = state.get("reviewer_directive")
        if directive is not None and agent_name in directive.target_agents:
            return directive.instructions
        return None

    async def _mandate_node(state: SupervisionState) -> dict:
        # Mandate's LLM subcheck produces real Findings, never Observations
        # (agents/mandate_reasoning.py) — nothing to resolve on an
        # escalation round, so it's never a *machine* re-dispatch target
        # (pipeline/escalation.py). A human reviewer can still send it back
        # with a directive (item 13), which is the only way this node runs
        # more than once.
        findings = await mandate_agent.review(
            state["case"], load_mandate_ruleset(), model=model,
            reviewer_directive=_directive_for(state, "mandate"),
        )
        return {"findings": findings}

    async def _kya_node(state: SupervisionState) -> dict:
        directive = _directive_for(state, "kya")
        if directive is not None:
            review = await kya_agent.review(state["case"], load_kya_ruleset(), model=model, reviewer_directive=directive)
            return {"findings": review.findings, "observations": review.observations}
        escalating = state.get("escalation_round", 0) > 0
        prior = observations_for("kya", state.get("observations", [])) if escalating else None
        review = await kya_agent.review(state["case"], load_kya_ruleset(), model=model, prior_observations=prior)
        if escalating:
            return {"observations": review.observations}
        return {"findings": review.findings, "observations": review.observations}

    async def _log_node(state: SupervisionState) -> dict:
        directive = _directive_for(state, "log")
        if directive is not None:
            review = await log_agent.review(state["case"], load_log_ruleset(), model=model, reviewer_directive=directive)
            return {"findings": review.findings, "observations": review.observations}
        escalating = state.get("escalation_round", 0) > 0
        prior = observations_for("log", state.get("observations", [])) if escalating else None
        review = await log_agent.review(state["case"], load_log_ruleset(), model=model, prior_observations=prior)
        if escalating:
            return {"observations": review.observations}
        return {"findings": review.findings, "observations": review.observations}

    async def _drift_node(state: SupervisionState) -> dict:
        directive = _directive_for(state, "drift")
        if directive is not None:
            review = await drift_agent.review(state["case"], load_drift_ruleset(), model=model, reviewer_directive=directive)
            return {"findings": review.findings, "observations": review.observations}
        escalating = state.get("escalation_round", 0) > 0
        prior = observations_for("drift", state.get("observations", [])) if escalating else None
        review = await drift_agent.review(state["case"], load_drift_ruleset(), model=model, prior_observations=prior)
        if escalating:
            return {"observations": review.observations}
        return {"findings": review.findings, "observations": review.observations}

    async def _escalate_check_node(state: SupervisionState) -> dict:
        return {}  # pure join point; routing decided by _route_after_specialists

    def _route_after_specialists(state: SupervisionState) -> str:
        """Decides only whether to escalate at all — NOT which specialists
        to re-dispatch (that's _route_escalation_targets, on bump_round's
        own outgoing edge). Returning specialist names directly from here
        was a real bug caught by the test suite: this edge's declared
        targets are only {"bump_round", "draft_report"}, so returning e.g.
        "kya" raised a KeyError at graph-execution time, not at build time.
        Since PLAN items 11/12, the settled exit is the scoring + drafting
        tail, not END."""
        if state.get("escalation_round", 0) >= _MAX_ESCALATION_ROUNDS:
            return "risk_score"
        return "bump_round" if escalation_targets(state.get("observations", [])) else "risk_score"

    async def _bump_round_node(state: SupervisionState) -> dict:
        return {"escalation_round": state.get("escalation_round", 0) + 1}

    def _route_escalation_targets(state: SupervisionState) -> list[str] | str:
        targets = escalation_targets(state.get("observations", []))
        return targets if targets else "risk_score"

    async def _risk_score_node(state: SupervisionState) -> dict:
        """Pure arithmetic (pipeline/scoring.py) — recomputed on every pass
        through the tail, since a reviewer-directed re-analysis may have
        changed the findings. Also the point where a consumed reviewer
        directive is cleared: it steered exactly one specialist pass, and
        every path from the specialists to the drafting tail runs through
        here."""
        score = score_findings(
            state["case"].case.case_id, state.get("findings", []), load_scoring_config()
        )
        return {"risk_score": score, "reviewer_directive": None}

    async def _draft_node(state: SupervisionState) -> dict:
        report = await draft_case_report(
            case_id=state["case"].case.case_id,
            firm_name=state["case"].case.firm.name,
            findings=state.get("findings", []),
            observations=state.get("observations", []),
            dispatch_plan=state.get("dispatch_plan"),
            escalation_round=state.get("escalation_round", 0),
            risk_score=state.get("risk_score"),
            # On a retry, the validator's exact complaints ride along so the
            # model fixes the actual problems instead of re-rolling blind.
            prior_problems=state.get("grounding_problems") or None,
            model=model,
        )
        return {"draft_report": report, "draft_attempts": state.get("draft_attempts", 0) + 1}

    async def _grounding_node(state: SupervisionState) -> dict:
        problems = check_grounding(
            state["draft_report"], state.get("findings", []), state.get("observations", [])
        )
        if not problems:
            return {"grounding_problems": [], "report_blocked": False}
        out_of_retries = state.get("draft_attempts", 0) > _MAX_GROUNDING_RETRIES
        return {"grounding_problems": problems, "report_blocked": out_of_retries}

    def _route_after_grounding(state: SupervisionState) -> str:
        if not state.get("grounding_problems"):
            return "human_gate"  # grounded — a named human decides what happens next
        if state.get("report_blocked"):
            return END  # out of retries — blocked, nothing approvable to gate
        return "draft_report"

    async def _human_gate_node(state: SupervisionState) -> dict:
        """PLAN item 13 — the graph pauses here (LangGraph `interrupt()`;
        the checkpointer holds the frozen run) and structurally cannot
        proceed without a resume payload carrying a reviewer's decision.
        Invalid payloads and cap-violating rerun requests re-interrupt with
        an error field rather than crashing the run: the gate holds until a
        *valid* named decision arrives."""
        rounds = state.get("reviewer_rounds", 0)
        rerun_allowed = rounds < _MAX_REVIEWER_ROUNDS
        context = {
            "reason": "report_approval",
            "message": "Grounded report awaiting a named reviewer's decision.",
            "case_id": state["case"].case.case_id,
            "rerun_allowed": rerun_allowed,
            "reviewer_rounds": rounds,
            "max_reviewer_rounds": _MAX_REVIEWER_ROUNDS,
        }

        error: str | None = None
        while True:
            payload = interrupt({**context, **({"error": error} if error else {})})
            if not isinstance(payload, dict):
                error = "Decision payload must be an object with action and reviewer."
                continue
            try:
                # decided_at is stamped server-side, never trusted from the client.
                decision = ReviewerDecision.model_validate(
                    {**payload, "decided_at": datetime.now(timezone.utc).isoformat()}
                )
            except ValidationError as exc:
                first = exc.errors()[0]
                error = f"Invalid decision ({'.'.join(str(p) for p in first['loc'])}): {first['msg']}"
                continue
            if decision.action == "rerun":
                if not rerun_allowed:
                    error = "Re-analysis cap reached for this case — approve or reject."
                    continue
                if decision.directive is None:
                    error = "A re-analysis decision requires instructions and target agents."
                    continue
            break

        updates: dict = {"reviewer_decisions": [decision]}
        if decision.action == "approve":
            updates["report_status"] = "issued"
        elif decision.action == "reject":
            updates["report_status"] = "rejected"
        else:
            updates["report_status"] = "draft"
            updates["reviewer_directive"] = decision.directive
            updates["reviewer_rounds"] = rounds + 1
        return updates

    def _route_after_gate(state: SupervisionState) -> list[str] | str:
        last = (state.get("reviewer_decisions") or [])[-1]
        if last.action == "rerun" and last.directive is not None:
            return list(last.directive.target_agents)
        return END

    graph = StateGraph(SupervisionState)
    graph.add_node("ingest", _ingest_node)
    graph.add_node("dispatch", _dispatch_node)
    graph.add_node("mandate", _mandate_node)
    graph.add_node("kya", _kya_node)
    graph.add_node("log", _log_node)
    graph.add_node("drift", _drift_node)
    graph.add_node("escalate_check", _escalate_check_node)
    graph.add_node("bump_round", _bump_round_node)
    graph.add_node("risk_score", _risk_score_node)
    graph.add_node("draft_report", _draft_node)
    graph.add_node("grounding_check", _grounding_node)
    graph.add_node("human_gate", _human_gate_node)

    graph.add_edge(START, "ingest")
    graph.add_edge("ingest", "dispatch")
    graph.add_conditional_edges("dispatch", _route_from_dispatch, [*_SPECIALIST_NODES, "escalate_check"])

    for node in _SPECIALIST_NODES:
        graph.add_edge(node, "escalate_check")

    graph.add_conditional_edges("escalate_check", _route_after_specialists, ["bump_round", "risk_score"])
    graph.add_conditional_edges("bump_round", _route_escalation_targets, [*_SPECIALIST_NODES, "risk_score"])
    graph.add_edge("risk_score", "draft_report")
    graph.add_edge("draft_report", "grounding_check")
    graph.add_conditional_edges("grounding_check", _route_after_grounding, ["draft_report", "human_gate", END])
    # The reviewer's re-analysis directive fans back out to exactly the
    # specialists it names; approve/reject end the run.
    graph.add_conditional_edges("human_gate", _route_after_gate, [*_SPECIALIST_NODES, END])

    return graph.compile(checkpointer=checkpointer)


async def run_case(case_path: str, *, model=None, thread_id: str = "run") -> SupervisionState:
    """One full pass up to the human gate. Since PLAN item 13 the graph
    *always* pauses at `human_gate` on the grounded path (an `interrupt()`
    needs a checkpointer, hence the per-call MemorySaver + thread config) —
    the returned state carries `__interrupt__` alongside the full record.
    Resuming with a decision is the caller's job (the API/UI in production,
    `Command(resume=...)` against a shared graph instance in tests)."""
    graph = build_graph(model=model, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": thread_id}}
    return await graph.ainvoke(
        {"case_path": case_path, "findings": [], "observations": [], "messages": []}, config
    )
