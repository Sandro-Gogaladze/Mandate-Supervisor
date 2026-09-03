import pytest

# PARKED — migration-plan.md Phase 2/3.
#
# These cover Drift, which is real and still wanted. They are parked because
# their FIXTURE is gone: every one built its case from data/cases/*.json, and
# the corpus is now two dossiers with a different shape.
#
# Parked rather than deleted, and loudly rather than quietly: the logic under
# test did not stop mattering, and a silently shrinking suite is how a
# migration loses coverage nobody notices. Each comes back when the pipeline
# consumes a Dossier and a dossier fixture exists to replace the case one.
pytestmark = pytest.mark.skip(reason="fixture removed with the case corpus — migration Phase 2/3")

from agents.drift import DriftAgent
from agents.drift_stats import amount_shift, distribution_psi, frequency_shift, split_baseline, to_dataframe
from data.loader import DATA_DIR, load_manifest
from ingestion.normalize import normalize_case
from registry.loader import load_drift_ruleset


def test_run_is_always_a_no_op() -> None:
    ruleset = load_drift_ruleset()
    for entry in load_manifest():
        case = normalize_case(DATA_DIR / entry["file"])
        assert DriftAgent().run(case, ruleset) == []
        assert DriftAgent().run(case, None) == []


def test_amount_shift_matches_manual_computation_for_case_006() -> None:
    """case-006's own narrative claims avg ₾182/tx in the baseline period
    climbing to ~₾370 by the end — confirm the baseline/comparison split
    and z-score computation reproduce the real numbers exactly, not just
    that *some* shift is detected."""
    case = normalize_case(DATA_DIR / "cases" / "case-006-drift.json")
    df = to_dataframe(case.case.transaction_history)
    baseline, comparison = split_baseline(df, baseline_window_days=30)
    assert len(baseline) == 14
    assert len(comparison) == 35
    shift = amount_shift(baseline, comparison)
    assert shift["baseline_mean"] == 187.95
    assert shift["comparison_mean"] == 316.51
    assert shift["z_score"] == 7.15


def test_counterparty_and_mcc_psi_for_case_006_are_large() -> None:
    """A brand-new dominant vendor and a brand-new MCC enter the mix after
    the baseline window — PSI should be far past the conventional 0.25
    'major shift' threshold for both."""
    case = normalize_case(DATA_DIR / "cases" / "case-006-drift.json")
    df = to_dataframe(case.case.transaction_history)
    baseline, comparison = split_baseline(df, baseline_window_days=30)
    assert distribution_psi(baseline, comparison, "counterparty_id") > 0.25
    assert distribution_psi(baseline, comparison, "mcc") > 0.25


def test_frequency_shift_does_not_crash_across_corpus() -> None:
    for entry in load_manifest():
        case = normalize_case(DATA_DIR / entry["file"])
        df = to_dataframe(case.case.transaction_history)
        baseline, comparison = split_baseline(df, baseline_window_days=30)
        frequency_shift(baseline, comparison)  # must not raise, even on tiny/empty windows


def test_psi_is_zero_for_identical_distributions() -> None:
    case = normalize_case(DATA_DIR / "cases" / "case-001-compliant.json")
    df = to_dataframe(case.case.transaction_history)
    assert distribution_psi(df, df, "counterparty_id") == 0.0
