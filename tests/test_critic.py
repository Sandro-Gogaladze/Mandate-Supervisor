"""The deterministic critic, unit level. Graph-level behaviour (events,
wiring) is covered in test_triage_run.py."""
from __future__ import annotations

from agents.critic import check_evidence_grounding
from schemas import Assessment, Observation


def _assessment(agent="log", narrative="", rule_id="LOG-STR-01", **over):
    return Assessment(**{
        "assessment_id": "A-1", "case_id": "C", "agent": agent, "rule_id": rule_id,
        "fact_ids": ["C:LOG-STR-01#candidate_clusters"], "verdict": "breach",
        "confidence": "probable", "severity_floor": 0.85, "severity_assessed": 0.85,
        "narrative": narrative, **over,
    })


CONTEXT = {"amounts": [2900.0, 2850.0, 2950.0], "threshold": 3000.0, "psi": 5.86}


def test_invented_amount_is_caught() -> None:
    a = _assessment(narrative="Cluster of 2900.0 and 7777.77 exceeds the threshold 3000.0.")
    (result,) = check_evidence_grounding([a], [], {"log": CONTEXT})
    assert result.passed is False
    assert result.unquoted_values == ["7777.77"]
    assert result.sources == ["A-1"]


def test_real_values_and_small_counts_pass() -> None:
    # "3 payments" is model phrasing, not evidence — small integers are not checked
    a = _assessment(narrative="3 payments of 2900.0, 2850.0 and 2950.0, PSI 5.86, under 3000.0.")
    (result,) = check_evidence_grounding([a], [], {"log": CONTEXT})
    assert result.passed is True


def test_deterministic_floor_assessments_are_out_of_scope() -> None:
    # a mandate cap assessment quotes the facts, not a dispatch context — never checked
    a = _assessment(agent="mandate", rule_id="MND-CAP-01",
                    fact_ids=["C:MND-CAP-01:RUN-1"], narrative="Cart total 2150.0 exceeds cap 500.0.")
    results = check_evidence_grounding([a], [], {"mandate": {"unrelated": True}})
    assert results == []  # nothing checkable → no vacuous verdict


def test_mandates_semantic_judgement_is_checked() -> None:
    a = _assessment(agent="mandate", rule_id="MND-SEM-01", fact_ids=["C:MND-SEM-01#intent_vs_cart:RUN-1"],
                    narrative="The cart totals 4444.44, far from what was asked.")
    (result,) = check_evidence_grounding([a], [], {"mandate": {"cart_total": 329.0}})
    assert result.passed is False and "4444.44" in result.unquoted_values


def test_observations_are_checked_against_their_agents_context() -> None:
    obs = Observation(case_id="C", agent="drift", note="New counterparty took 88.5 percent of spend.",
                      cited_evidence="share 0.885")
    (result,) = check_evidence_grounding([], [obs], {"drift": {"share": 0.885}})
    assert result.passed is False  # 88.5 is not in the evidence (0.885 is)
    assert "88.5" in result.unquoted_values


def test_agent_without_recorded_context_is_skipped_not_judged() -> None:
    a = _assessment(narrative="Cluster of 9999.99.")
    assert check_evidence_grounding([a], [], {}) == []
