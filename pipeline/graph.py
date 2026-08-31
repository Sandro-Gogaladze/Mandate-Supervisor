"""The bounded runs (architecture-v2 §14): triage and drafting.

Each graph starts, does one job, appends what it produced to the ledger, and
exits. None is held open — the case lives in the ledger, not in a paused
process. The one interrupt() left is the human gate at the end of the
DRAFTING run: it guards the artifact (a report cannot issue without a named
decision — minutes, which is what a checkpointer is for), never the case
(open for a week — a ledger state).

TRIAGE — build_triage_graph():

    ingest → dispatch → {mandate, kya, log, drift} → escalate_check
           ⇄ bump_round → critic → synthesizer → risk_score → END

  The existing detection pipeline, minus the drafting tail, plus: every
  node appends its output to the ledger as it is produced; every specialist
  dispatch records the exact composed context it received
  (dispatch_recorded — the event this architecture exists to make
  possible); the deterministic critic and the additive synthesizer run
  before scoring. A directed re-analysis is a triage run with a
  reviewer_directive in its initial state — it enters at exactly the named
  specialists (the floor applies to pass 1 only; coverage was guaranteed
  when the case first arrived).

DRAFTING — build_drafting_graph():

    load_record → draft_report ⇄ grounding_check → human_gate (interrupt) → END

  Only reachable by explicit request — a clean case never drafts, it gets
  "close, no action" (a named decision, not a document). The score is
  recomputed from the ledger's current findings first, so the report states
  the tier as of when it was written. Grounding retry cap, report_blocked
  path, and the gate's self-defending loop are unchanged from the old
  single graph. A `rerun` decision records the directive and ENDS the run;
  the caller then starts a directed triage — the fan-back no longer lives
  inside one long-running graph.

Every guarantee here is code, not prompt: the skill floor
(agents/skills.py), the evidence floor (agents/context.py), observations
never scoring (pipeline/scoring.py's signature), grounding
(agents/grounding.py), the critic (agents/critic.py), correlation id
resolution (agents/synthesizer.py), and the gate (graph topology).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt
from pydantic import ValidationError

from agents.context import (
    ContextCompositionError,
    canonical_context,
    compose_context,
    context_digest,
)
from agents.critic import check_evidence_grounding
from agents.drafting import draft_case_report
from agents.drift import DriftAgent
from agents.grounding import check_grounding
from agents.kya import KYAAgent
from agents.llm import format_escalation_addendum
from agents.log import LogAgent
from agents.mandate import MandateAgent
from agents.prompts import assemble_run_prompts, effective_text
from agents.skills import SPECIALIST_SKILLS_BY_AGENT, enforce_skill_floor
from agents.synthesizer import synthesize
from ingestion.normalize import normalize_case_payload
from ledger import LedgerStore, get_default_store
from ledger.projection import project_case
from ledger.seed import latest_submission
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
from schemas import DispatchPlan, DispatchRecord, ReviewerDecision, ReviewerDirective

_SPECIALIST_NODES = ("mandate", "kya", "log", "drift")
_MAX_ESCALATION_ROUNDS = 1
# 1 initial draft + at most 2 regenerations, then blocked (CLAUDE.md).
_MAX_GROUNDING_RETRIES = 2
# The human-directed loop is bounded by the human — every iteration costs an
# explicit named decision. This cap is belt-and-braces, not the real control.
_MAX_REVIEWER_ROUNDS = 3


def _new_run_id(kind: str) -> str:
    return f"{kind[:3]}-{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Triage
# ---------------------------------------------------------------------------


def build_triage_graph(*, model=None, store: LedgerStore | None = None) -> CompiledStateGraph:
    store = store or get_default_store()
    mandate_agent = MandateAgent()
    kya_agent = KYAAgent()
    log_agent = LogAgent()
    drift_agent = DriftAgent()

    async def _ingest_node(state: SupervisionState) -> dict:
        case_id = state["case_id"]
        raw = latest_submission(store, case_id)
        ingested = normalize_case_payload(raw)

        directive = state.get("reviewer_directive")
        run_id = _new_run_id("triage")
        prompts = assemble_run_prompts("triage", state.get("prompt_overrides"))
        store.append(
            case_id=case_id, event_type="run_started", run_id=run_id,
            payload={
                "run_id": run_id, "kind": "triage", "prompts": prompts,
                **({"directive": directive.model_dump()} if directive else {}),
            },
            actor="system:triage",
        )
        return {
            "case": ingested,
            "ingestion_findings": ingested.findings,
            "run_id": run_id,
            "prompts": prompts,
            "pass_number": 2 if directive else 1,
        }

    async def _dispatch_node(state: SupervisionState) -> dict:
        case = state["case"]
        directive = state.get("reviewer_directive")

        if directive is not None:
            # A directed pass: the human named the specialists; no LLM
            # proposal, and the floor does not re-apply (pass 2).
            selected = [SPECIALIST_SKILLS_BY_AGENT[a] for a in directive.target_agents]
            selected = enforce_skill_floor(selected, case, pass_number=2)
            plan = DispatchPlan(
                run_mandate="mandate" in directive.target_agents,
                run_kya="kya" in directive.target_agents,
                run_log="log" in directive.target_agents,
                run_drift="drift" in directive.target_agents,
                reasoning=f"Directed re-analysis by a named reviewer: {directive.instructions}",
            )
        else:
            plan = await propose_dispatch_plan(
                case, model=model,
                system_prompt=effective_text(state["prompts"], "ORCH-DISPATCH"),
            )
            proposed = [
                skill for flag, skill in [
                    (plan.run_mandate, "mandate.review"), (plan.run_kya, "kya.review"),
                    (plan.run_log, "log.analyze"), (plan.run_drift, "drift.analyze"),
                ] if flag
            ]
            selected = enforce_skill_floor(proposed, case, pass_number=1)
            plan = enforce_floor(plan, case)  # the mirrored view the UI shows

        store.append(
            case_id=case.case.case_id, event_type="dispatch_planned", run_id=state["run_id"],
            payload={"plan": plan.model_dump(), "selected_skills": selected},
            actor="agent:orchestrator",
        )
        return {"dispatch_plan": plan, "selected_skills": selected, "escalation_round": 0}

    def _route_from_dispatch(state: SupervisionState) -> list[str]:
        agents = [
            agent for agent, skill in SPECIALIST_SKILLS_BY_AGENT.items()
            if skill in state.get("selected_skills", [])
        ]
        ordered = [a for a in _SPECIALIST_NODES if a in agents]
        return ordered or ["escalate_check"]  # floor guarantees non-empty on pass 1

    def _directive_for(state: SupervisionState, agent_name: str) -> str | None:
        directive = state.get("reviewer_directive")
        if directive is not None and agent_name in directive.target_agents:
            return directive.instructions
        return None

    def _record_dispatch(state: SupervisionState, agent_name: str, composed: dict, instruction: str) -> None:
        record = DispatchRecord(
            case_id=state["case"].case.case_id,
            run_id=state["run_id"],
            target=agent_name,
            skill=SPECIALIST_SKILLS_BY_AGENT[agent_name],
            instruction=instruction,
            context_blocks=composed,
            context_digest=context_digest(composed),
        )
        # Recorded BEFORE the model call (§9.4) — the audit trail shows the
        # briefing even if the subagent then dies mid-flight.
        store.append(
            case_id=record.case_id, event_type="dispatch_recorded", run_id=state["run_id"],
            payload=record.model_dump(), actor="agent:orchestrator",
        )

    def _record_outputs(state: SupervisionState, agent_name: str, findings, observations) -> None:
        for finding in findings:
            store.append(
                case_id=finding.case_id, event_type="finding_recorded", run_id=state["run_id"],
                payload=finding.model_dump(), actor=f"agent:{agent_name}",
            )
        for observation in observations:
            store.append(
                case_id=observation.case_id, event_type="observation_recorded", run_id=state["run_id"],
                payload=observation.model_dump(), actor=f"agent:{agent_name}",
            )

    async def _mandate_node(state: SupervisionState) -> dict:
        case = state["case"]
        directive = _directive_for(state, "mandate")
        ruleset = load_mandate_ruleset()
        composed = compose_context(canonical_context("mandate.review", case))
        _record_dispatch(state, "mandate", composed, directive or "")
        findings = await mandate_agent.review(
            case, ruleset, model=model, reviewer_directive=directive,
            prompts=state.get("prompts"), context=composed,
        )
        _record_outputs(state, "mandate", findings, [])
        return {"findings": findings, "dispatch_contexts": {"mandate": composed}}

    async def _kya_node(state: SupervisionState) -> dict:
        case = state["case"]
        directive = _directive_for(state, "kya")
        escalating = state.get("escalation_round", 0) > 0 and directive is None
        prior = observations_for("kya", state.get("observations", [])) if escalating else None
        ruleset = load_kya_ruleset()

        floor = kya_agent.run(case, ruleset)  # deterministic, cheap; review() recomputes identically
        composed = compose_context(canonical_context("kya.review", case, floor_findings=floor))
        instruction = directive or (format_escalation_addendum(prior) if prior else "")
        _record_dispatch(state, "kya", composed, instruction)

        review = await kya_agent.review(
            case, ruleset, model=model, prior_observations=prior,
            reviewer_directive=directive, prompts=state.get("prompts"), context=composed,
        )
        if escalating:
            # Rule-backed verdicts were decided in round 0 — an escalation
            # round only narrows/resolves the observation list.
            _record_outputs(state, "kya", [], review.observations)
            return {"observations": review.observations, "dispatch_contexts": {"kya": composed}}
        _record_outputs(state, "kya", review.findings, review.observations)
        return {
            "findings": review.findings, "observations": review.observations,
            "dispatch_contexts": {"kya": composed},
        }

    async def _log_node(state: SupervisionState) -> dict:
        case = state["case"]
        directive = _directive_for(state, "log")
        escalating = state.get("escalation_round", 0) > 0 and directive is None
        prior = observations_for("log", state.get("observations", [])) if escalating else None
        ruleset = load_log_ruleset()

        try:
            composed = compose_context(canonical_context("log.analyze", case, ruleset=ruleset))
        except ContextCompositionError:
            # No active Log rules — review() returns empty; nothing dispatched.
            review = await log_agent.review(case, ruleset, model=model)
            return {"findings": review.findings, "observations": review.observations}

        instruction = directive or (format_escalation_addendum(prior) if prior else "")
        _record_dispatch(state, "log", composed, instruction)
        review = await log_agent.review(
            case, ruleset, model=model, prior_observations=prior,
            reviewer_directive=directive, prompts=state.get("prompts"), context=composed,
        )
        if escalating:
            _record_outputs(state, "log", [], review.observations)
            return {"observations": review.observations, "dispatch_contexts": {"log": composed}}
        _record_outputs(state, "log", review.findings, review.observations)
        return {
            "findings": review.findings, "observations": review.observations,
            "dispatch_contexts": {"log": composed},
        }

    async def _drift_node(state: SupervisionState) -> dict:
        case = state["case"]
        directive = _directive_for(state, "drift")
        escalating = state.get("escalation_round", 0) > 0 and directive is None
        prior = observations_for("drift", state.get("observations", [])) if escalating else None
        ruleset = load_drift_ruleset()

        tx_count = len(case.case.transaction_history)
        try:
            rule = next(
                r for r in ruleset.rules
                if r.type == "behavioral_drift_detected" and r.status == "active"
            )
            from schemas import typed_params

            insufficient = tx_count < typed_params(rule).min_total_transactions
        except StopIteration:
            insufficient = True

        if insufficient:
            # Dispatched but declined on data availability — auditable as
            # such, without computing statistics over too little history.
            composed = {"insufficient_baseline_gate": True, "transaction_count": tx_count}
            _record_dispatch(state, "drift", composed, directive or "")
            review = await drift_agent.review(case, ruleset, model=model)
            return {"findings": review.findings, "observations": review.observations,
                    "dispatch_contexts": {"drift": composed}}

        composed = compose_context(canonical_context("drift.analyze", case, ruleset=ruleset))
        instruction = directive or (format_escalation_addendum(prior) if prior else "")
        _record_dispatch(state, "drift", composed, instruction)
        review = await drift_agent.review(
            case, ruleset, model=model, prior_observations=prior,
            reviewer_directive=directive, prompts=state.get("prompts"), context=composed,
        )
        if escalating:
            _record_outputs(state, "drift", [], review.observations)
            return {"observations": review.observations, "dispatch_contexts": {"drift": composed}}
        _record_outputs(state, "drift", review.findings, review.observations)
        return {
            "findings": review.findings, "observations": review.observations,
            "dispatch_contexts": {"drift": composed},
        }

    async def _escalate_check_node(state: SupervisionState) -> dict:
        return {}  # pure join point

    def _route_after_specialists(state: SupervisionState) -> str:
        if state.get("escalation_round", 0) >= _MAX_ESCALATION_ROUNDS:
            return "critic"
        return "bump_round" if escalation_targets(state.get("observations", [])) else "critic"

    async def _bump_round_node(state: SupervisionState) -> dict:
        next_round = state.get("escalation_round", 0) + 1
        store.append(
            case_id=state["case"].case.case_id, event_type="escalation_round_started",
            run_id=state["run_id"],
            payload={"round": next_round, "targets": escalation_targets(state.get("observations", []))},
            actor="system:triage",
        )
        return {"escalation_round": next_round}

    def _route_escalation_targets(state: SupervisionState) -> list[str] | str:
        targets = escalation_targets(state.get("observations", []))
        return targets if targets else "critic"

    async def _critic_node(state: SupervisionState) -> dict:
        results = check_evidence_grounding(
            state.get("findings", []), state.get("observations", []),
            state.get("dispatch_contexts", {}),
        )
        for result in results:
            store.append(
                case_id=state["case"].case.case_id, event_type="critic_checked",
                run_id=state["run_id"], payload=result.model_dump(), actor="system:critic",
            )
        return {"critic_results": [r.model_dump() for r in results]}

    async def _synthesizer_node(state: SupervisionState) -> dict:
        findings = state.get("findings", [])
        correlations = await synthesize(
            state["case"].case.case_id, findings, model=model,
            system_prompt=effective_text(state["prompts"], "SYNTHESIZER") if state.get("prompts") else None,
        ) if len(findings) >= 2 else []
        for correlation in correlations:
            store.append(
                case_id=correlation.case_id, event_type="correlation_recorded",
                run_id=state["run_id"], payload=correlation.model_dump(), actor="agent:synthesizer",
            )
        return {"correlations": correlations}

    async def _risk_score_node(state: SupervisionState) -> dict:
        case_id = state["case"].case.case_id
        score = score_findings(case_id, state.get("findings", []), load_scoring_config())
        store.append(
            case_id=case_id, event_type="score_computed", run_id=state["run_id"],
            payload=score.model_dump(), actor="system:scoring",
        )
        store.append(
            case_id=case_id, event_type="run_completed", run_id=state["run_id"],
            payload={
                "run_id": state["run_id"], "kind": "triage",
                "finding_count": len(state.get("findings", [])),
                "observation_count": len(state.get("observations", [])),
            },
            actor="system:triage",
        )
        # The directive steered exactly one pass; consumed here.
        return {"risk_score": score, "reviewer_directive": None}

    graph = StateGraph(SupervisionState)
    graph.add_node("ingest", _ingest_node)
    graph.add_node("dispatch", _dispatch_node)
    graph.add_node("mandate", _mandate_node)
    graph.add_node("kya", _kya_node)
    graph.add_node("log", _log_node)
    graph.add_node("drift", _drift_node)
    graph.add_node("escalate_check", _escalate_check_node)
    graph.add_node("bump_round", _bump_round_node)
    graph.add_node("critic", _critic_node)
    graph.add_node("synthesizer", _synthesizer_node)
    graph.add_node("risk_score", _risk_score_node)

    graph.add_edge(START, "ingest")
    graph.add_edge("ingest", "dispatch")
    graph.add_conditional_edges("dispatch", _route_from_dispatch, [*_SPECIALIST_NODES, "escalate_check"])
    for node in _SPECIALIST_NODES:
        graph.add_edge(node, "escalate_check")
    graph.add_conditional_edges("escalate_check", _route_after_specialists, ["bump_round", "critic"])
    graph.add_conditional_edges("bump_round", _route_escalation_targets, [*_SPECIALIST_NODES, "critic"])
    graph.add_edge("critic", "synthesizer")
    graph.add_edge("synthesizer", "risk_score")
    graph.add_edge("risk_score", END)

    return graph.compile()


async def run_triage(
    case_id: str,
    *,
    model=None,
    store: LedgerStore | None = None,
    prompt_overrides: dict[str, str] | None = None,
    directive: ReviewerDirective | None = None,
):
    """One bounded triage pass. Starts, appends everything it produces to
    the ledger, exits. Returns the projected CaseRecord — the durable truth,
    not the transient graph state."""
    store = store or get_default_store()
    graph = build_triage_graph(model=model, store=store)
    initial: dict = {
        "case_id": case_id, "findings": [], "observations": [], "messages": [],
        **({"prompt_overrides": prompt_overrides} if prompt_overrides else {}),
        **({"reviewer_directive": directive} if directive else {}),
    }
    await graph.ainvoke(initial)
    return project_case(store.events_for(case_id))


# ---------------------------------------------------------------------------
# Drafting
# ---------------------------------------------------------------------------


def build_drafting_graph(*, model=None, store: LedgerStore | None = None, checkpointer=None) -> CompiledStateGraph:
    store = store or get_default_store()

    async def _load_record_node(state: SupervisionState) -> dict:
        case_id = state["case_id"]
        record = project_case(store.events_for(case_id))

        run_id = _new_run_id("drafting")
        prompts = assemble_run_prompts("drafting", state.get("prompt_overrides"))
        store.append(
            case_id=case_id, event_type="run_started", run_id=run_id,
            payload={"run_id": run_id, "kind": "drafting", "prompts": prompts},
            actor="system:drafting",
        )

        # The report states the tier as of when it was written — recompute
        # from the ledger's *current* findings, not the last triage's score.
        score = score_findings(case_id, record.findings, load_scoring_config())
        store.append(
            case_id=case_id, event_type="score_computed", run_id=run_id,
            payload=score.model_dump(), actor="system:scoring",
        )

        last_triage = next((r for r in reversed(record.runs) if r.kind == "triage"), None)
        return {
            "run_id": run_id,
            "prompts": prompts,
            "firm_name": record.firm,
            "findings": record.findings,
            "observations": record.observations,
            "risk_score": score,
            "dispatch_plan": last_triage.plan if last_triage else None,
            "escalation_round": record.escalation_rounds,
            "draft_attempts": 0,
            "grounding_problems": [],
            "reviewer_rounds": sum(1 for d in record.decisions if d.action == "rerun"),
        }

    async def _draft_node(state: SupervisionState) -> dict:
        report = await draft_case_report(
            case_id=state["case_id"],
            firm_name=state.get("firm_name", "unknown"),
            findings=state.get("findings", []),
            observations=state.get("observations", []),
            dispatch_plan=state.get("dispatch_plan"),
            escalation_round=state.get("escalation_round", 0),
            risk_score=state.get("risk_score"),
            prior_problems=state.get("grounding_problems") or None,
            model=model,
            system_prompt=effective_text(state["prompts"], "DRAFTING"),
        )
        store.append(
            case_id=state["case_id"], event_type="report_drafted", run_id=state["run_id"],
            payload=report.model_dump(), actor="agent:drafting",
        )
        return {"draft_report": report, "draft_attempts": state.get("draft_attempts", 0) + 1}

    async def _grounding_node(state: SupervisionState) -> dict:
        problems = check_grounding(
            state["draft_report"], state.get("findings", []), state.get("observations", [])
        )
        attempt = state.get("draft_attempts", 0)
        store.append(
            case_id=state["case_id"], event_type="grounding_checked", run_id=state["run_id"],
            payload={"passed": not problems, "problems": problems, "attempt": attempt},
            actor="system:grounding",
        )
        if not problems:
            return {"grounding_problems": [], "report_blocked": False}
        out_of_retries = attempt > _MAX_GROUNDING_RETRIES
        if out_of_retries:
            store.append(
                case_id=state["case_id"], event_type="report_blocked", run_id=state["run_id"],
                payload={"problems": problems}, actor="system:grounding",
            )
            store.append(
                case_id=state["case_id"], event_type="run_completed", run_id=state["run_id"],
                payload={"run_id": state["run_id"], "kind": "drafting",
                         "finding_count": len(state.get("findings", [])),
                         "observation_count": len(state.get("observations", []))},
                actor="system:drafting",
            )
        return {"grounding_problems": problems, "report_blocked": out_of_retries}

    def _route_after_grounding(state: SupervisionState) -> str:
        if not state.get("grounding_problems"):
            return "human_gate"
        if state.get("report_blocked"):
            return END  # blocked — nothing approvable to gate
        return "draft_report"

    async def _human_gate_node(state: SupervisionState) -> dict:
        """The graph pauses here (interrupt(); the checkpointer holds the
        frozen run) and structurally cannot issue anything without a resume
        payload carrying a named reviewer's decision. Invalid payloads and
        cap-violating rerun requests re-interrupt with an error field."""
        rounds = state.get("reviewer_rounds", 0)
        rerun_allowed = rounds < _MAX_REVIEWER_ROUNDS
        context = {
            "reason": "report_approval",
            "message": "Grounded report awaiting a named reviewer's decision.",
            "case_id": state["case_id"],
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
                # decided_at stamped server-side, never trusted from the client.
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

        store.append(
            case_id=state["case_id"], event_type="decision_recorded", run_id=state["run_id"],
            payload=decision.model_dump(), actor=f"human:{decision.reviewer}",
        )
        store.append(
            case_id=state["case_id"], event_type="run_completed", run_id=state["run_id"],
            payload={"run_id": state["run_id"], "kind": "drafting",
                     "finding_count": len(state.get("findings", [])),
                     "observation_count": len(state.get("observations", []))},
            actor="system:drafting",
        )

        updates: dict = {"reviewer_decisions": [decision]}
        if decision.action == "approve":
            updates["report_status"] = "issued"
        elif decision.action == "reject":
            updates["report_status"] = "rejected"
        else:
            # The drafting run ENDS here; the caller reads the recorded
            # directive and starts a directed triage run — the fan-back no
            # longer lives inside one long-held graph.
            updates["report_status"] = "draft"
            updates["reviewer_directive"] = decision.directive
            updates["reviewer_rounds"] = rounds + 1
        return updates

    graph = StateGraph(SupervisionState)
    graph.add_node("load_record", _load_record_node)
    graph.add_node("draft_report", _draft_node)
    graph.add_node("grounding_check", _grounding_node)
    graph.add_node("human_gate", _human_gate_node)

    graph.add_edge(START, "load_record")
    graph.add_edge("load_record", "draft_report")
    graph.add_edge("draft_report", "grounding_check")
    graph.add_conditional_edges("grounding_check", _route_after_grounding, ["draft_report", "human_gate", END])
    graph.add_edge("human_gate", END)

    return graph.compile(checkpointer=checkpointer)


async def start_drafting(
    case_id: str,
    *,
    model=None,
    store: LedgerStore | None = None,
    prompt_overrides: dict[str, str] | None = None,
    thread_id: str | None = None,
):
    """Runs the drafting graph up to the human gate (or to a blocked END).
    Returns (graph, config, state) — resume with resolve_gate(). The
    checkpointer is per-call and disposable: it holds one in-flight draft
    for minutes; the ledger holds the case forever."""
    store = store or get_default_store()
    graph = build_drafting_graph(model=model, store=store, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": thread_id or _new_run_id("thread")}}
    initial: dict = {
        "case_id": case_id, "messages": [],
        **({"prompt_overrides": prompt_overrides} if prompt_overrides else {}),
    }
    state = await graph.ainvoke(initial, config)
    return graph, config, state


async def resolve_gate(graph: CompiledStateGraph, config: dict, decision: dict):
    """Resume a held gate with a reviewer's decision dict. The gate node
    validates it server-side — a bad payload re-interrupts with an error."""
    return await graph.ainvoke(Command(resume=decision), config)
