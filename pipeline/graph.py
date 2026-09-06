"""The bounded runs: review and drafting.

Each graph starts, does one job, appends what it produced to the ledger, and
exits. None is held open — the case lives in the ledger, not in a paused
process. The one interrupt() left is the human gate at the end of the
DRAFTING run: it guards the artifact (a report cannot issue without a named
decision — minutes, which is what a checkpointer is for), never the case
(open for a week — a ledger state).

REVIEW — build_review_graph(): one officer request, answered.

    ingest → orchestrate → {the skills it dispatched…} → specialists_done
           → control_assurance → critic → synthesizer → record → END

  A first pass ("run the review") and a later question use the same graph.
  The first pass deterministically dispatches every governed review skill;
  later questions ask the orchestrator to dispatch skills with a briefing,
  reply from the record, or ask for the report. `ingest` reads the submission
  from the ledger by case id, rebuilds
  the dossier and runs intake (ingestion/normalize.py). Every specialist runs
  its deterministic floor over the dossier in scope (facts), assesses it
  (assessments), and makes its one contained model call; every fact,
  assessment and projected finding is appended to the ledger as it is
  produced, and every dispatch records the exact composed context the agent
  received. Control Assurance runs after whichever peers ran, then the
  deterministic critic, the additive synthesizer, the score and the
  authorisation recommendation. The run kind on the record is "triage" for
  a first pass or a directed re-analysis and "investigation" for a question.

DRAFTING — build_drafting_graph():

    load_record → draft_report ⇄ grounding_check → human_gate (interrupt) → END

  Only reachable by explicit request. The score is recomputed from the
  ledger's current findings first. A `rerun` decision records the directive
  and ENDS the run; the caller then starts a directed review.

Every guarantee here is code, not prompt: the evidence floor
(agents/context.py), observations never scoring (pipeline/scoring.py's
signature), grounding (agents/grounding.py), the critic (agents/critic.py),
correlation id resolution (agents/synthesizer.py), and the gate (graph
topology). First-pass coverage is a deterministic policy and its complete
dispatch plan is recorded.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt
from pydantic import ValidationError

from agents.assess import (
    current_findings,
    link_supersessions,
    project_failure_occurrences,
    project_findings,
)
from agents.base import SpecialistReview, scoped
from agents.context import (
    ContextCompositionError,
    canonical_context,
    compose_context,
    context_digest,
    resolve_blocks,
)
from agents.critic import check_evidence_grounding
from agents.drafting import draft_case_report
from agents.grounding import check_grounding
from agents.investigator import investigate
from agents.orchestrator import (FIRST_PASS_REQUEST, Dispatch, OrchestratorDecision, close_out,
                                 first_pass_decision, route)
from agents.prompts import assemble_run_prompts, effective_text
from agents.skills import REVIEW_SKILLS, SKILLS, SPECIALIST_SKILLS_BY_AGENT
from agents.synthesizer import synthesize
from ingestion.normalize import dossier_from_submission, normalize_dossier
from ledger import LedgerStore, get_default_store
from ledger.projection import project_case
from ledger.seed import latest_submission
from pipeline.scoring import score_findings
from pipeline.state import SupervisionState
from registry.loader import load_failure_catalogue, load_scoring_config
from schemas import (
    Assessment,
    Ruleset,
    DispatchPlan,
    DispatchRecord,
    Observation,
    ReviewerDecision,
    ReviewerDirective,
)

from agents.catalog import AGENTS, PEERS, RULESET_LOADERS
from registry.loader import load_all_rulesets
_SPECIALIST_NODES = (*PEERS, "systemic")
_RULESET_LOADERS = RULESET_LOADERS
# One specialist's model call. Injection now judges every run and Consent
# every selection; on a fifty-run dossier that is minutes, not seconds, and
# a cap that fires turns the whole judgement into "unavailable". Generous on
# purpose — the fallback exists for a hung call, not a long one.
_SPECIALIST_TIMEOUT_S = 900
# How many specialists may hold a model call open at once — one per peer, so
# the fan-out the graph describes is the fan-out that actually happens.
#
# This was 3, on the theory that concurrent generations exhausted the
# account's output-tokens-per-minute allowance. That diagnosis was wrong:
# the account's live headers report 2,000,000 output and 10,000,000 input
# tokens per minute, and eight calls capped at max_tokens=16000 cannot
# exceed 128,000 output tokens even if every one of them ran to its limit in
# the same minute — under 7% of the budget. The stalls were real but came
# from elsewhere (see _dispatch_specialist: the deterministic floor and the
# per-fact ledger writes are synchronous, and while they hold the event loop
# no concurrent response is being read).
_MODEL_CONCURRENCY = int(os.environ.get("MANDATE_MODEL_CONCURRENCY", "8"))
_model_slots: asyncio.Semaphore | None = None


def _model_slot() -> asyncio.Semaphore:
    global _model_slots
    if _model_slots is None:
        _model_slots = asyncio.Semaphore(_MODEL_CONCURRENCY)
    return _model_slots
# 1 initial draft + at most 2 regenerations, then blocked (CLAUDE.md).
_MAX_GROUNDING_RETRIES = 2
# The human-directed loop is bounded by the human — every iteration costs an
# explicit named decision. This cap is belt-and-braces, not the real control.
_MAX_REVIEWER_ROUNDS = 3


from pipeline.review_basis import snapshot_basis


def _new_run_id(kind: str) -> str:
    return f"{kind[:3]}-{uuid.uuid4().hex[:12]}"


def _agents() -> dict:
    return {name: cls() for name, cls in AGENTS.items()}


def _next_round(record) -> int:
    """The first triage is round 1; every later triage or investigation pass
    is a new round of the same review."""
    return 1 + sum(1 for r in record.runs if r.kind in ("triage", "investigation"))


def _seed_from_record(record) -> dict:
    """A later round starts from what earlier rounds established, so its
    assessments can supersede theirs and the score is over the whole record."""
    return {"facts": record.facts, "assessments": record.assessments,
            "findings": record.findings, "failure_occurrences": record.failure_occurrences,
            "observations": record.observations}


# ---------------------------------------------------------------------------
# What every specialist pass shares: floor → context → record → review → record
# ---------------------------------------------------------------------------


def _record_dispatch(store: LedgerStore, state: SupervisionState, agent_name: str,
                     skill: str, composed: dict, instruction: str) -> None:
    record = DispatchRecord(
        case_id=state["case_id"], run_id=state["run_id"], target=agent_name, skill=skill,
        instruction=instruction, context_blocks=composed, context_digest=context_digest(composed),
    )
    # Recorded BEFORE the model call — the audit trail shows the briefing
    # even if the specialist then dies mid-flight.
    store.append(case_id=record.case_id, event_type="dispatch_recorded", run_id=state["run_id"],
                 payload=record.model_dump(), actor="agent:orchestrator")


async def _stream_specialist(store, state, name, status, facts=()):
    """Use the existing LangGraph → AG-UI → CopilotKit event stream.

    STEP_FINISHED is a stream transition, not a concurrent worker finishing.
    This explicit completion event lets the existing map show the truth.

    The payload is deliberately small: this agent's dispatch, assessments,
    postures and failures for this run, plus fact COUNTS and the ledger
    sequence range the facts occupy. The facts themselves stay on the
    ledger — pushing them through the stream twice per agent was 8 MB per
    triage, and the console's main thread stalled on it until the map's
    nodes went unmeasured and vanished mid-run. The console reads facts
    from the ledger when the run finishes or a turn is opened.
    """
    from collections import Counter

    from langchain_core.callbacks.manager import adispatch_custom_event
    own = [e for e in store.events_for_run(state['run_id'])
           if e.actor == f'agent:{name}' or (e.event_type == 'dispatch_recorded' and e.payload.get('target') == name)]
    fact_seqs = [e.seq for e in own if e.event_type == 'fact_recorded']
    kinds = Counter(f.kind for f in facts)
    await adispatch_custom_event('specialist_progress', {
        'agent': name, 'status': status, 'run_id': state['run_id'],
        'events': [e.model_dump() for e in own if e.event_type != 'fact_recorded'],
        'fact_counts': {'total': len(facts),
                        **{k: kinds.get(k, 0) for k in ('satisfied', 'breach', 'absent', 'measurement')}},
        'fact_seq_range': [min(fact_seqs), max(fact_seqs)] if fact_seqs else None,
    })


def _record_review(store: LedgerStore, state: SupervisionState, agent_name: str,
                   review: SpecialistReview, ruleset, *, observations_only: bool = False,
                   scope: list[str] | None = None) -> dict:
    """Append what one specialist pass produced — one event per fact,
    assessment, projected finding and observation — and return the state
    update. On an escalation round only the observations are new: the
    rule-backed verdicts were decided in round 0. A fact already on the
    record (a later round re-running a deterministic floor over an unchanged
    dossier) is not appended twice; an assessment always is, superseding
    the earlier round's."""
    run_id = state["run_id"]
    actor = f"agent:{agent_name}"
    for o in review.observations:
        store.append(case_id=o.case_id, event_type="observation_recorded", run_id=run_id,
                     payload=o.model_dump(), actor=actor)
    if review.narration:
        store.append(case_id=state["case_id"], event_type="specialist_narrated", run_id=run_id,
                     payload={"agent": agent_name, "narration": review.narration}, actor=actor)
    if observations_only:
        return {"observations": review.observations}
    from pipeline.review_support import version_review_facts, clear_reconsidered_rules
    review = version_review_facts(review, state)
    clear_reconsidered_rules(review, state, agent_name, ruleset)
    known = {f.fact_id for f in state.get("facts", [])}
    # Model-judged specialists historically emitted the rule id but not the
    # book version. The dispatcher knows the exact immutable book used, so it
    # closes that provenance field before anything reaches the ledger or the
    # failure-occurrence projection.
    if ruleset is not None:
        review.assessments = [
            a.model_copy(update={"ruleset_version": ruleset.version})
            if a.rule_id and not a.ruleset_version else a
            for a in review.assessments
        ]
    review.assessments = link_supersessions(review.assessments, state.get("assessments", []))
    scope = scope or state.get("run_scope") or None
    for a in review.assessments:
        a.review_run_refs = scope
    findings = project_findings(review.assessments, [ruleset] if ruleset else [])
    occurrences = project_failure_occurrences(
        review.assessments,
        [ruleset] if ruleset else [],
        load_failure_catalogue(),
    )
    for posture in review.postures:
        store.append(case_id=state["case_id"], event_type="control_posture_recorded", run_id=run_id,
                     payload=posture.model_dump(), actor=actor)
    for f in review.facts:
        if f.fact_id in known:
            continue
        store.append(case_id=f.case_id, event_type="fact_recorded", run_id=run_id,
                     payload=f.model_dump(), actor=actor, run_ref=f.run_ref)
    for a in review.assessments:
        store.append(case_id=a.case_id, event_type="assessment_recorded", run_id=run_id,
                     payload=a.model_dump(), actor=actor)
    for f in findings:
        store.append(case_id=f.case_id, event_type="finding_recorded", run_id=run_id,
                     payload=f.model_dump(), actor=actor)
    for occurrence in occurrences:
        store.append(
            case_id=occurrence.case_id,
            event_type="failure_occurrence_recorded",
            run_id=run_id,
            payload=occurrence.model_dump(),
            actor=actor,
        )
    return {"facts": review.facts, "assessments": review.assessments,
            "findings": findings, "failure_occurrences": occurrences,
            "observations": review.observations}


