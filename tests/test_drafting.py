"""agents/drafting.py — payload discipline and retry-feedback plumbing
(PLAN item 12). The injection-containment property tested here is the
important one: the drafting agent's input must never contain raw
firm-authored text, only the structured record."""
from __future__ import annotations

import json

import pytest

from agents.drafting import draft_case_report
from agents.llm import ModelDidNotCallTool, message_text
from schemas import DispatchPlan, DraftReport, Finding, Observation
from tests.fakes import FakeChatModel

_PLAN = DispatchPlan(skills=["mandate.review", "kya.review"], reasoning="thin history", first_pass=True)

_DRAFT_ARGS = {
    "overall_assessment": "One breach found.",
    "sections": [{"title": "Cap breach", "body": "Cart exceeded the cap.", "cited_findings": [1],
                  "character": "adverse"}],
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
    assert fake.bind_kwargs_for("draft_case_report")["tool_choice"] == {"type": "any"}
    assert "output_config" not in fake.bind_kwargs_for("draft_case_report")


async def test_payload_is_structured_record_only():
    fake = FakeChatModel({"draft_case_report": _DRAFT_ARGS})
    await draft_case_report(
        case_id="CASE-T", firm_name="Kolkheti",
        findings=[_finding()],
        observations=[Observation(case_id="CASE-T", agent="log", note="hunch", cited_evidence="e")],
        dispatch_plan=_PLAN, escalation_round=1, model=fake,
    )
    payload = json.loads(message_text(fake.last_messages[-1]))
    # The structured record, and nothing else — most importantly no slot a
    # raw firm-authored string (natural_language_intent, line items,
    # prompt playback) could arrive through.
    assert set(payload) == {"firm", "risk", "findings", "unverified_observations", "dispatch", "escalation_round_ran"}
    # Numbered, not named: the briefing carries a short `ref` and the real
    # finding_id never reaches the model, so it cannot be asked to transcribe
    # ~900 tokens of opaque identifiers — or to invent one.
    assert payload["findings"][0]["ref"] == 1
    assert "finding_id" not in payload["findings"][0]
    assert payload["dispatch"]["ran"] == ["mandate", "kya"]
    assert payload["escalation_round_ran"] is True


async def test_model_not_calling_tool_fails_without_retrying():
    """Drafting is one forced reporting call, not a retry loop."""
    fake = FakeChatModel({"some_other_tool": {}})
    with pytest.raises(ModelDidNotCallTool):
        await draft_case_report(
            case_id="CASE-T", firm_name="Kolkheti", findings=[], observations=[],
            dispatch_plan=_PLAN, escalation_round=0, model=fake,
        )


async def test_a_report_with_no_findings_may_have_no_sections():
    """An empty `sections` is only a failure when there was something to
    write about — a clean case has nothing to cite."""
    fake = FakeChatModel({"draft_case_report": {**_DRAFT_ARGS, "sections": []}})
    report = await draft_case_report(
        case_id="CASE-T", firm_name="Kolkheti", findings=[], observations=[],
        dispatch_plan=_PLAN, escalation_round=0, model=fake,
    )
    assert report.sections == []


async def test_cited_ref_numbers_resolve_back_to_real_finding_ids():
    """The model cites numbers; everything downstream still sees real ids."""
    fake = FakeChatModel({"draft_case_report": _DRAFT_ARGS})
    report = await draft_case_report(
        case_id="CASE-T", firm_name="Kolkheti", findings=[_finding()], observations=[],
        dispatch_plan=_PLAN, escalation_round=0, model=fake,
    )
    assert report.sections[0].cited_finding_ids == ["F-1"]


async def test_a_ref_outside_the_range_is_dropped_not_invented():
    """An out-of-range ref cannot become a fabricated id. It is dropped, and
    grounding then reports the finding it stood for as uncited — which is the
    complaint a reviewer should actually see."""
    fake = FakeChatModel({"draft_case_report": {
        **_DRAFT_ARGS,
        "sections": [{"title": "Ghost", "body": "b", "cited_findings": [99], "character": "adverse"}],
    }})
    report = await draft_case_report(
        case_id="CASE-T", firm_name="Kolkheti", findings=[_finding()], observations=[],
        dispatch_plan=_PLAN, escalation_round=0, model=fake,
    )
    assert report.sections[0].cited_finding_ids == []
