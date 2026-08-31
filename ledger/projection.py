"""events → CaseRecord (architecture-v2 §11). A pure function.

Case status is **computed from history, never stored** — a stored status
column can disagree with the events; a derived one cannot. Same principle as
pipeline/scoring.py::score_findings(), which recomputes rather than reading a
saved number.

Dedup reuses pipeline/state.py's reducers verbatim — one definition of "the
same finding" across the run reducer and the projection, so a re-triage that
re-derives an identical finding doesn't double it in the record. (This is
also why Stage 0's finding_id-prefix fix is a hard prerequisite: with the old
collision, dedup here would silently drop a real finding.)
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pipeline.state import _add_findings, _add_observations
from schemas import (
    Correlation,
    DispatchPlan,
    DispatchRecord,
    DraftReport,
    Finding,
    InvestigationAnswer,
    Observation,
    ReviewerDecision,
    RiskScore,
)

from .events import LedgerEvent

CaseStatus = Literal[
    "submitted",
    "triaged",
    "under_review",
    "investigating",
    "pending_decision",
    "issued",
    "closed_rejected",
    "closed_no_action",
]

RunKind = Literal["triage", "investigation", "drafting"]


class RunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    kind: RunKind
    # prompt_id -> {effective, override, default_version} exactly as recorded
    # on run_started — the full text, not a pointer, since an overridden
    # prompt has no stable artifact to point at (§6).
    prompts: dict[str, dict] = Field(default_factory=dict)
    plan: DispatchPlan | None = None      # the orchestrator's own reasoning (dispatch_planned)
    dispatches: list[DispatchRecord] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    correlations: list[Correlation] = Field(default_factory=list)
    risk_score: RiskScore | None = None
    started_at: str
    completed_at: str | None = None


class RunDiff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_a: str
    run_b: str
    prompts_changed: list[str]  # prompt_ids whose effective text differs
    findings_only_in_a: list[Finding]
    findings_only_in_b: list[Finding]
    findings_in_both: list[str]  # by type+agent identity, see diff_runs()
    dispatch_targets_a: list[str]
    dispatch_targets_b: list[str]


class CaseRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    status: CaseStatus
    firm: str
    runs: list[RunRecord] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)       # union across runs, deduped
    observations: list[Observation] = Field(default_factory=list)
    correlations: list[Correlation] = Field(default_factory=list)
    answers: list[InvestigationAnswer] = Field(default_factory=list)
    risk_score: RiskScore | None = None                          # latest computed
    draft_report: DraftReport | None = None                      # latest drafted
    report_blocked: bool = False
    grounding_problems: list[str] = Field(default_factory=list)
    decisions: list[ReviewerDecision] = Field(default_factory=list)
    open_questions: list[dict] = Field(default_factory=list)     # {question_id, question}
    opened_by: str | None = None
    submitted_summary: str | None = None
    escalation_rounds: int = 0
    first_event_at: str
    last_event_at: str
    event_count: int


class EmptyCaseError(ValueError):
    """project_case() over zero events — there is no such case, and returning
    a phantom record would let a typo'd case_id look like a real, clean case."""


def _derive_status(
    *,
    closed: bool,
    decisions: list[ReviewerDecision],
    has_grounded_draft_after_last_decision: bool,
    open_questions: bool,
    opened: bool,
    triaged: bool,
) -> CaseStatus:
    if closed:
        return "closed_no_action"
    if decisions:
        last = decisions[-1]
        if last.action == "approve":
            return "issued"
        if last.action == "reject":
            return "closed_rejected"
        # a rerun decision is not terminal — falls through to the live states
    if has_grounded_draft_after_last_decision:
        return "pending_decision"
    if open_questions:
        return "investigating"
    if opened:
        return "under_review"
    if triaged:
        return "triaged"
    return "submitted"


