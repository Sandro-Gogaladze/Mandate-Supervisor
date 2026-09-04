"""Drift's judged verdict becomes an assessment citing the baseline measurement."""
from __future__ import annotations

import pytest

from agents.drift import DriftAgent
from agents.drift_reasoning import analyze_drift
from agents.llm import ModelDidNotCallTool, message_text
from registry.loader import load_drift_ruleset
from schemas import Observation
from tests.fakes import FakeChatModel


def _rule():
    return next(r for r in load_drift_ruleset().rules if r.type == "behavioral_drift_detected")


_CLEAN = {"drift": {"anomalous": False, "explanation": "n/a", "cited_evidence": "n/a",
                    "transaction_ids": [], "onset_event_ref": None}, "other_observations": []}


async def test_clean_judgement_is_a_clear_assessment(kst) -> None:
    facts = DriftAgent().run(kst, load_drift_ruleset())
    (a,), observations = await analyze_drift(kst, facts, _rule(), model=FakeChatModel({"record_drift_analysis": _CLEAN}))
    assert a.verdict == "clear" and not a.scores
    assert a.fact_ids == [facts[0].fact_id] and observations == []


async def test_drift_judged_present_is_a_breach(kst) -> None:
    result = {"drift": {"anomalous": True, "explanation": "Counterparty mix PSI 1.1608 is a major shift.",
                        "cited_evidence": "psi 1.1608", "transaction_ids": ["TXN-KST-0045"],
                        "onset_event_ref": "MER-QVC-8801"}, "other_observations": []}
    (a,), _ = await analyze_drift(kst, DriftAgent().run(kst, load_drift_ruleset()), _rule(),
                                  model=FakeChatModel({"record_drift_analysis": result}))
    assert a.verdict == "breach" and a.weighted() == pytest.approx(0.6 * 0.7)


async def test_other_observations_and_addenda(kst) -> None:
    result = {**_CLEAN, "other_observations": [{"note": "New MCC entered in August.", "cited_evidence": "mcc mix"}]}
    fake = FakeChatModel({"record_drift_analysis": result})
    prior = [Observation(case_id="DOSSIER-KST-2026-001", agent="drift", note="earlier note", cited_evidence="x")]
    _, observations = await analyze_drift(kst, DriftAgent().run(kst, load_drift_ruleset()), _rule(),
                                          model=fake, prior_observations=prior, reviewer_directive="Check August.")
    assert [o.note for o in observations] == ["New MCC entered in August."]
    system = message_text(fake.last_messages_for("record_drift_analysis")[0])
    assert "earlier note" in system and "Check August." in system


async def test_the_onset_lands_on_a_logged_event_and_never_an_invented_one(kst) -> None:
    """F65: 'something specific changed it'. A valid ref becomes the
    assessment's subject and an evidence ref; an invented one is dropped."""
    facts = DriftAgent().run(kst, load_drift_ruleset())
    assert [c["ref"] for c in facts[0].values["change_points"] if c["evaluable"]][-1] == "MER-QVC-8801"

    def verdict(ref):
        return FakeChatModel({"record_drift_analysis": {"drift": {
            "anomalous": True, "explanation": "Counterparty mix PSI 6.3423 after the onboarding.",
            "cited_evidence": "psi 6.3423", "transaction_ids": ["TXN-KST-0045"],
            "onset_event_ref": ref}, "other_observations": []}})

    (a,), _ = await analyze_drift(kst, facts, _rule(), model=verdict("MER-QVC-8801"))
    assert a.subject == "MER-QVC-8801" and [r.ref for r in a.evidence_refs] == ["change_log[MER-QVC-8801]", "TXN-KST-0045"]
    assert a.run_refs == ["RUN-2026-0813-0045"] and a.failure_ids == ["F65"]
    assert "Onset: MER-QVC-8801 (merchant_onboarded, 2026-08-05)" in a.narrative
    (a,), _ = await analyze_drift(kst, facts, _rule(), model=verdict("an-event-nobody-logged"))
    assert a.subject == "psi 6.3423" and [r.ref for r in a.evidence_refs] == ["TXN-KST-0045"]
    assert a.failure_ids == [] and "Onset" not in a.narrative


async def test_model_that_does_not_call_the_tool_is_a_clear_error(kst) -> None:
    with pytest.raises(ModelDidNotCallTool):
        await analyze_drift(kst, [], _rule(), model=FakeChatModel({}))
