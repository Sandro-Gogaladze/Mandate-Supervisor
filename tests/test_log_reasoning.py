from agents.llm import THINKING_EFFORT
from agents.log import LogAgent, LogReview
from agents.log_reasoning import analyze_log
from data.loader import DATA_DIR
from ingestion.normalize import normalize_case
from registry.loader import load_log_ruleset
from schemas import Finding, Observation
from tests.fakes import FakeChatModel


def _rules():
    ruleset = load_log_ruleset()
    structuring = next(r for r in ruleset.rules if r.type == "transaction_structuring_detected")
    concentration = next(r for r in ruleset.rules if r.type == "counterparty_concentration_anomaly")
    velocity = next(r for r in ruleset.rules if r.type == "transaction_velocity_anomaly")
    return structuring, concentration, velocity


_NOT_ANOMALOUS = {"anomalous": False, "explanation": "n/a", "cited_evidence": "n/a"}

_CLEAN_RESULT = {
    "structuring": _NOT_ANOMALOUS,
    "concentration": _NOT_ANOMALOUS,
    "velocity": _NOT_ANOMALOUS,
    "other_observations": [],
}


async def test_no_findings_when_nothing_anomalous() -> None:
    case = normalize_case(DATA_DIR / "cases" / "case-001-compliant.json")
    fake = FakeChatModel({"record_log_analysis": _CLEAN_RESULT})

    findings, observations = await analyze_log(case, *_rules(), model=fake)

    assert findings == []
    assert observations == []


async def test_structuring_finding_when_model_judges_the_cluster_deliberate() -> None:
    case = normalize_case(DATA_DIR / "cases" / "case-005-structuring.json")
    result = {
        **_CLEAN_RESULT,
        "structuring": {
            "anomalous": True,
            "explanation": "3 payments to Guria Import-Export, 17-22 min apart, each under the ₾3,000 threshold, summing to ₾8,700.",
            "cited_evidence": "amounts=[2900.0, 2850.0, 2950.0], sum=8700.0",
        },
    }
    fake = FakeChatModel({"record_log_analysis": result})

    findings, _ = await analyze_log(case, *_rules(), model=fake)

    assert len(findings) == 1
    assert isinstance(findings[0], Finding)
    assert findings[0].rule_id == "LOG-STR-01"
    assert findings[0].agent == "log"


async def test_concentration_finding_when_flagged() -> None:
    case = normalize_case(DATA_DIR / "cases" / "case-005-structuring.json")
    result = {
        **_CLEAN_RESULT,
        "concentration": {
            "anomalous": True,
            "explanation": "48.8% of spend concentrated on Guria Import-Export.",
            "cited_evidence": "share=0.488, count=7 of 16 transactions",
        },
    }
    fake = FakeChatModel({"record_log_analysis": result})

    findings, _ = await analyze_log(case, *_rules(), model=fake)

    assert len(findings) == 1
    assert findings[0].rule_id == "LOG-CON-01"
    assert findings[0].severity_weight == _rules()[1].severity_weight


async def test_all_three_can_fire_together() -> None:
    case = normalize_case(DATA_DIR / "cases" / "case-005-structuring.json")
    anomalous = {"anomalous": True, "explanation": "flagged", "cited_evidence": "x"}
    result = {"structuring": anomalous, "concentration": anomalous, "velocity": anomalous, "other_observations": []}
    fake = FakeChatModel({"record_log_analysis": result})

    findings, _ = await analyze_log(case, *_rules(), model=fake)

    assert {f.rule_id for f in findings} == {"LOG-STR-01", "LOG-CON-01", "LOG-VEL-01"}
    assert len({f.finding_id for f in findings}) == 3  # distinct ids, no collision


async def test_other_observations_become_unscored_observation_objects() -> None:
    case = normalize_case(DATA_DIR / "cases" / "case-006-drift.json")
    result = {
        **_CLEAN_RESULT,
        "other_observations": [
            {"note": "Amounts cluster suspiciously close to round numbers.", "cited_evidence": "round_number_count=9"},
        ],
    }
    fake = FakeChatModel({"record_log_analysis": result})

    findings, observations = await analyze_log(case, *_rules(), model=fake)

    assert findings == []
    assert len(observations) == 1
    assert isinstance(observations[0], Observation)
    assert observations[0].agent == "log"
    assert not hasattr(observations[0], "rule_id")
    assert not hasattr(observations[0], "severity_weight")


async def test_uses_high_thinking_effort_and_auto_tool_choice() -> None:
    case = normalize_case(DATA_DIR / "cases" / "case-001-compliant.json")
    fake = FakeChatModel({"record_log_analysis": _CLEAN_RESULT})

    await analyze_log(case, *_rules(), model=fake)

    assert fake.last_bind_kwargs["tool_choice"] == {"type": "auto"}
    assert fake.last_bind_kwargs["output_config"] == {"effort": THINKING_EFFORT}


async def test_prompt_includes_candidate_clusters_and_threshold() -> None:
    """The model is hardcoded nothing about whether a cluster IS
    structuring — but it must be given the real candidate clusters and the
    real threshold to judge against, or it has nothing to reason from."""
    case = normalize_case(DATA_DIR / "cases" / "case-005-structuring.json")
    fake = FakeChatModel({"record_log_analysis": _CLEAN_RESULT})

    await analyze_log(case, *_rules(), model=fake)

    payload = fake.last_messages[1].content
    assert "candidate_structuring_clusters" in payload
    assert "MER-GIE-001" in payload
    assert "reporting_flag_threshold" in payload
    assert "3000" in payload


async def test_review_returns_all_findings_and_observations_from_one_call() -> None:
    case = normalize_case(DATA_DIR / "cases" / "case-005-structuring.json")
    ruleset = load_log_ruleset()
    result = {
        "structuring": {"anomalous": True, "explanation": "x", "cited_evidence": "x"},
        "concentration": {"anomalous": True, "explanation": "x", "cited_evidence": "x"},
        "velocity": _NOT_ANOMALOUS,
        "other_observations": [{"note": "note", "cited_evidence": "x"}],
    }
    fake = FakeChatModel({"record_log_analysis": result})

    review = await LogAgent().review(case, ruleset, model=fake)

    assert isinstance(review, LogReview)
    assert len(review.findings) == 2
    assert len(review.observations) == 1


async def test_review_without_ruleset_does_not_call_the_model() -> None:
    case = normalize_case(DATA_DIR / "cases" / "case-005-structuring.json")
    fake = FakeChatModel({"record_log_analysis": _CLEAN_RESULT})

    review = await LogAgent().review(case, None, model=fake)

    assert review.findings == []
    assert fake.last_bind_kwargs is None


async def test_empty_transaction_history_short_circuits_without_calling_the_model() -> None:
    case = normalize_case(DATA_DIR / "cases" / "case-001-compliant.json")
    case.case.transaction_history.clear()
    fake = FakeChatModel({"record_log_analysis": _CLEAN_RESULT})

    findings, observations = await analyze_log(case, *_rules(), model=fake)

    assert findings == []
    assert observations == []
    assert fake.last_bind_kwargs is None