def project_case(events: list[LedgerEvent]) -> CaseRecord:
    if not events:
        raise EmptyCaseError("cannot project a case from zero events")

    case_id = events[0].case_id
    firm = "unknown"
    submitted_summary: str | None = None
    runs: dict[str, RunRecord] = {}
    run_order: list[str] = []
    findings: list[Finding] = []
    observations: list[Observation] = []
    correlations: list[Correlation] = []
    answers: list[InvestigationAnswer] = []
    decisions: list[ReviewerDecision] = []
    questions: dict[str, dict] = {}
    answered: set[str] = set()
    risk_score: RiskScore | None = None
    draft_report: DraftReport | None = None
    report_blocked = False
    grounding_problems: list[str] = []
    opened_by: str | None = None
    closed = False
    triaged = False
    escalation_rounds = 0
    # a draft only "awaits a decision" if no decision has landed after it
    draft_pending = False

    for event in events:
        payload = event.payload
        kind = event.event_type

        if kind == "case_submitted":
            firm = (payload.get("firm") or {}).get("name", firm)
            submitted_summary = payload.get("narrative") or submitted_summary
        elif kind == "case_opened":
            opened_by = event.actor.removeprefix("human:")
        elif kind == "run_started":
            run = RunRecord(
                run_id=payload["run_id"],
                kind=payload["kind"],
                prompts=payload.get("prompts", {}),
                started_at=event.recorded_at,
            )
            runs[run.run_id] = run
            run_order.append(run.run_id)
        elif kind == "dispatch_planned":
            if event.run_id in runs and "plan" in payload:
                runs[event.run_id].plan = DispatchPlan.model_validate(payload["plan"])
        elif kind == "dispatch_recorded":
            record = DispatchRecord.model_validate(payload)
            if record.run_id in runs:
                runs[record.run_id].dispatches.append(record)
        elif kind == "finding_recorded":
            finding = Finding.model_validate(payload)
            findings = _add_findings(findings, [finding])
            if event.run_id in runs:
                runs[event.run_id].findings = _add_findings(runs[event.run_id].findings, [finding])
        elif kind == "observation_recorded":
            observation = Observation.model_validate(payload)
            observations = _add_observations(observations, [observation])
            if event.run_id in runs:
                runs[event.run_id].observations = _add_observations(
                    runs[event.run_id].observations, [observation]
                )
        elif kind == "correlation_recorded":
            correlation = Correlation.model_validate(payload)
            correlations.append(correlation)
            if event.run_id in runs:
                runs[event.run_id].correlations.append(correlation)
        elif kind == "score_computed":
            risk_score = RiskScore.model_validate(payload)
            if event.run_id in runs:
                runs[event.run_id].risk_score = risk_score
        elif kind == "run_completed":
            if event.run_id in runs:
                runs[event.run_id].completed_at = event.recorded_at
            if payload.get("kind") == "triage" or (event.run_id in runs and runs[event.run_id].kind == "triage"):
                triaged = True
        elif kind == "escalation_round_started":
            escalation_rounds += 1
        elif kind == "question_asked":
            questions[payload["question_id"]] = payload
        elif kind == "investigation_completed":
            answer = InvestigationAnswer.model_validate(payload)
            answers.append(answer)
            answered.add(answer.question_id)
        elif kind == "report_drafted":
            draft_report = DraftReport.model_validate(payload)
            draft_pending = False  # pending only once grounding passes
        elif kind == "grounding_checked":
            grounding_problems = payload.get("problems", [])
            if payload.get("passed"):
                draft_pending = True
                report_blocked = False
        elif kind == "report_blocked":
            report_blocked = True
            grounding_problems = payload.get("problems", grounding_problems)
            draft_pending = False
        elif kind == "decision_recorded":
            decisions.append(ReviewerDecision.model_validate(payload))
            draft_pending = False
        elif kind == "case_closed":
            closed = True

    open_questions = [q for qid, q in questions.items() if qid not in answered]

    status = _derive_status(
        closed=closed,
        decisions=decisions,
        has_grounded_draft_after_last_decision=draft_pending,
        open_questions=bool(open_questions),
        # A recorded decision or an asked question is human engagement even
        # without an explicit case_opened event — a rerun or an answered
        # investigation leaves the case live under review.
        opened=opened_by is not None or bool(decisions) or bool(questions),
        triaged=triaged,
    )

    return CaseRecord(
        case_id=case_id,
        status=status,
        firm=firm,
        runs=[runs[rid] for rid in run_order],
        findings=findings,
        observations=observations,
        correlations=correlations,
        answers=answers,
        risk_score=risk_score,
        draft_report=draft_report,
        report_blocked=report_blocked,
        grounding_problems=grounding_problems,
        decisions=decisions,
        open_questions=open_questions,
        opened_by=opened_by,
        submitted_summary=submitted_summary,
        escalation_rounds=escalation_rounds,
        first_event_at=events[0].recorded_at,
        last_event_at=events[-1].recorded_at,
        event_count=len(events),
    )


def diff_runs(a: RunRecord, b: RunRecord) -> RunDiff:
    """What changed between two passes over the same case. Findings are
    matched by (agent, type, rule_id) — their *identity as a verdict* — not
    finding_id, which legitimately differs between runs."""

    def key(f: Finding) -> tuple:
        return (f.agent, f.type, f.rule_id)

    keys_a = {key(f) for f in a.findings}
    keys_b = {key(f) for f in b.findings}

    prompts_changed = sorted(
        pid
        for pid in set(a.prompts) | set(b.prompts)
        if (a.prompts.get(pid) or {}).get("effective") != (b.prompts.get(pid) or {}).get("effective")
    )

    return RunDiff(
        run_a=a.run_id,
        run_b=b.run_id,
        prompts_changed=prompts_changed,
        findings_only_in_a=[f for f in a.findings if key(f) not in keys_b],
        findings_only_in_b=[f for f in b.findings if key(f) not in keys_a],
        findings_in_both=sorted(f"{ag}:{ty}" for (ag, ty, _r) in keys_a & keys_b),
        dispatch_targets_a=[d.target for d in a.dispatches],
        dispatch_targets_b=[d.target for d in b.dispatches],
    )
