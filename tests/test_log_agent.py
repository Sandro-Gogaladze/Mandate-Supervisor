"""Log's deterministic statistics, on the real dossier."""
from __future__ import annotations

from agents.log import LogAgent
from agents.log_stats import amount_stats, counterparty_breakdown, structuring_clusters, to_dataframe, velocity_stats
from registry.loader import load_log_ruleset
from tests.corpus import thin


def test_candidate_clusters_are_same_counterparty_runs_within_the_window(kst) -> None:
    df = to_dataframe(kst.transaction_history)
    clusters = [c for c in structuring_clusters(df, window_hours=24.0) if len(c["transaction_ids"]) >= 2]
    for c in clusters:
        assert len({c["counterparty_id"]}) == 1
        assert c["sum"] == round(sum(c["amounts"]), 2)


def test_counterparty_breakdown_shares_sum_to_one(kst) -> None:
    assert abs(sum(row["share"] for row in counterparty_breakdown(to_dataframe(kst.transaction_history))) - 1.0) < 1e-9


def test_amount_stats_matches_manual_computation(kst) -> None:
    stats = amount_stats(to_dataframe(kst.transaction_history))
    assert stats["total"] == round(sum(t.amount for t in kst.transaction_history), 2)
    assert stats["count"] == 102 and stats["max"] == 867.0


def test_velocity_stats_on_both_dossiers(kst, hal) -> None:
    for d in (kst, hal):
        assert velocity_stats(to_dataframe(d.transaction_history))["min_gap_hours"] is not None


def test_the_floor_is_one_measurement_per_judged_rule_plus_shared_statistics(kst) -> None:
    facts = LogAgent().run(kst, load_log_ruleset())
    by_id = {f.fact_id.split(":", 1)[1]: f for f in facts}
    assert set(by_id) == {"LOG-STR-01#candidate_clusters", "LOG-CON-01#counterparty_breakdown",
                          "LOG-CON-01#new_payee_share", "LOG-VEL-01#velocity",
                          "log#amount_stats", "log#hourly_distribution"}
    assert by_id["LOG-STR-01#candidate_clusters"].values["reporting_flag_threshold"] == 1000.0  # consumer_shopping dial


def test_the_new_payee_measurement_is_f55s_signal(kst, hal) -> None:
    """A brand-new recipient suddenly getting most of the money: the share
    of the latest month, and whether the register first saw the payee inside
    the window, in front of the judge with the dial it is judged against."""
    for d, share in ((kst, 51.6), (hal, 83.0)):
        f = next(f for f in LogAgent().run(d, load_log_ruleset()) if f.fact_id.endswith("#new_payee_share"))
        top = f.values["counterparties"][0]
        assert (top["counterparty_id"], top["share_pct"], top["new_in_window"]) == ("MER-QVC-8801", share, True)
        assert f.values["latest_month"] == "2026-08" and f.values["new_payee_min_share_pct"] == 20.0
        assert "Quickvale" in f.statement and "inside the review window" in f.statement


def test_no_history_is_an_honest_absence(kst) -> None:
    facts = LogAgent().run(thin(kst, 0), load_log_ruleset())
    assert len(facts) == 3 and {f.absent_reason for f in facts} == {"insufficient_history"}
