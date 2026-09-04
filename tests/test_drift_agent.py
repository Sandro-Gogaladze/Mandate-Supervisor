"""Drift's deterministic statistics, on the real dossier."""
from __future__ import annotations

from agents.drift import DriftAgent
from agents.drift_stats import amount_shift, distribution_psi, frequency_shift, split_baseline, to_dataframe
from registry.loader import load_drift_ruleset
from tests.corpus import thin


def test_baseline_split_covers_the_whole_history(kst) -> None:
    df = to_dataframe(kst.transaction_history)
    baseline, comparison = split_baseline(df, baseline_window_days=30)
    assert len(baseline) + len(comparison) == 102 and len(baseline) == 21
    shift = amount_shift(baseline, comparison)
    assert shift["baseline_mean"] == 208.24 and shift["z_score"] == -0.09


def test_psi_is_zero_for_identical_distributions(kst) -> None:
    df = to_dataframe(kst.transaction_history)
    assert distribution_psi(df, df, "counterparty_id") == 0.0


def test_frequency_shift_does_not_crash_on_thin_windows(kst) -> None:
    df = to_dataframe(thin(kst, 3).transaction_history)
    frequency_shift(*split_baseline(df, baseline_window_days=30))


def test_the_floor_is_one_measurement_carrying_the_split(kst) -> None:
    f, = DriftAgent().run(kst, load_drift_ruleset())
    assert f.kind == "measurement" and f.values["counterparty_mix_psi"] == 1.1608
    strongest = max((c for c in f.values["change_points"] if c["evaluable"]),
                    key=lambda c: c["counterparty_mix_psi"])
    assert strongest["ref"] == "MER-QVC-8801" and strongest["kind"] == "merchant_onboarded"
    assert "MER-QVC-8801" in f.statement  # the onset the floor already points at


async def test_review_below_the_minimum_declines_without_the_model(kst) -> None:
    review = await DriftAgent().review(thin(kst, 20), load_drift_ruleset())
    assert review.insufficient_baseline is True
    assert [a.verdict for a in review.assessments] == ["concern"]  # the data gap, not a drift verdict
    f, = review.facts
    assert f.absent_reason == "insufficient_history" and f.values["min_total_transactions"] == 30
