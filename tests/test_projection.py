"""Stage 2 — events → CaseRecord (docs/architecture-v2.md §11)."""
from __future__ import annotations

import pytest

from ledger import LedgerStore
from ledger.projection import EmptyCaseError, diff_runs, project_case

CASE = "CASE-P-001"


@pytest.fixture
def store(tmp_path) -> LedgerStore:
    return LedgerStore(tmp_path / "ledger.db")


def _finding(fid: str, agent: str = "mandate", type_: str = "category_out_of_scope") -> dict:
    return {
        "finding_id": fid, "case_id": CASE, "agent": agent, "type": type_,
        "rule_id": "MND-CAP-02", "severity_weight": 0.7, "summary": "s", "details": {},
    }


def _decision(action: str, directive: dict | None = None) -> dict:
    return {
        "action": action, "reviewer": "Ana Dvaladze", "comment": None,
        "directive": directive, "decided_at": "2026-09-01T10:00:00+00:00",
    }


def _submit(store) -> None:
    store.append(case_id=CASE, event_type="case_submitted",
                 payload={"case_id": CASE, "firm": {"name": "Test Firm"}, "narrative": "n"},
                 actor="system:seed")


def _triage(store, run_id: str = "run-1", findings: list[dict] | None = None,
            prompts: dict | None = None) -> None:
    store.append(case_id=CASE, event_type="run_started",
                 payload={"run_id": run_id, "kind": "triage", "prompts": prompts or {}},
                 actor="system:triage", run_id=run_id)
    for f in findings or []:
        store.append(case_id=CASE, event_type="finding_recorded", payload=f,
                     actor=f"agent:{f['agent']}", run_id=run_id)
    store.append(case_id=CASE, event_type="run_completed",
                 payload={"run_id": run_id, "kind": "triage", "finding_count": len(findings or []),
                          "observation_count": 0},
                 actor="system:triage", run_id=run_id)


def test_empty_event_list_raises_not_phantom() -> None:
    with pytest.raises(EmptyCaseError):
        project_case([])


def test_submitted_then_triaged_then_under_review(store) -> None:
    _submit(store)
    assert project_case(store.events_for(CASE)).status == "submitted"

    _triage(store, findings=[_finding("F-1")])
    record = project_case(store.events_for(CASE))
    assert record.status == "triaged"
    assert record.firm == "Test Firm"
    assert [f.finding_id for f in record.findings] == ["F-1"]
    assert record.runs[0].kind == "triage"
    assert record.runs[0].completed_at is not None

    store.append(case_id=CASE, event_type="case_opened", payload={}, actor="human:Ana Dvaladze")
    record = project_case(store.events_for(CASE))
    assert record.status == "under_review"
    assert record.opened_by == "Ana Dvaladze"


def test_open_question_means_investigating_until_answered(store) -> None:
    _submit(store)
    _triage(store)
    store.append(case_id=CASE, event_type="case_opened", payload={}, actor="human:Ana")
    store.append(case_id=CASE, event_type="question_asked",
                 payload={"question_id": "Q-1", "question": "who is MER-BEF-005?"},
                 actor="human:Ana")
    assert project_case(store.events_for(CASE)).status == "investigating"

    store.append(case_id=CASE, event_type="investigation_completed",
                 payload={"case_id": CASE, "question_id": "Q-1", "question": "who is MER-BEF-005?",
                          "answer": "a new counterparty", "cited_evidence": [], "tool_calls": []},
                 actor="agent:investigator", run_id="run-inv-1")
    record = project_case(store.events_for(CASE))
    assert record.status == "under_review"
    assert record.open_questions == []
    assert len(record.answers) == 1


def test_grounded_draft_means_pending_decision_then_issued(store) -> None:
    _submit(store)
    _triage(store, findings=[_finding("F-1")])
    store.append(case_id=CASE, event_type="report_drafted",
                 payload={"case_id": CASE, "overall_assessment": "x", "sections": [],
                          "open_observations_note": None},
                 actor="agent:drafting", run_id="run-d-1")
    store.append(case_id=CASE, event_type="grounding_checked",
                 payload={"passed": True, "problems": [], "attempt": 1},
                 actor="system:grounding", run_id="run-d-1")
    assert project_case(store.events_for(CASE)).status == "pending_decision"

    store.append(case_id=CASE, event_type="decision_recorded", payload=_decision("approve"),
                 actor="human:Ana Dvaladze", run_id="run-d-1")
    record = project_case(store.events_for(CASE))
    assert record.status == "issued"
    assert record.decisions[-1].action == "approve"