async def _dispatch_specialist(
    store: LedgerStore, model, state: SupervisionState, agent, *, ruleset,
    instruction: str = "", directive: str | None = None,
    prior: list[Observation] | None = None, extras: list | None = None,
    observations_only: bool = False, run_scope: list[str] | None = None,
) -> dict:
    """One specialist pass over the dossier in scope, recorded end to end."""
    run_scope = run_scope or state.get("run_scope") or None
    dossier = scoped(state["dossier"], run_scope)
    evidence = normalize_dossier(dossier) if run_scope else state.get("evidence")
    skill = SPECIALIST_SKILLS_BY_AGENT[agent.name]

    if agent.name in ("control_assurance", "systemic"):
        kwargs = {"rulebooks": load_all_rulesets()}
        if agent.name == "control_assurance":
            kwargs["peer_facts"] = [f for f in state.get("facts", []) if f.domain in PEERS]
            kwargs["peer_assessments"] = [a for a in state.get("assessments", []) if a.agent in PEERS]
        if agent.name == "systemic":
            kwargs["portfolio"] = [dossier_from_submission(latest_submission(store, cid))
                                   for cid in store.all_case_ids()]
        # `prompts` reaches these three for the same reason it reaches the
        # peers: they narrate too, and a supervisor's per-run prompt override
        # must apply to every line the console shows them.
        review = await agent.review(dossier, ruleset, evidence=evidence,
                                    prompts=state.get("prompts"),
                                    round=state.get("review_round", 1), **kwargs)
        context = canonical_context(
            skill, dossier, evidence=evidence, ruleset=ruleset, floor_facts=review.facts,
            peer_facts=kwargs.get("peer_facts"), portfolio=kwargs.get("portfolio"),
            peer_assessments=kwargs.get("peer_assessments"),
        )
        _record_dispatch(store, state, agent.name, skill, context, instruction)
        update = await asyncio.to_thread(_record_review, store, state, agent.name, review,
                                         ruleset, scope=run_scope)
        await _stream_specialist(store, state, agent.name, 'complete', review.facts)
        return update
    # Off the event loop, both of them. `run()` is the deterministic floor —
    # 650 rule evaluations and real Ed25519 verification for a fifty-run
    # dossier — and each `append` opens a connection, takes the writer lock,
    # hashes and commits (an fsync per fact). Run on the loop thread, either
    # one stops every *other* specialist's response from being read while it
    # works, which is what turned eight concurrent calls into eight calls
    # that all hit the 900 s timeout. The lock inside `append` still
    # serializes writers, so the hash chain is unaffected.
    floor_facts = await asyncio.to_thread(agent.run, dossier, ruleset, evidence=evidence)
    from pipeline.review_support import version_review_facts
    floor_facts = version_review_facts(SpecialistReview(facts=floor_facts, assessments=[]), state).facts
    # Facts land before the model starts; a timeout cannot erase the floor.
    known = {f.fact_id for f in state.get("facts", [])}
    if not observations_only:
        def _append_floor() -> None:
            for f in floor_facts:
                if f.fact_id not in known:
                    store.append(case_id=f.case_id, event_type="fact_recorded", run_id=state["run_id"],
                                 payload=f.model_dump(), actor=f"agent:{agent.name}", run_ref=f.run_ref)
        await asyncio.to_thread(_append_floor)
    composed: dict | None
    llm_context: dict | None = None
    if agent.name == "drift" and evidence is not None and not evidence.drift.sufficient:
        # Dispatched but declined on data availability — auditable as such,
        # without computing statistics over too little history.
        composed = {"insufficient_baseline_gate": True,
                    "transaction_count": len(dossier.transaction_history)}
    else:
        try:
            base = canonical_context(skill, dossier, evidence=evidence, ruleset=ruleset,
                                     floor_facts=floor_facts)
            composed = llm_context = compose_context(base, extras)
        except ContextCompositionError:
            composed = None  # no active rule for this skill — nothing to brief
    if composed is not None:
        _record_dispatch(store, state, agent.name, skill, composed, instruction)
    await _stream_specialist(store, state, agent.name, 'reasoning', floor_facts)

    kwargs = dict(evidence=evidence, model=model, reviewer_directive=directive,
                  prompts=state.get("prompts"), context=llm_context,
                  round=state.get("review_round", 1))
    if agent.name != "mandate":
        kwargs["prior_observations"] = prior
    if state.get("deterministic_only"):
        from pipeline.review_support import unjudged_review
        review = unjudged_review(agent, dossier, ruleset, floor_facts, state.get("review_round", 1))
    else:
        try:
            async with _model_slot():
                review = await asyncio.wait_for(agent.review(dossier, ruleset, **kwargs), timeout=_SPECIALIST_TIMEOUT_S)
        except Exception as exc:
            logging.getLogger(__name__).exception("%s review failed", agent.name)
            from pipeline.review_support import unjudged_review
            review = unjudged_review(agent, dossier, ruleset, floor_facts, state.get("review_round", 1))
            store.append(case_id=state["case_id"], event_type="specialist_failed", run_id=state["run_id"],
                         payload={"agent": agent.name, "error": type(exc).__name__,
                                  "message": "Judgment unavailable; deterministic evidence retained."},
                         actor=f"agent:{agent.name}")
    from pipeline.review_support import validate_review
    review = version_review_facts(review, {**state, "facts": [*state.get("facts", []), *floor_facts]})
    review = validate_review(review, dossier, ruleset)
    recording_state = {**state, "facts": [*state.get("facts", []), *floor_facts]}
    # Same reason as the floor above: this writes one event per assessment,
    # finding and occurrence, and it runs while its peers are still streaming.
    update = await asyncio.to_thread(_record_review, store, recording_state, agent.name, review,
                                     ruleset, observations_only=observations_only, scope=run_scope)
    if composed is not None:
        update["dispatch_contexts"] = {agent.name: composed}
    await _stream_specialist(store, state, agent.name, 'complete', review.facts)
    return update


