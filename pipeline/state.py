"""LangGraph state shape — the dossier through the graph (migration Phase 2).

`facts`, `assessments`, `findings` and `observations` use dedup-aware
reducers, not plain `operator.add`, so LangGraph concatenates each
specialist node's returned list into the running total on fan-in rather
than the last node to finish clobbering the others — and stays idempotent
against a node contributing the same item twice.

That case is real, not hypothetical: LangGraph's default retry policy
re-executes a node function from scratch on a transient error (e.g. a
flaky LLM call inside a specialist's reasoning pass, after its deterministic
floor already computed real facts) — confirmed live via a raw `/agent`
trace showing the same node's STARTED/FINISHED events repeat several times
in one run. `operator.add` has no way to know a retried node's output is a
repeat; these reducers do, by identity. Fact and assessment ids are
deterministic (`<case>:<rule>[:<run>]`), which is what makes this work.

`dossier` is the submission as loaded; `evidence` is what intake established
about it (signatures, registries, shared statistics, which blocks are
present); `run_scope` names the runs a round concerns — empty means the
whole dossier (round 1), a list means the orchestrator narrowed it (round 2,
Phase 5). `findings` are the projection of `assessments` the synthesis tail
(critic, synthesizer, scoring, drafting) still reads.

`dispatch_plan` / `escalation_round`: which specialists the propose-enforce
dispatch selected, and whether this is the one permitted extra round. On the
escalation round a re-dispatched specialist only contributes to
`observations`, never `assessments` — its rule-backed verdicts were decided
in round 0.

`messages` (via `MessagesState`) is otherwise unused by this pipeline —
there's no chat loop — but CopilotKit's AG-UI protocol is built around a
message-thread abstraction even for non-chat, state-driven UIs.
"""
from __future__ import annotations

import operator
from typing import Annotated

from langgraph.graph import MessagesState

from schemas import (
    Assessment,
    Correlation,
    DispatchPlan,
    DraftReport,
    EvidencePack,
    Fact,
    FailureOccurrence,
    Finding,
    Observation,
    ReportStatus,
    ReviewerDecision,
    ReviewerDirective,
    RiskScore,
)
from schemas.dossier import LoadedDossier


def _add_facts(existing: list[Fact], new: list[Fact]) -> list[Fact]:
    seen = {f.fact_id for f in existing}
    return existing + [f for f in new if f.fact_id not in seen]


def _add_assessments(existing: list[Assessment], new: list[Assessment]) -> list[Assessment]:
    seen = {a.assessment_id for a in existing}
    return existing + [a for a in new if a.assessment_id not in seen]


def _add_findings(existing: list[Finding], new: list[Finding]) -> list[Finding]:
    seen = {f.finding_id for f in existing}
    return existing + [f for f in new if f.finding_id not in seen]


def _add_failure_occurrences(
    existing: list[FailureOccurrence], new: list[FailureOccurrence]
) -> list[FailureOccurrence]:
    seen = {o.occurrence_id for o in existing}
    return existing + [o for o in new if o.occurrence_id not in seen]


def _add_observations(existing: list[Observation], new: list[Observation]) -> list[Observation]:
    def key(o: Observation) -> tuple:
        return (o.case_id, o.agent, o.note, o.cited_evidence)

    seen = {key(o) for o in existing}
    return existing + [o for o in new if key(o) not in seen]


def _merge_dispatch_contexts(existing: dict, new: dict) -> dict:
    """Parallel specialist nodes each contribute their own agent's composed
    context on fan-in; a later dispatch of the same agent (escalation round,
    directed pass) replaces its entry — the critic checks output against the
    context of the pass that produced it."""
    return {**existing, **new}


class SupervisionState(MessagesState, total=False):
    # The case is addressed by id and read from the ledger's case_submitted
    # event — never by filesystem path.
    case_id: str
    dossier: LoadedDossier
    evidence: EvidencePack
    run_scope: list[str]
    deterministic_only: bool
    facts: Annotated[list[Fact], _add_facts]
    assessments: Annotated[list[Assessment], _add_assessments]
    findings: Annotated[list[Finding], _add_findings]
    failure_occurrences: Annotated[list[FailureOccurrence], _add_failure_occurrences]
    observations: Annotated[list[Observation], _add_observations]
    # Run bookkeeping: run_id groups this run's ledger events; prompts is the
    # assembled per-run prompt set recorded on run_started; pass_number 1 =
    # first triage (floor applies), 2 = a directed pass.
    run_id: str
    pass_number: int
    # 1 on the first triage; each later triage or investigation pass is a
    # new round, and an assessment it makes of a claim an earlier round
    # already made supersedes the earlier one (agents/assess.py).
    review_round: int
    firm_name: str
    # Investigation-run keys: the officer's message and identity, the
    # orchestrator's routing decision, and its reply.
    officer_message: str
    officer: str
    question_id: str
    orchestrator_decision: dict
    orchestrator_reply: str
    prompt_overrides: dict
    prompts: dict
    dispatch_plan: DispatchPlan
    selected_skills: list[str]
    # True on the "run the review" turn: the graph uses the deterministic
    # complete first-pass dispatch instead of calling the routing model.
    first_pass: bool
    # agent -> {skill, instruction, run_scope, context_blocks}: the
    # orchestrator's briefing for each specialist it dispatched this turn.
    dispatch_briefings: dict
    escalation_round: int
    # agent -> the exact composed context it received (recorded on
    # dispatch_recorded; the critic reads this).
    dispatch_contexts: Annotated[dict, _merge_dispatch_contexts]
    critic_results: list[dict]
    correlations: list[Correlation]
    # The drafting/grounding tail. Plain overwrites: exactly one draft is
    # current at a time (a grounding retry *replaces* the failed draft).
    draft_report: DraftReport
    draft_attempts: int
    grounding_problems: list[str]
    report_blocked: bool
    # The pure-function score; recomputed on every pass through the tail.
    risk_score: RiskScore
    # The human gate. Decisions accumulate; the directive is transient
    # steering for exactly one re-analysis pass, cleared once consumed.
    reviewer_decisions: Annotated[list[ReviewerDecision], operator.add]
    reviewer_directive: ReviewerDirective | None
    reviewer_rounds: int
    report_status: ReportStatus
