"""agents/drafting.py — payload discipline and retry-feedback plumbing
(PLAN item 12). The injection-containment property tested here is the
important one: the drafting agent's input must never contain raw
firm-authored text, only the structured record."""
from __future__ import annotations

import json

import pytest

from agents.drafting import draft_case_report
from agents.llm import ModelDidNotCallTool
from schemas import DispatchPlan, DraftReport, Finding, Observation
from tests.fakes import FakeChatModel

_PLAN = DispatchPlan(run_mandate=True, run_kya=True, run_log=False, run_drift=False, reasoning="thin history")

_DRAFT_ARGS = {
    "overall_assessment": "One breach found.",
    "sections": [{"title": "Cap breach", "body": "Cart exceeded the cap.", "cited_finding_ids": ["F-1"]}],
    "open_observations_note": None,
}


def _finding() -> Finding:
    return Finding(
        finding_id="F-1", case_id="CASE-T", agent="mandate", type="per_transaction_cap_exceeded",
        rule_id="MND-CAP-01", severity_weight=0.8, summary="Cart total 2150 exceeds cap 500.",
    )


async def test_returns_typed_report_with_case_id_attached():
    fake = FakeChatModel({"draft_case_report": _DRAFT_ARGS})
    report = await draft_case_report(
        case_id="CASE-T", firm_name="Kolkheti", findings=[_finding()], observations=[],
        dispatch_plan=_PLAN, escalation_round=0, model=fake,
    )
    assert isinstance(report, DraftReport)
    assert report.case_id == "CASE-T"
    assert report.sections[0].cited_finding_ids == ["F-1"]


async def test_payload_is_structured_record_only():
    fake = FakeChatModel({"draft_case_report": _DRAFT_ARGS})
    await draft_case_report(
        case_id="CASE-T", firm_name="Kolkheti",
        findings=[_finding()],
        observations=[Observation(case_id="CASE-T", agent="log", note="hunch", cited_evidence="e")],
        dispatch_plan=_PLAN, escalation_round=1, model=fake,
    )
    payload = json.loads(fake.last_messages[-1].content)
    # The structured record, and nothing else — most importantly no slot a
    # raw firm-authored string (natural_language_intent, line items,
    # prompt playback) could arrive through.
    assert set(payload) == {"firm", "risk", "findings", "unverified_observations", "dispatch", "escalation_round_ran"}
    assert payload["findings"][0]["finding_id"] == "F-1"
    assert payload["dispatch"]["ran"] == ["mandate", "kya"]
    assert payload["escalation_round_ran"] is True


async def test_retry_feedback_lands_in_system_prompt():
    fake = FakeChatModel({"draft_case_report": _DRAFT_ARGS})
    await draft_case_report(
        case_id="CASE-T", firm_name="Kolkheti", findings=[_finding()], observations=[],
        dispatch_plan=_PLAN, escalation_round=0, model=fake,
        prior_problems=["Finding 'F-1' is not cited by any section."],
    )
    system = fake.last_messages[0].content
    assert "FAILED grounding validation" in system
    assert "Finding 'F-1' is not cited" in system


async def test_first_attempt_has_no_retry_addendum():
    fake = FakeChatModel({"draft_case_report": _DRAFT_ARGS})
    await draft_case_report(
        case_id="CASE-T", firm_name="Kolkheti", findings=[], observations=[],
        dispatch_plan=_PLAN, escalation_round=0, model=fake,
    )
    assert "FAILED grounding validation" not in fake.last_messages[0].content


async def test_model_not_calling_tool_raises_clearly():
    fake = FakeChatModel({"some_other_tool": {}})
    with pytest.raises(ModelDidNotCallTool):
        await draft_case_report(
            case_id="CASE-T", firm_name="Kolkheti", findings=[], observations=[],
            dispatch_plan=_PLAN, escalation_round=0, model=fake,
        )
