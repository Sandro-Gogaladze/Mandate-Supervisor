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
    """An observation is checked against ITS OWN agent's context, so a figure
    only another agent was given is ungrounded here.

    This used to assert that 88.5 was ungrounded against a context holding
    0.885. That is the same number written the way a supervisor reads it,
    and calling it a fabrication is the false positive `_grounded` now
    rules out — so the case is made with a figure nobody was given."""
    obs = Observation(case_id="C", agent="drift", note="New counterparty took 88.5 percent of spend.",
                      cited_evidence="share 0.885")
    (result,) = check_evidence_grounding([], [obs], {"drift": {"share": 0.885}})
    assert result.passed is True, result.unquoted_values

    invented = Observation(case_id="C", agent="drift", note="Spend concentrated at 62.5 percent.",
                           cited_evidence="share 0.885")
    (result,) = check_evidence_grounding([], [invented], {"drift": {"share": 0.885}})
    assert result.passed is False
    assert "62.5" in result.unquoted_values


def test_agent_without_recorded_context_is_skipped_not_judged() -> None:
    a = _assessment(narrative="Cluster of 9999.99.")
    assert check_evidence_grounding([a], [], {}) == []


_PROPORTIONS = {"cap_utilisation_median": 0.915, "settled_share": 0.995,
                "new_payee_share": 0.17396358, "decline_rate": 0.06317}


def test_a_proportion_written_as_a_percentage_is_grounded() -> None:
    """The context holds proportions; a specialist writes percentages, because
    that is how a supervisor reads them. Measured live on Ashgrove, comparing
    the digits alone reported four correct Log claims as fabrications, which
    downgraded them to inconclusive and blocked the case on a judgment gap."""
    a = _assessment(narrative="Median cap utilisation 91.5%, 99.5% settled, "
                              "17.4% new payees, 6.3% declines.")
    (result,) = check_evidence_grounding([a], [], {"log": _PROPORTIONS})
    assert result.passed is True, result.unquoted_values


def test_rounding_to_the_precision_written_is_grounded() -> None:
    a = _assessment(narrative="Cap utilisation ran at 92% of the ceiling.")
    (result,) = check_evidence_grounding([a], [], {"log": _PROPORTIONS})
    assert result.passed is True, result.unquoted_values


def test_a_percentage_the_context_does_not_support_is_still_caught() -> None:
    """The point of the unit tolerance is to stop punishing a correct
    conversion — not to stop checking. 93% is nobody's rounding of 0.915."""
    a = _assessment(narrative="Cap utilisation ran at 93.0% of the ceiling.")
    (result,) = check_evidence_grounding([a], [], {"log": _PROPORTIONS})
    assert result.passed is False
    assert result.unquoted_values == ["93.0"]


def test_precision_beyond_the_context_is_still_caught() -> None:
    a = _assessment(narrative="Median cap utilisation was exactly 91.53%.")
    (result,) = check_evidence_grounding([a], [], {"log": _PROPORTIONS})
    assert result.passed is False
    assert result.unquoted_values == ["91.53"]


def test_a_comma_separated_list_is_not_one_grouped_number() -> None:
    """`5261,5499,5651` is four MCC codes, not 526,154,995,651.

    The old pattern treated any comma between digits as a thousands
    separator, so KYA writing `retail codes (5261,5499,5651)` was reported as
    quoting a twelve-digit figure that appears nowhere in its evidence — a
    correct assessment failed for punctuation."""
    a = _assessment(agent="kya", rule_id="KYA-REG-03",
                    narrative="Activity fits: retail codes (5261,5499,5651) and nothing else.")
    (result,) = check_evidence_grounding([a], [], {"kya": {"mccs": [5261, 5499, 5651]}})
    assert result.passed is True, result.unquoted_values


def test_real_grouped_thousands_still_read_as_one_number() -> None:
    a = _assessment(narrative="Settled 1,748.10 against the threshold 3000.0.")
    (result,) = check_evidence_grounding([a], [], {"log": {"settled": 1748.10, "threshold": 3000.0}})
    assert result.passed is True, result.unquoted_values
