"""Log's judged verdicts become assessments citing the floor's measurements."""
from __future__ import annotations

import pytest

from agents.llm import ModelDidNotCallTool, message_text
from agents.log import LogAgent
from agents.log_reasoning import analyze_log
from registry.loader import load_log_ruleset
from schemas import Observation
from tests.fakes import FakeChatModel


def _rules():
    ruleset = load_log_ruleset()
    by_type = {r.type: r for r in ruleset.rules}
    return (by_type["transaction_structuring_detected"], by_type["counterparty_concentration_anomaly"],
            by_type["transaction_velocity_anomaly"])


_NOT = {"anomalous": False, "explanation": "n/a", "cited_evidence": "n/a", "transaction_ids": []}
_CLEAN = {"structuring": _NOT, "concentration": _NOT, "velocity": _NOT, "other_observations": []}


def _facts(kst):
    return LogAgent().run(kst, load_log_ruleset())


async def test_clean_judgements_are_clear_assessments_citing_measurements(kst) -> None:
    fake = FakeChatModel({"record_log_analysis": _CLEAN})
    assessments, observations = await analyze_log(kst, _facts(kst), *_rules(), model=fake)
    assert [(a.rule_id, a.verdict) for a in assessments] == [
        ("LOG-STR-01", "clear"), ("LOG-CON-01", "clear"), ("LOG-VEL-01", "clear")]
    assert all(not a.scores for a in assessments)
    assert assessments[0].fact_ids == ["DOSSIER-KST-2026-001:LOG-STR-01#candidate_clusters"]
    assert observations == []


async def test_an_anomalous_judgement_is_a_breach_priced_at_the_floor(kst) -> None:
    result = {**_CLEAN, "structuring": {"anomalous": True,
                                        "explanation": "Two same-day payments to one merchant sum past the threshold.",
                                        "cited_evidence": "sum 1240.0",
                                        "transaction_ids": ["TXN-KST-0001"]}}
    assessments, _ = await analyze_log(kst, _facts(kst), *_rules(), model=FakeChatModel({"record_log_analysis": result}))
    a = next(a for a in assessments if a.rule_id == "LOG-STR-01")
    assert a.verdict == "breach" and a.confidence == "probable"
    assert a.severity_floor == a.severity_assessed == 0.85 and a.weighted() == pytest.approx(0.85 * 0.7)
    assert a.subject == "sum 1240.0"
    assert a.run_refs == ["RUN-2026-0616-0001"]
    assert [r.ref for r in a.evidence_refs] == ["TXN-KST-0001"]


async def test_other_observations_are_observations_never_assessments(kst) -> None:
    result = {**_CLEAN, "other_observations": [{"note": "Weekend clustering.", "cited_evidence": "hourly"}]}
    assessments, observations = await analyze_log(kst, _facts(kst), *_rules(), model=FakeChatModel({"record_log_analysis": result}))
    (obs,) = observations
    assert isinstance(obs, Observation) and obs.agent == "log"
    assert len(assessments) == 3


async def test_open_log_pattern_names_candidate_failure_transactions_and_runs(kst) -> None:
    result = {**_CLEAN, "other_observations": [{
        "note": "Round amounts repeat.", "cited_evidence": "TXN-KST-0001",
        "failure_id": "F62", "transaction_ids": ["TXN-KST-0001", "TXN-INVENTED"],
    }]}
    _, observations = await analyze_log(
        kst, _facts(kst), *_rules(), model=FakeChatModel({"record_log_analysis": result})
    )
    (obs,) = observations
    assert obs.failure_id == "F62"
    assert obs.transaction_refs == ["TXN-KST-0001"]
    assert obs.run_refs == ["RUN-2026-0616-0001"]


async def test_anomaly_without_a_valid_transaction_is_not_projectable(kst) -> None:
    result = {**_CLEAN, "velocity": {
        "anomalous": True, "explanation": "fast", "cited_evidence": "invented",
        "transaction_ids": ["TXN-INVENTED"],
    }}
    assessments, _ = await analyze_log(
        kst, _facts(kst), *_rules(), model=FakeChatModel({"record_log_analysis": result})
    )
    a = next(a for a in assessments if a.rule_id == "LOG-VEL-01")
    assert a.verdict == "inconclusive" and a.failure_ids == []


async def test_escalation_and_reviewer_addenda_reach_the_prompt(kst) -> None:
    fake = FakeChatModel({"record_log_analysis": _CLEAN})
    prior = [Observation(case_id="DOSSIER-KST-2026-001", agent="log", note="Weekend clustering.", cited_evidence="h")]
    await analyze_log(kst, _facts(kst), *_rules(), model=fake, prior_observations=prior,
                      reviewer_directive="Look at Saturdays.")
    system = message_text(fake.last_messages_for("record_log_analysis")[0])
    assert "escalation round" in system and "Weekend clustering." in system
    assert "<reviewer_instruction>" in system and "Look at Saturdays." in system


async def test_review_with_no_history_never_calls_the_model(kst) -> None:
    from tests.corpus import thin

    fake = FakeChatModel({"record_log_analysis": _CLEAN})
    review = await LogAgent().review(thin(kst, 0), load_log_ruleset(), model=fake)
    assert fake.call_log == [] and len(review.facts) == 3
    gap, = review.assessments  # the missing history is a data-gap concern, not a verdict
    assert gap.verdict == "concern" and "3 rules" in gap.narrative


async def test_model_that_does_not_call_the_tool_is_a_clear_error(kst) -> None:
    with pytest.raises(ModelDidNotCallTool):
        await analyze_log(kst, _facts(kst), *_rules(), model=FakeChatModel({}))
