from agents.drift import DriftAgent, DriftReview
from agents.drift_reasoning import analyze_drift
from agents.llm import THINKING_EFFORT
from data.loader import DATA_DIR
from ingestion.normalize import normalize_case
from registry.loader import load_drift_ruleset
from schemas import Finding, Observation
from tests.fakes import FakeChatModel


def _rule():
    ruleset = load_drift_ruleset()
    return next(r for r in ruleset.rules if r.type == "behavioral_drift_detected")


_CLEAN_RESULT = {
    "drift": {"anomalous": False, "explanation": "n/a", "cited_evidence": "n/a"},
    "other_observations": [],
}


async def test_no_finding_when_not_anomalous() -> None:
    case = normalize_case(DATA_DIR / "cases" / "case-006-drift.json")
    fake = FakeChatModel({"record_drift_analysis": _CLEAN_RESULT})

    findings, observations = await analyze_drift(case, _rule(), model=fake)

    assert findings == []
    assert observations == []


async def test_finding_when_model_judges_drift_present() -> None:
    case = normalize_case(DATA_DIR / "cases" / "case-006-drift.json")
    result = {
        "drift": {
            "anomalous": True,
            "explanation": "Average transaction size grew from ₾187.95 to ₾316.51 (z=7.15), with a new vendor and category dominating the mix.",
            "cited_evidence": "z_score=7.15, counterparty_mix_psi=5.86, mcc_mix_psi=2.02",
        },
        "other_observations": [],
    }
    fake = FakeChatModel({"record_drift_analysis": result})

    findings, _ = await analyze_drift(case, _rule(), model=fake)

    assert len(findings) == 1
    assert isinstance(findings[0], Finding)
    assert findings[0].agent == "drift"
    assert findings[0].rule_id == "DRIFT-BHV-01"
    assert findings[0].severity_weight == _rule().severity_weight


async def test_other_observations_become_unscored_observation_objects() -> None:
    case = normalize_case(DATA_DIR / "cases" / "case-006-drift.json")
    result = {
        **_CLEAN_RESULT,
        "other_observations": [
            {"note": "New vendor Batumi Express Freight might warrant its own KYA look.", "cited_evidence": "17 of 35 comparison-window transactions"},
        ],
    }
    fake = FakeChatModel({"record_drift_analysis": result})

    findings, observations = await analyze_drift(case, _rule(), model=fake)

    assert findings == []
    assert len(observations) == 1
    assert isinstance(observations[0], Observation)
    assert observations[0].agent == "drift"
    assert not hasattr(observations[0], "rule_id")


async def test_uses_high_thinking_effort_and_auto_tool_choice() -> None:
    case = normalize_case(DATA_DIR / "cases" / "case-006-drift.json")
    fake = FakeChatModel({"record_drift_analysis": _CLEAN_RESULT})

    await analyze_drift(case, _rule(), model=fake)

    assert fake.last_bind_kwargs["tool_choice"] == {"type": "auto"}
    assert fake.last_bind_kwargs["output_config"] == {"effort": THINKING_EFFORT}


async def test_prompt_includes_real_psi_and_zscore_numbers() -> None:
    case = normalize_case(DATA_DIR / "cases" / "case-006-drift.json")
    fake = FakeChatModel({"record_drift_analysis": _CLEAN_RESULT})

    await analyze_drift(case, _rule(), model=fake)

    payload = fake.last_messages[1].content
    assert "counterparty_mix_psi" in payload
    assert "z_score" in payload
    assert "7.15" in payload


async def test_review_flags_insufficient_baseline_below_min_transactions() -> None:
    """case-007 has only 7 transactions, far under the 30-tx minimum —
    review() must report insufficient_baseline without calling the model
    at all, not attempt a judgment on a meaningless sample."""
    case = normalize_case(DATA_DIR / "cases" / "case-007-prompt-injection.json")
    ruleset = load_drift_ruleset()
    fake = FakeChatModel({"record_drift_analysis": _CLEAN_RESULT})

    review = await DriftAgent().review(case, ruleset, model=fake)

    assert isinstance(review, DriftReview)
    assert review.insufficient_baseline is True
    assert review.findings == []
    assert fake.last_bind_kwargs is None  # never called


async def test_review_runs_full_analysis_when_sufficient_history() -> None:
    """case-006 has 49 transactions — comfortably over the 30-tx floor."""
    case = normalize_case(DATA_DIR / "cases" / "case-006-drift.json")
    ruleset = load_drift_ruleset()
    result = {
        "drift": {"anomalous": True, "explanation": "flagged", "cited_evidence": "x"},
        "other_observations": [],
    }
    fake = FakeChatModel({"record_drift_analysis": result})

    review = await DriftAgent().review(case, ruleset, model=fake)

    assert review.insufficient_baseline is False
    assert len(review.findings) == 1


async def test_review_without_ruleset_does_not_call_the_model() -> None:
    case = normalize_case(DATA_DIR / "cases" / "case-006-drift.json")
    fake = FakeChatModel({"record_drift_analysis": _CLEAN_RESULT})

    review = await DriftAgent().review(case, None, model=fake)

    assert review.findings == []
    assert fake.last_bind_kwargs is None
