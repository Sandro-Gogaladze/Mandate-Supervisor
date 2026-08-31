"""The ledger's event vocabulary (docs/architecture-v2.md §10.5).

An event is the unit of record: one thing that happened to one case, with a
typed payload, a mandatory actor, and its place in the hash chain. Events are
the *only* representation of a case — status and every projection derive from
them (ledger/projection.py), never the other way around.

`actor` is mandatory and typed by prefix: a finding recorded by `agent:drift`
and a decision recorded by `human:Ana Dvaladze` must be distinguishable a
year later without parsing the payload. `run_id` groups the events of one
bounded run (triage / investigation / drafting) so two runs of the same case
can be compared; case-level events (open, close, submit) carry none.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

# One finding per event, not a batch: "every finding citable" needs each
# finding to have its own seq, timestamp, and producing actor.
EVENT_TYPES = frozenset({
    "case_submitted",          # full raw CaseBundle dict
    "case_opened",             # {}
    "run_started",             # {run_id, kind, prompts: {prompt_id: {effective, override, default_version}}}
    "dispatch_planned",        # {plan: DispatchPlan, selected_skills} — the orchestrator's own reasoning
    "dispatch_recorded",       # DispatchRecord — the exact context sent to one agent
    "finding_recorded",        # Finding
    "observation_recorded",    # Observation
    "critic_checked",          # {target, finding_id?, passed, unquoted_values}
    "correlation_recorded",    # Correlation
    "escalation_round_started",  # {round, targets}
    "score_computed",          # RiskScore
    "run_completed",           # {run_id, kind, finding_count, observation_count}
    "question_asked",          # {question_id, question}
    "investigation_completed",  # InvestigationAnswer
    "report_drafted",          # DraftReport
    "grounding_checked",       # {passed, problems, attempt}
    "report_blocked",          # {problems}
    "decision_recorded",       # ReviewerDecision
    "case_closed",             # {reason}
})

_ACTOR_PREFIXES = ("system:", "agent:", "human:")


class LedgerEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int
    case_id: str
    run_id: str | None
    event_type: str
    payload: dict
    actor: str
    recorded_at: str  # ISO-8601 UTC, stamped by the store, never by the caller
    prev_hash: str
    hash: str

    @field_validator("event_type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        if v not in EVENT_TYPES:
            raise ValueError(f"unknown event_type {v!r}")
        return v

    @field_validator("actor")
    @classmethod
    def _typed_actor(cls, v: str) -> str:
        if not v.startswith(_ACTOR_PREFIXES) or v in _ACTOR_PREFIXES:
            raise ValueError(
                f"actor {v!r} must be '<kind>:<name>' with kind in "
                f"{[p.rstrip(':') for p in _ACTOR_PREFIXES]}"
            )
        return v
