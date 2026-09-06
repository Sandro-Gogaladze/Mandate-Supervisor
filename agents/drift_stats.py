"""Deterministic statistics for Drift — same split as agents/log_stats.py:
pure arithmetic an LLM would do unreliably itself (PSI, z-scores, per-week
frequency across dozens of rows), never a verdict. Nothing here decides
whether a shift counts as "drift"; agents/drift_reasoning.py's LLM call
does, given these numbers as evidence.
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from agents.log_stats import to_dataframe  # shared — same conversion, no reason to duplicate

__all__ = ["to_dataframe", "split_baseline", "distribution_psi", "amount_shift", "frequency_shift", "mix_breakdown", "change_points"]


def split_baseline(df: pd.DataFrame, *, baseline_window_days: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Everything within `baseline_window_days` of the first transaction is
    the baseline; everything after is the comparison window being checked
    against it."""
    start = df["timestamp"].min()
    cutoff = start + timedelta(days=baseline_window_days)
    baseline = df[df["timestamp"] < cutoff]
    comparison = df[df["timestamp"] >= cutoff]
    return baseline, comparison


def distribution_psi(baseline: pd.DataFrame, comparison: pd.DataFrame, column: str) -> float:
    """Population Stability Index between the baseline and comparison
    window's distribution over `column` (e.g. counterparty_id, mcc).
    Conventionally: <0.1 no significant shift, 0.1-0.25 moderate, >0.25 major."""
    if baseline.empty or comparison.empty:
        return 0.0
    categories = set(baseline[column]) | set(comparison[column])
    eps = 1e-4
    total = 0.0
    for category in categories:
        base_pct = max((baseline[column] == category).sum() / len(baseline), eps)
        comp_pct = max((comparison[column] == category).sum() / len(comparison), eps)
        total += (comp_pct - base_pct) * np.log(comp_pct / base_pct)
    return round(float(total), 4)


def amount_shift(baseline: pd.DataFrame, comparison: pd.DataFrame) -> dict:
    baseline_mean = float(baseline["amount"].mean())
    baseline_std = float(baseline["amount"].std()) if len(baseline) > 1 else 0.0
    comparison_mean = float(comparison["amount"].mean())
    z_score = (comparison_mean - baseline_mean) / baseline_std if baseline_std > 0 else None
    return {
        "baseline_mean": round(baseline_mean, 2),
        "baseline_std": round(baseline_std, 2),
        "comparison_mean": round(comparison_mean, 2),
        "comparison_std": round(float(comparison["amount"].std()), 2) if len(comparison) > 1 else 0.0,
        "z_score": round(z_score, 2) if z_score is not None else None,
    }


def frequency_shift(baseline: pd.DataFrame, comparison: pd.DataFrame) -> dict:
    def per_week(window: pd.DataFrame) -> float | None:
        span_days = (window["timestamp"].max() - window["timestamp"].min()).days
        if span_days <= 0:
            return None
        return round(len(window) / (span_days / 7), 2)

    return {"baseline_per_week": per_week(baseline), "comparison_per_week": per_week(comparison)}


def mix_breakdown(df: pd.DataFrame, column: str) -> dict:
    return df[column].value_counts().to_dict()


def baseline_stability(baseline: pd.DataFrame) -> dict:
    """Is the baseline itself steady enough to be a baseline?

    Every drift verdict is a comparison against the first window, so if the
    agent was already changing *during* that window the comparison measures
    nothing. Split the baseline in half and run the same statistics across the
    halves: a baseline that fails its own drift test cannot support a finding
    about what came after.

    Deliberately arithmetic, not judgement. This does not ask whether the
    agent misbehaved — that must never turn on a constant — it asks whether
    the evidence can carry the question at all, which is the same family as
    `min_total_transactions` and is rightly decided in code.

    Only the amount z-score is offered as a decidable signal. The mix PSIs are
    computed and returned for context, but a rule must NOT decide on them: a
    consumer shopping agent buys from a different merchant almost every run,
    so PSI between two halves of its own history is enormous whatever it does
    — measured at 10.3 and 11.7 on the two corpus baselines, both of which are
    ordinary. On a high-cardinality category with ten samples a side, PSI
    measures sparsity, not instability. Weighing that is exactly the judgement
    DRIFT-BHV-01 hands to a model; a computable rule cannot make it.
    """
    if len(baseline) < 4:
        return {"evaluable": False, "reason": "fewer than 4 baseline transactions to split",
                "baseline_transactions": len(baseline)}
    ordered = baseline.sort_values("timestamp")
    half = len(ordered) // 2
    first, second = ordered.iloc[:half], ordered.iloc[half:]
    amounts = amount_shift(first, second)
    return {
        "evaluable": True,
        "baseline_transactions": len(baseline),
        "first_half": len(first),
        "second_half": len(second),
        "counterparty_mix_psi": distribution_psi(first, second, "counterparty_id"),
        "mcc_mix_psi": distribution_psi(first, second, "mcc"),
        "amount_z_score": amounts["z_score"],
        "first_half_mean": amounts["baseline_mean"],
        "second_half_mean": amounts["comparison_mean"],
    }


def change_points(df: pd.DataFrame, events: list[dict]) -> list[dict]:
    """The baseline statistics evaluated BEFORE and AFTER each dated
    `change_log` event — what lets an onset land on a named event rather than
    a date (F65). Each event gets the same numbers the baseline split gets;
    an event with too little history on one side is reported with
    `evaluable: False` rather than skipped, so the model can see it was
    considered."""
    out = []
    for event in events:
        at = pd.Timestamp(event["at"])
        ts = df["timestamp"]
        if ts.dt.tz is not None and at.tzinfo is None:
            at = at.tz_localize(ts.dt.tz)
        elif ts.dt.tz is None and at.tzinfo is not None:
            at = at.tz_convert(None)
        before, after = df[ts < at], df[ts >= at]
        row = {"ref": event["ref"], "kind": event["kind"], "at": event["at"],
               "before_count": int(len(before)), "after_count": int(len(after)),
               "evaluable": len(before) >= 2 and len(after) >= 2}
        if row["evaluable"]:
            row.update({
                "amount_shift": amount_shift(before, after),
                "frequency_shift": frequency_shift(before, after),
                "counterparty_mix_psi": distribution_psi(before, after, "counterparty_id"),
                "mcc_mix_psi": distribution_psi(before, after, "mcc"),
                "new_counterparties_after": sorted(set(after["counterparty_id"]) - set(before["counterparty_id"])),
            })
        out.append(row)
    return out
