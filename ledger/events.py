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
    "dossier_submitted",
    "control_posture_recorded", "specialist_failed", "authorisation_computed",
    "authorisation_decided", "run_evaluated", "case_watched",
    "case_submitted",          # the submission: dossier.json + runs + transaction_history + firm
    "fact_recorded",           # Fact — one per fact, so each has its own seq and actor
    "assessment_recorded",     # Assessment
    "case_opened",             # {}
    "run_started",             # {run_id, kind, prompts: {prompt_id: {effective, override, default_version}}}
    "dispatch_planned",        # {plan: DispatchPlan, selected_skills} — the orchestrator's own reasoning
    "dispatch_recorded",       # DispatchRecord — the exact context sent to one agent
    "finding_recorded",        # Finding
    "failure_occurrence_recorded",  # FailureOccurrence: named F-id + exact affected runs
    "observation_recorded",    # Observation
    # {agent, narration} — the specialist's briefing line for the officer,
    # written over its own assessments only. Model-written prose, so it is
    # recorded like any other model output and is never citable evidence:
    # the report cites assessments, not a paraphrase of them.
    "specialist_narrated",
    "critic_checked",          # {target, finding_id?, passed, unquoted_values}
    "correlation_recorded",    # Correlation
    "escalation_round_started",  # {round, targets}
    "score_computed",          # RiskScore
    "run_completed",           # {run_id, kind, finding_count, observation_count}
    "question_asked",          # {question_id, question}
    "orchestrator_replied",    # {intent, targets, instruction, message} — the routing decision, on the record
    # {message, main_risks, breach_count, disposition} — the orchestrator's
    # closing brief once the specialists have reported. Presentational: the
    # counts in it are the authorisation policy's, and nothing reads it back.
    "orchestrator_summarised",
    "investigation_completed",  # InvestigationAnswer
    "report_drafted",          # DraftReport
    "grounding_checked",       # {passed, problems, attempt}
    "report_blocked",          # {problems}
    "decision_recorded",       # ReviewerDecision
    "case_closed",             # {reason}
    # {reason, cleared_through_seq} — the review history is set aside so the
    # next run starts from the submission alone. Nothing is deleted: the
    # ledger stays append-only and every earlier event is still readable and
    # still in the hash chain. The projection simply stops carrying work
    # recorded before this marker, and WHO reset it and WHEN is itself on
    # the record — which is the only version of "clear history" a hash-
    # chained audit trail can honestly offer.
    "review_history_cleared",
    # {domain, from_version, to_version, draft_id, sweep_id, rationale, edits,
    #  evidence} — a rulebook becomes policy. The sweep id is the point: the
    # evidence a promotion rested on is part of the promotion record, so
    # "what did you know when you tightened this?" has an answer.
    "ruleset_promoted",
})

_ACTOR_PREFIXES = ("system:", "agent:", "human:")


class LedgerEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int
    case_id: str
    run_id: str | None
    run_ref: str | None = None
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
