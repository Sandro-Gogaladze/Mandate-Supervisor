"""LangGraph state shape (PLAN item 4, extended PLAN item 9).

`findings` and `observations` use a dedup-aware reducer, not plain
`operator.add`, so LangGraph concatenates each specialist node's returned
list into the running total on fan-in, rather than the last node to finish
clobbering the others — same idea as `operator.add`, but idempotent
against a node contributing the same finding/observation twice.

That case is real, not hypothetical: LangGraph's default retry policy
re-executes a node function from scratch on a transient error (e.g. a
flaky LLM call inside a specialist's agentic ceiling, after its
deterministic floor already computed real findings) — confirmed live via
a raw `/agent` trace showing the same node's STARTED/FINISHED events
repeat several times in one run, and, more concretely, via the frontend
rendering two `Finding`s with an identical `finding_id` after exactly such
a retry. `operator.add` has no way to know a retried node's output is a
repeat rather than something new; this reducer does, by identity
(`finding_id` for `Finding`, the full field tuple for `Observation`, which
has no id of its own).

`ingestion_findings` is kept separate from `findings` on purpose: it's
ingestion's own gate-level check (PLAN item 3), informational, not the
authoritative supervisory output. The Mandate/KYA specialist nodes
independently re-verify (against whatever ruleset they're given) rather
than replay it.

`dispatch_plan` / `escalation_round` are PLAN item 9: which specialists
the propose-enforce dispatch selected, and whether this is the one
permitted extra round (0 = first pass, 1 = the escalation round, capped
there — see pipeline/graph.py). On the escalation round, a re-dispatched
specialist node only contributes to `observations`, never `findings` — its
rule-backed verdicts were already decided in round 0; re-adding them would
duplicate what's already in state, not add anything new. See
docs/phases/09-dispatch-and-escalation.md.

`messages` (via `MessagesState`) is otherwise unused by this pipeline —
there's no chat loop — but CopilotKit's AG-UI protocol is built around a
message-thread abstraction even for non-chat, state-driven UIs (confirmed
against the official AG-UI LangGraph examples before adding this; the
"agentic generative ui" reference example keeps `messages` for exactly
this reason). Present so the UI layer (PLAN item 10) can attach.
"""
from __future__ import annotations

from typing import Annotated

from langgraph.graph import MessagesState

import operator

from ingestion.normalize import IngestedCase
from schemas import (
    Correlation,
    DispatchPlan,
    DraftReport,
    Finding,
    Observation,
    ReportStatus,
    ReviewerDecision,
    ReviewerDirective,
    RiskScore,
)


def _add_findings(existing: list[Finding], new: list[Finding]) -> list[Finding]:
    seen = {f.finding_id for f in existing}
    return existing + [f for f in new if f.finding_id not in seen]


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
    # event — never by filesystem path. (The old case_path was client-
    # controlled state fed to a file read; architecture-v2 §14.1.)
    case_id: str
    # Run bookkeeping (architecture-v2 §10.5): run_id groups this run's
    # ledger events; prompts is the assembled per-run prompt set recorded on
    # run_started; pass_number 1 = first triage (floor applies), 2 = a
    # directed pass (targets exactly what the human named).
    case: IngestedCase
    ingestion_findings: list[Finding]
    findings: Annotated[list[Finding], _add_findings]
    observations: Annotated[list[Observation], _add_observations]
    run_id: str
    pass_number: int
    firm_name: str
    # Investigation-run keys (architecture-v2 §14.2): the officer's message
    # and identity, the orchestrator's routing decision, and its reply.
    officer_message: str
    officer: str
    question_id: str
    orchestrator_decision: dict
    orchestrator_reply: str
    prompt_overrides: dict
    prompts: dict
    dispatch_plan: DispatchPlan
    selected_skills: list[str]
    escalation_round: int
    # agent -> the exact composed context it received (recorded on
    # dispatch_recorded; the critic reads this).
    dispatch_contexts: Annotated[dict, _merge_dispatch_contexts]
    # Deterministic critic results + validated synthesizer output — plain
    # overwrites, each is produced once per pass through the tail.
    critic_results: list[dict]
    correlations: list[Correlation]
    # PLAN item 12 — the drafting/grounding tail. All plain overwrites, no
    # reducers: exactly one draft is current at a time (a grounding retry
    # *replaces* the failed draft, it doesn't accumulate next to it).
    draft_report: DraftReport
    draft_attempts: int
    grounding_problems: list[str]
    report_blocked: bool
    # PLAN item 11 — the pure-function score; recomputed on every pass
    # through the tail (a reviewer-directed re-analysis may change findings,
    # so the number must follow them). Plain overwrite.
    risk_score: RiskScore
    # PLAN item 13 — the human gate. Decisions accumulate (an audit trail
    # of every named call made on this case); the directive is transient
    # steering for exactly one re-analysis pass, cleared once consumed;
    # status/rounds are plain overwrites.
    reviewer_decisions: Annotated[list[ReviewerDecision], operator.add]
    reviewer_directive: ReviewerDirective | None
    reviewer_rounds: int
    report_status: ReportStatus
