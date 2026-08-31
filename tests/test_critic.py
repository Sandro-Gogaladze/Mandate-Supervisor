"""Stage 6 — the deterministic critic (architecture-v2 §15.1), unit level.
Graph-level behavior (events, wiring) is covered in test_triage_run.py."""
from __future__ import annotations

from agents.critic import check_evidence_grounding
from schemas import Finding, Observation


def _finding(agent="log", summary="", details=None, type_="transaction_structuring_detected"):
    return Finding(
        finding_id="F-1", case_id="C", agent=agent, type=type_,
        rule_id="LOG-STR-01", severity_weight=0.85, summary=summary, details=details or {},
    )


CONTEXT = {"amounts": [2900.0, 2850.0, 2950.0], "threshold": 3000.0, "psi": 5.86}


def test_invented_amount_is_caught() -> None:
    finding = _finding(summary="Cluster of 2900.0 and 7777.77 exceeds the threshold 3000.0.")
    (result,) = check_evidence_grounding([finding], [], {"log": CONTEXT})
    assert result.passed is False
    assert result.unquoted_values == ["7777.77"]
    assert result.sources == ["F-1"]


def test_real_values_and_small_counts_pass() -> None:
    # "3 payments" is model phrasing, not evidence — small integers are not checked
    finding = _finding(summary="3 payments of 2900.0, 2850.0 and 2950.0, PSI 5.86, under 3000.0.")
    (result,) = check_evidence_grounding([finding], [], {"log": CONTEXT})
    assert result.passed is True


def test_deterministic_floor_findings_are_out_of_scope() -> None:
    # mandate cap finding quotes the case, not a dispatch context — never checked
    finding = _finding(agent="mandate", type_="per_transaction_cap_exceeded",
                       summary="Cart total 2150.0 exceeds cap 500.0.")
    results = check_evidence_grounding([finding], [], {"mandate": {"unrelated": True}})
    assert results == []  # nothing checkable → no vacuous verdict


def test_observations_are_checked_against_their_agents_context() -> None:
    obs = Observation(case_id="C", agent="drift", note="New counterparty took 88.5 percent of spend.",
                      cited_evidence="share 0.885")
    (result,) = check_evidence_grounding([], [obs], {"drift": {"share": 0.885}})
    assert result.passed is False  # 88.5 is not in the evidence (0.885 is)
    assert "88.5" in result.unquoted_values


def test_agent_without_recorded_context_is_skipped_not_judged() -> None:
    finding = _finding(summary="Cluster of 9999.99.")
    assert check_evidence_grounding([finding], [], {}) == []
