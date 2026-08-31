from agents.log import LogAgent
from agents.log_stats import (
    amount_stats,
    counterparty_breakdown,
    structuring_clusters,
    to_dataframe,
    velocity_stats,
)
from data.loader import DATA_DIR, load_manifest
from ingestion.normalize import normalize_case
from registry.loader import load_log_ruleset


def test_run_is_always_a_no_op() -> None:
    """Log has no deterministic detection at all (revised design — see
    agents/log_reasoning.py module docstring). run() stays Protocol-
    conformant and key-free, same shape as Drift's stub; all real analysis
    only happens through review()."""
    ruleset = load_log_ruleset()
    for entry in load_manifest():
        case = normalize_case(DATA_DIR / entry["file"])
        assert LogAgent().run(case, ruleset) == []
        assert LogAgent().run(case, None) == []


def test_structuring_cluster_matches_case_005_exact_numbers() -> None:
    """case-005's own narrative claims 3 payments (₾2,900/₾2,850/₾2,950,
    summing ₾8,700) to the same counterparty, 17-22 minutes apart — this is
    the candidate-cluster computation the LLM is handed as evidence
    (agents/log_reasoning.py::_structured_view); confirm it's exactly
    right before trusting anything built on top of it."""
    case = normalize_case(DATA_DIR / "cases" / "case-005-structuring.json")
    df = to_dataframe(case.case.transaction_history)
    clusters = [c for c in structuring_clusters(df, window_hours=24.0) if len(c["transaction_ids"]) >= 2]
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster["counterparty_id"] == "MER-GIE-001"
    assert sorted(cluster["amounts"]) == [2850.0, 2900.0, 2950.0]
    assert cluster["sum"] == 8700.0


def test_counterparty_breakdown_shares_sum_to_one() -> None:
    case = normalize_case(DATA_DIR / "cases" / "case-006-drift.json")
    df = to_dataframe(case.case.transaction_history)
    breakdown = counterparty_breakdown(df)
    assert abs(sum(row["share"] for row in breakdown) - 1.0) < 1e-9


def test_amount_stats_matches_manual_computation() -> None:
    case = normalize_case(DATA_DIR / "cases" / "case-001-compliant.json")
    df = to_dataframe(case.case.transaction_history)
    stats = amount_stats(df)
    manual_total = round(sum(t.amount for t in case.case.transaction_history), 2)
    assert stats["total"] == manual_total
    assert stats["count"] == len(case.case.transaction_history)


def test_velocity_stats_does_not_crash_on_real_corpus() -> None:
    for entry in load_manifest():
        case = normalize_case(DATA_DIR / entry["file"])
        df = to_dataframe(case.case.transaction_history)
        stats = velocity_stats(df)
        assert stats["min_gap_hours"] is not None
