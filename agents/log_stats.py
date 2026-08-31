"""Deterministic pandas statistics over a case's transaction_history.

Nothing here is a Finding by itself — these are reusable, reproducible
aggregates that both the deterministic structuring rule
(agents/log_checks.py) and the LLM anomaly analysis
(agents/log_reasoning.py) read from, rather than each recomputing its own
version. The LLM only ever reasons over numbers computed here, never over
the raw transaction list unfiltered — "pandas statistics... [with]
narration/judgment of already-computed numbers" (CLAUDE.md), not the LLM
doing its own ad hoc arithmetic.
"""
from __future__ import annotations

import pandas as pd

from schemas import TransactionLogEntry


def to_dataframe(transactions: list[TransactionLogEntry]) -> pd.DataFrame:
    df = pd.DataFrame([t.model_dump() for t in transactions])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False)
    return df.sort_values("timestamp").reset_index(drop=True)


def counterparty_breakdown(df: pd.DataFrame) -> list[dict]:
    """Per-counterparty count/total/share of total spend, sorted by share
    descending — the input the concentration check reasons over."""
    total = df["amount"].sum()
    grouped = df.groupby(["counterparty_id", "counterparty_name"], as_index=False).agg(
        count=("amount", "size"), total=("amount", "sum")
    )
    grouped["share"] = grouped["total"] / total
    grouped = grouped.sort_values("share", ascending=False)
    return grouped.to_dict(orient="records")


def structuring_clusters(df: pd.DataFrame, *, window_hours: float) -> list[dict]:
    """Every maximal run of same-counterparty transactions where each
    consecutive pair is within `window_hours` of each other — candidate
    clusters, not yet filtered by threshold/size (agents/log_checks.py
    does that). One cluster can be a single transaction; callers filter
    on size."""
    clusters: list[dict] = []
    for (cp_id, cp_name), group in df.groupby(["counterparty_id", "counterparty_name"]):
        group = group.sort_values("timestamp")
        gaps_hours = group["timestamp"].diff().dt.total_seconds() / 3600.0
        # a new cluster starts wherever the gap exceeds the window (or at the first row)
        new_cluster = (gaps_hours > window_hours) | gaps_hours.isna()
        cluster_id = new_cluster.cumsum()
        for _, cluster_rows in group.groupby(cluster_id):
            clusters.append({
                "counterparty_id": cp_id,
                "counterparty_name": cp_name,
                "transaction_ids": cluster_rows["transaction_id"].tolist(),
                "amounts": cluster_rows["amount"].tolist(),
                "sum": float(cluster_rows["amount"].sum()),
                "first_timestamp": cluster_rows["timestamp"].min().isoformat(),
                "last_timestamp": cluster_rows["timestamp"].max().isoformat(),
            })
    return clusters


def velocity_stats(df: pd.DataFrame) -> dict:
    """Inter-transaction gap distribution (all transactions, not
    per-counterparty) — evidence for the velocity-anomaly check."""
    gaps_hours = df["timestamp"].diff().dt.total_seconds().dropna() / 3600.0
    if gaps_hours.empty:
        return {"min_gap_hours": None, "median_gap_hours": None, "gaps_under_1_hour": 0}
    return {
        "min_gap_hours": round(float(gaps_hours.min()), 3),
        "median_gap_hours": round(float(gaps_hours.median()), 2),
        "gaps_under_1_hour": int((gaps_hours < 1.0).sum()),
    }


def amount_stats(df: pd.DataFrame) -> dict:
    amounts = df["amount"]
    return {
        "count": int(len(amounts)),
        "total": round(float(amounts.sum()), 2),
        "mean": round(float(amounts.mean()), 2),
        "median": round(float(amounts.median()), 2),
        "std": round(float(amounts.std()), 2) if len(amounts) > 1 else 0.0,
        "min": round(float(amounts.min()), 2),
        "max": round(float(amounts.max()), 2),
        "round_number_count": int((amounts % 100 == 0).sum()),
    }


def hourly_distribution(df: pd.DataFrame) -> dict:
    hours = df["timestamp"].dt.hour
    return {str(h): int(c) for h, c in hours.value_counts().sort_index().items()}