# ---------------------------------------------------------------------------
# Review — one request through the orchestrator
# ---------------------------------------------------------------------------


def _unique(xs):
    return list(dict.fromkeys(xs))


def build_review_graph(*, model=None, store: LedgerStore | None = None, checkpointer=None,
                       rulesets: dict[str, Ruleset] | None = None) -> CompiledStateGraph:
    """`rulesets` overrides the active registry, domain by domain — the seam
    the policy sandbox uses to run a candidate rulebook through the real
    pipeline (agents/base.py takes the book as an argument for exactly this
    reason). Omit it and every agent gets the book that is in force."""
    store = store or get_default_store()
    agents = _agents()
    overrides = rulesets or {}

    def book(domain: str) -> "Ruleset | None":
        return overrides[domain] if domain in overrides else _RULESET_LOADERS[domain]()

    async def _ingest_node(state: SupervisionState) -> dict:
        case_id = state["case_id"]
        payload = latest_submission(store, case_id)
        dossier = dossier_from_submission(payload)
        evidence = normalize_dossier(dossier)
        record = project_case(store.events_for(case_id))
        review_round = _next_round(record)

        directive = state.get("reviewer_directive")
        first_pass = bool(state.get("first_pass")) and directive is None
        kind = "triage" if first_pass or directive is not None else "investigation"
        request = state.get("officer_message") or (directive.instructions if directive else FIRST_PASS_REQUEST)
        run_id = _new_run_id(kind)
        prompts = assemble_run_prompts(kind, state.get("prompt_overrides"))
        officer = state.get("officer") or "officer"
        question_id = state.get("question_id") or f"Q-{uuid.uuid4().hex[:8]}"
        store.append(
            case_id=case_id, event_type="run_started", run_id=run_id,
            payload={
                "run_id": run_id, "kind": kind, "prompts": prompts,
                "review_basis": snapshot_basis(store),
                "deterministic_only": state.get("deterministic_only", False),
                "first_pass": first_pass, "request": request,
                "runs_in_scope": len(dossier.runs), "review_round": review_round,
                **({"directive": directive.model_dump()} if directive else {}),
            },
            actor="system:review",
        )
        if kind == "investigation":
            store.append(case_id=case_id, event_type="question_asked", run_id=run_id,
                         payload={"question_id": question_id, "question": request}, actor=f"human:{officer}")
        return {
            "dossier": dossier,
            "evidence": evidence,
            "run_scope": [],
            "run_id": run_id,
            "prompts": prompts,
            "question_id": question_id,
            "officer_message": request,
            "first_pass": first_pass,
            "pass_number": 1 if first_pass else 2,
            "review_round": review_round,
            "firm_name": (payload.get("firm") or {}).get("name", dossier.dossier.operator_id),
            **(_seed_from_record(record) if review_round > 1 else {}),
        }

    async def _orchestrate_node(state: SupervisionState) -> dict:
        case_id = state["case_id"]
        dossier = state["dossier"]
        directive = state.get("reviewer_directive")
        first_pass = bool(state.get("first_pass"))
        if directive is not None:
            # A named reviewer said exactly what to re-examine: no model call.
            decision = OrchestratorDecision(
                reasoning=f"Directed re-analysis by a named reviewer: {directive.instructions}",
                intent="dispatch", message_to_officer="Re-examining as directed.",
                dispatches=[Dispatch(skill=SPECIALIST_SKILLS_BY_AGENT[a], instruction=directive.instructions,
                                     run_scope=list(directive.run_scope)) for a in directive.target_agents
                            if a in SPECIALIST_SKILLS_BY_AGENT],
            )
        elif state.get("deterministic_only"):
            decision = OrchestratorDecision(
                reasoning="Comprehensive deterministic review; model judgments remain unresolved.",
                intent="dispatch", message_to_officer="Running every rule; no model judgement in this pass.",
                dispatches=[Dispatch(skill=s) for s in REVIEW_SKILLS],
            )
        elif first_pass:
            # Coverage is fixed policy on the initial review. Paying a model
            # to rediscover the same fan-out was slower, stochastic, and
            # capable of accidentally omitting a skill.
            decision = first_pass_decision()
        else:
            record = project_case(store.events_for(case_id))
            try:
                decision = await route(
                    state.get("officer_message") or FIRST_PASS_REQUEST, record,
                    first_pass=first_pass, known_runs={r.run_id for r in dossier.runs}, model=model,
                    system_prompt=effective_text(state["prompts"], "ORCHESTRATOR"),
                )
            except Exception as exc:  # noqa: BLE001 — the model, the network, the account
                # The turn still completes and says what happened, on the
                # record; a run that dies here would otherwise sit half-written
                # on the ledger with nothing said to the officer.
                logging.getLogger(__name__).exception("orchestrator call failed on %s", case_id)
                detail = str(exc).split("\n")[0][:300]
                store.append(case_id=case_id, event_type="specialist_failed", run_id=state["run_id"],
                             payload={"agent": "orchestrator", "error": type(exc).__name__,
                                      "message": f"The orchestrator could not reach the model: {detail}"},
                             actor="agent:orchestrator")
                decision = OrchestratorDecision(
                    reasoning="", intent="reply", dispatches=[],
                    message_to_officer=f"I could not reach the model to decide what to run ({type(exc).__name__}). "
                                       f"Nothing was dispatched. {detail}",
                )
        skills = decision.targets
        plan = DispatchPlan(
            reasoning=decision.reasoning, intent=decision.intent, first_pass=first_pass, skills=skills,
            briefings={d.skill: d.instruction for d in decision.dispatches if d.instruction},
            run_scope={d.skill: d.run_scope for d in decision.dispatches if d.run_scope},
            context_blocks={d.skill: d.context_blocks for d in decision.dispatches if d.context_blocks},
            not_dispatched=[s for s in REVIEW_SKILLS if s not in skills] if first_pass and decision.intent == "dispatch" else [],
            message_to_officer=decision.message_to_officer,
        )
        store.append(
            case_id=case_id, event_type="dispatch_planned", run_id=state["run_id"],
            payload={"plan": plan.model_dump(), "selected_skills": skills, "decision": decision.model_dump()},
            actor="agent:orchestrator",
        )
        return {
            "dispatch_plan": plan, "selected_skills": skills, "escalation_round": 0,
            "dispatch_briefings": {SKILLS[d.skill].agent: d.model_dump() for d in decision.dispatches},
            "orchestrator_decision": decision.model_dump(),
            "orchestrator_reply": decision.message_to_officer,
        }

    def _route_from_orchestrator(state: SupervisionState) -> list[str] | str:
        decision = OrchestratorDecision.model_validate(state["orchestrator_decision"])
        if decision.intent != "dispatch" or not decision.dispatches:
            return "record"
        names = _unique(SKILLS[d.skill].agent for d in decision.dispatches)
        peers = [n for n in names if n != "control_assurance"]
        return peers or ["control_assurance"]

    def _run_observations(state: SupervisionState) -> list[Observation]:
        """Only what THIS run's specialists left open. The state is seeded with
        every observation ever recorded on the case; a second look that
        re-opened them all on every question would never end."""
        return [Observation.model_validate(e.payload) for e in store.events_for_run(state["run_id"])
                if e.event_type == "observation_recorded"]

    def _briefing(state: SupervisionState, agent_name: str) -> dict:
        return (state.get("dispatch_briefings") or {}).get(agent_name) or {}

    def _extras(state: SupervisionState, agent_name: str) -> list | None:
        blocks = _briefing(state, agent_name).get("context_blocks") or []
        if not blocks:
            return None
        return resolve_blocks(project_case(store.events_for(state["case_id"])), blocks)

    def _specialist_node(agent_name: str):
        agent = agents[agent_name]

        async def node(state: SupervisionState) -> dict:
            brief = _briefing(state, agent_name)
            instruction = brief.get("instruction") or ""
            # One call per specialist per review. A specialist that cannot
            # decide records `inconclusive` and the officer's own follow-up
            # question is the second look.
            return await _dispatch_specialist(
                store, model, state, agent, ruleset=book(agent_name), instruction=instruction,
                directive=brief.get("instruction") or None, extras=_extras(state, agent_name),
                run_scope=brief.get("run_scope") or None,
            )

        node.__name__ = f"_{agent_name}_node"
        return node

    async def _investigator_node(state: SupervisionState) -> dict:
        brief = _briefing(state, "investigator")
        question = brief.get("instruction") or state.get("officer_message", "")
        extras = _extras(state, "investigator") or []
        composed = {"question": question, "context_blocks": [b.model_dump() for b in extras]}
        _record_dispatch(store, state, "investigator", "investigator.lookup", composed, brief.get("instruction") or "")
        answer, observations = await investigate(
            scoped(state["dossier"], brief.get("run_scope") or state.get("run_scope")), question,
            question_id=state["question_id"], store=store, model=model,
            system_prompt=effective_text(state["prompts"], "INVESTIGATOR"),
        )
        store.append(case_id=answer.case_id, event_type="investigation_completed",
                     run_id=state["run_id"], payload=answer.model_dump(), actor="agent:investigator")
        for o in observations:
            store.append(case_id=o.case_id, event_type="observation_recorded",
                         run_id=state["run_id"], payload=o.model_dump(), actor="agent:investigator")
        return {"observations": observations}

    async def _specialists_done_node(state: SupervisionState) -> dict:
        return {}  # pure join point for the peer fan-out

    def _peers_ran(state: SupervisionState) -> bool:
        return any(SKILLS[s].agent in PEERS for s in state.get("selected_skills", []) if s in SKILLS)

    def _route_after_specialists(state: SupervisionState) -> str:
        return "control_assurance" if _peers_ran(state) else "record"

    async def _control_node(state: SupervisionState) -> dict:
        return await _dispatch_specialist(store, model, state, agents["control_assurance"],
                                          ruleset=book("control_assurance"))

    async def _critic_node(state: SupervisionState) -> dict:
        results = check_evidence_grounding(
            [a for a in state.get("assessments", []) if a.round == state.get("review_round")],
            state.get("observations", []), state.get("dispatch_contexts", {}),
        )
        for result in results:
            store.append(case_id=state["case_id"], event_type="critic_checked",
                         run_id=state["run_id"], payload=result.model_dump(), actor="system:critic")
        return {"critic_results": [r.model_dump() for r in results]}

    async def _synthesizer_node(state: SupervisionState) -> dict:
        run_events = store.events_for_run(state["run_id"])
        findings = current_findings(state.get("findings", []), state.get("assessments", []))
        changed = any(e.event_type == "finding_recorded" for e in run_events)
        correlations = await synthesize(
            state["case_id"], findings, model=model,
            system_prompt=effective_text(state["prompts"], "SYNTHESIZER") if state.get("prompts") else None,
        ) if changed and len(findings) >= 2 and not state.get("deterministic_only") else []
        for correlation in correlations:
            store.append(case_id=correlation.case_id, event_type="correlation_recorded",
                         run_id=state["run_id"], payload=correlation.model_dump(), actor="agent:synthesizer")
        return {"correlations": correlations}

    async def _close_out(state, recommendation, findings, score) -> None:
        """The orchestrator's last word on the turn: what came back, in three
        sentences, over a record that is already final. It reads the finished
        recommendation and cannot change it — a brief that fails to arrive
        costs the officer a sentence, never a verdict, so a failure here is
        logged and the turn completes."""
        if state.get("deterministic_only"):
            return
        try:
            brief = await close_out(
                recommendation, findings, score=score,
                correlations=state.get("correlations") or [], model=model,
                system_prompt=effective_text(state["prompts"], "ORCHESTRATOR-CLOSING") if state.get("prompts") else None,
            )
        except Exception:
            logging.getLogger(__name__).exception("closing brief failed on %s", state["case_id"])
            return
        store.append(
            case_id=state["case_id"], event_type="orchestrator_summarised", run_id=state["run_id"],
            payload=brief.model_dump(), actor="agent:orchestrator",
        )

    async def _record_node(state: SupervisionState) -> dict:
        case_id = state["case_id"]
        decision = state.get("orchestrator_decision") or {}
        plan = state.get("dispatch_plan")
        run_events = store.events_for_run(state["run_id"])
        kind = next((e.payload.get("kind") for e in run_events if e.event_type == "run_started"), "investigation")
        # The orchestrator's own turn goes on the record — what it routed,
        # with what briefing, and what it told the officer.
        store.append(
            case_id=case_id, event_type="orchestrator_replied", run_id=state["run_id"],
            payload={
                "intent": decision.get("intent"),
                "targets": [d.get("skill") for d in decision.get("dispatches", [])],
                "instruction": next((d.get("instruction") for d in decision.get("dispatches", []) if d.get("instruction")), ""),
                "briefings": plan.briefings if plan else {},
                "run_scope": sorted({r for d in decision.get("dispatches", []) for r in d.get("run_scope", [])}),
                "not_dispatched": plan.not_dispatched if plan else [],
                "message": decision.get("message_to_officer", ""),
            },
            actor="agent:orchestrator",
        )
        updates: dict = {"reviewer_directive": None}
        if any(e.event_type == "assessment_recorded" for e in run_events):
            findings = current_findings(state.get("findings", []), state.get("assessments", []))
            score = score_findings(case_id, findings, load_scoring_config())
            store.append(case_id=case_id, event_type="score_computed", run_id=state["run_id"],
                         payload=score.model_dump(), actor="system:scoring")
            from pipeline.authorisation import record_recommendation
            recommendation = record_recommendation(store, state)
            updates["risk_score"] = score
            await _close_out(state, recommendation, findings, score)
        store.append(
            case_id=case_id, event_type="run_completed", run_id=state["run_id"],
            payload={
                "run_id": state["run_id"], "kind": kind,
                "fact_count": len(state.get("facts", [])),
                "assessment_count": len(state.get("assessments", [])),
                "finding_count": sum(1 for e in run_events if e.event_type == "finding_recorded"),
                "observation_count": sum(1 for e in run_events if e.event_type == "observation_recorded"),
            },
            actor="system:review",
        )
        return updates

    graph = StateGraph(SupervisionState)
    graph.add_node("ingest", _ingest_node)
    graph.add_node("orchestrate", _orchestrate_node)
    for name in _SPECIALIST_NODES:
        graph.add_node(name, _specialist_node(name))
    graph.add_node("investigator", _investigator_node)
    graph.add_node("specialists_done", _specialists_done_node)
    graph.add_node("control_assurance", _control_node)
    graph.add_node("critic", _critic_node)
    graph.add_node("synthesizer", _synthesizer_node)
    graph.add_node("record", _record_node)

    graph.add_edge(START, "ingest")
    graph.add_edge("ingest", "orchestrate")
    graph.add_conditional_edges("orchestrate", _route_from_orchestrator,
                                [*_SPECIALIST_NODES, "investigator", "control_assurance", "record"])
    for node in (*_SPECIALIST_NODES, "investigator"):
        graph.add_edge(node, "specialists_done")
    graph.add_conditional_edges("specialists_done", _route_after_specialists, ["control_assurance", "record"])
    graph.add_edge("control_assurance", "critic")
    graph.add_edge("critic", "synthesizer")
    graph.add_edge("synthesizer", "record")
    graph.add_edge("record", END)

    # checkpointer is AG-UI thread plumbing only (api/main.py) — disposable,
    # never the record. run_triage() compiles without one: nothing interrupts.
    return graph.compile(checkpointer=checkpointer)


