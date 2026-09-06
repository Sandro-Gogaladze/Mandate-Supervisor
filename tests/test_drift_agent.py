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


def test_the_floor_carries_the_split_and_checks_the_baseline_can_bear_it(kst) -> None:
    """Two facts: the split the model judges, and whether the baseline is
    steady enough for that judgement to mean anything."""
    facts = {x.rule_id: x for x in DriftAgent().run(kst, load_drift_ruleset())}
    assert set(facts) == {"DRIFT-BHV-01", "DRIFT-BAS-01"}
    steady = facts["DRIFT-BAS-01"]
    assert steady.kind == "satisfied" and abs(steady.values["amount_z_score"]) <= 2.0
    f = facts["DRIFT-BHV-01"]
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


def test_a_steady_baseline_is_never_flagged_by_mix_churn(kst, hal) -> None:
    """The regression this rule was nearly written with.

    Baseline-half counterparty PSI is 10.3 on Kestrel and 11.7 on Halcyon —
    both far past any conventional threshold, both entirely ordinary, because
    a consumer shopping agent buys from a different merchant almost every run.
    A computable rule cannot weigh that, so it decides on the amount z-score
    alone and must stay quiet on both.
    """
    from agents.drift_stats import baseline_stability, split_baseline, to_dataframe

    for dossier in (kst, hal):
        baseline, _ = split_baseline(to_dataframe(dossier.transaction_history), baseline_window_days=30)
        stats = baseline_stability(baseline)
        assert stats["counterparty_mix_psi"] > 1.0          # the tempting signal, and it is noise
        assert abs(stats["amount_z_score"]) <= 2.0          # the one that means something
    facts = {f.rule_id: f for f in DriftAgent().run(kst, load_drift_ruleset())}
    assert facts["DRIFT-BAS-01"].kind == "satisfied"


async def test_unexplained_drift_is_its_own_finding(kst) -> None:
    """Drift the operator's own record cannot account for is the worse of the
    two findings, and until F89 existed it was the one with no name."""
    from tests.fakes import FakeChatModel

    def build(onset):
        tx = [t.transaction_id for t in kst.transaction_history[-3:]]
        return {"drift": {"anomalous": True, "explanation": "Average size doubled.",
                          "cited_evidence": "z 7.15", "transaction_ids": tx,
                          "onset_event_ref": onset},
                "other_observations": []}

    book = load_drift_ruleset()
    # No logged cause: BHV-01 breaches but establishes no F65; UNX-01 carries F89.
    fake = FakeChatModel({"record_drift_analysis": build(None), "write_narration": {"narration": "n"}})
    review = await DriftAgent().review(kst, book, model=fake)
    by_rule = {a.rule_id: a for a in review.assessments}
    assert by_rule["DRIFT-BHV-01"].verdict == "breach" and by_rule["DRIFT-BHV-01"].failure_ids == []
    assert by_rule["DRIFT-UNX-01"].verdict == "breach" and by_rule["DRIFT-UNX-01"].failure_ids == ["F89"]

    # A logged cause: F65 is established, and the shift is not unexplained.
    fake = FakeChatModel({"record_drift_analysis": build("MER-QVC-8801"), "write_narration": {"narration": "n"}})
    review = await DriftAgent().review(kst, book, model=fake)
    by_rule = {a.rule_id: a for a in review.assessments}
    assert by_rule["DRIFT-BHV-01"].failure_ids == ["F65"]
    assert by_rule["DRIFT-UNX-01"].verdict == "clear" and not by_rule["DRIFT-UNX-01"].scores