def test_reject_closes_and_rerun_returns_to_under_review(store) -> None:
    _submit(store)
    _triage(store, findings=[_finding("F-1")])
    store.append(case_id=CASE, event_type="case_opened", payload={}, actor="human:Ana")
    store.append(case_id=CASE, event_type="report_drafted",
                 payload={"case_id": CASE, "overall_assessment": "x", "sections": [],
                          "open_observations_note": None},
                 actor="agent:drafting", run_id="run-d-1")
    store.append(case_id=CASE, event_type="grounding_checked",
                 payload={"passed": True, "problems": [], "attempt": 1},
                 actor="system:grounding", run_id="run-d-1")

    directive = {"instructions": "look again at Log", "target_agents": ["log"]}
    store.append(case_id=CASE, event_type="decision_recorded",
                 payload=_decision("rerun", directive), actor="human:Ana", run_id="run-d-1")
    # a rerun is not terminal — the case is live again, awaiting the directed pass
    assert project_case(store.events_for(CASE)).status == "under_review"

    store.append(case_id=CASE, event_type="decision_recorded", payload=_decision("reject"),
                 actor="human:Ana", run_id="run-d-2")
    assert project_case(store.events_for(CASE)).status == "closed_rejected"


def test_case_closed_wins_over_everything(store) -> None:
    _submit(store)
    _triage(store)
    store.append(case_id=CASE, event_type="case_closed", payload={"reason": "clean"},
                 actor="human:Ana")
    assert project_case(store.events_for(CASE)).status == "closed_no_action"


def test_rederived_finding_dedups_but_new_one_lands(store) -> None:
    _submit(store)
    _triage(store, "run-1", findings=[_finding("F-1")])
    # a second run re-derives the identical finding (same id) and adds a new one
    _triage(store, "run-2", findings=[_finding("F-1"), _finding("F-2", "kya", "signature_invalid")])
    record = project_case(store.events_for(CASE))
    assert [f.finding_id for f in record.findings] == ["F-1", "F-2"]
    assert [f.finding_id for f in record.runs[1].findings] == ["F-1", "F-2"]


def test_report_blocked_is_not_pending_decision(store) -> None:
    _submit(store)
    _triage(store, findings=[_finding("F-1")])
    store.append(case_id=CASE, event_type="report_drafted",
                 payload={"case_id": CASE, "overall_assessment": "x", "sections": [],
                          "open_observations_note": None},
                 actor="agent:drafting", run_id="run-d-1")
    store.append(case_id=CASE, event_type="report_blocked",
                 payload={"problems": ["Finding 'F-1' is not cited by any section"]},
                 actor="system:grounding", run_id="run-d-1")
    record = project_case(store.events_for(CASE))
    assert record.status == "triaged"
    assert record.report_blocked is True
    assert record.grounding_problems


def test_diff_runs_matches_verdict_identity_not_finding_id(store) -> None:
    _submit(store)
    prompts_a = {"ORCH-DISPATCH": {"effective": "default text", "override": None, "default_version": "2026.1"}}
    prompts_b = {"ORCH-DISPATCH": {"effective": "custom text", "override": "custom text", "default_version": "2026.1"}}
    _triage(store, "run-1", findings=[_finding("CASE-P-001-MND-001")], prompts=prompts_a)
    _triage(store, "run-2", findings=[
        _finding("CASE-P-001-MND-901"),  # same verdict, different id — must count as shared
        _finding("CASE-P-001-STR-001", "log", "transaction_structuring_detected"),
    ], prompts=prompts_b)
    record = project_case(store.events_for(CASE))
    diff = diff_runs(record.runs[0], record.runs[1])
    assert diff.prompts_changed == ["ORCH-DISPATCH"]
    assert diff.findings_only_in_a == []
    assert [f.type for f in diff.findings_only_in_b] == ["transaction_structuring_detected"]
    assert diff.findings_in_both == ["mandate:category_out_of_scope"]