# The two run kinds are one graph; these names stay for the callers.
build_triage_graph = build_review_graph
build_investigation_graph = build_review_graph


def _initial_state(case_id: str, **extra) -> dict:
    return {"case_id": case_id, "facts": [], "assessments": [], "findings": [],
            "observations": [], "messages": [], **extra}


async def run_triage(
    case_id: str,
    *,
    model=None,
    store: LedgerStore | None = None,
    prompt_overrides: dict[str, str] | None = None,
    directive: ReviewerDirective | None = None,
    deterministic_only: bool = False,
    rulesets: dict[str, Ruleset] | None = None,
):
    """A first pass (or a directed re-analysis). Starts, appends everything
    it produces to the ledger, exits. Returns the projected CaseRecord — the
    durable truth, not the transient graph state."""
    store = store or get_default_store()
    graph = build_review_graph(model=model, store=store, rulesets=rulesets)
    initial = _initial_state(
        case_id, first_pass=directive is None, deterministic_only=deterministic_only,
        **({"prompt_overrides": prompt_overrides} if prompt_overrides else {}),
        **({"reviewer_directive": directive} if directive else {}),
    )
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
            state["draft_report"], state.get("findings", []), state.get("observations", []),
            risk_score=state.get("risk_score"),
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


# ---------------------------------------------------------------------------
# A question
# ---------------------------------------------------------------------------


async def run_investigation(
    case_id: str,
    officer_message: str,
    *,
    officer: str = "officer",
    model=None,
    store: LedgerStore | None = None,
    prompt_overrides: dict[str, str] | None = None,
):
    """One officer message through the orchestrator. Returns (CaseRecord,
    the orchestrator's reply) — the record is the durable truth; the reply
    is conversational surface."""
    store = store or get_default_store()
    graph = build_review_graph(model=model, store=store)
    state = await graph.ainvoke(_initial_state(
        case_id, officer_message=officer_message, officer=officer, first_pass=False,
        **({"prompt_overrides": prompt_overrides} if prompt_overrides else {}),
    ))
    return project_case(store.events_for(case_id)), state.get("orchestrator_reply", "")
