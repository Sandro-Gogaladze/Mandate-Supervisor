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


def roundness(df: pd.DataFrame) -> dict:
    """How often the agent pays a suspiciously exact figure.

    A round number is a chosen number. In retail it is rare by construction —
    prices end in .99 — so a run of them says the amount was decided rather
    than quoted. How many is too many depends entirely on what the agent buys,
    which is why LOG-RND-01 is judged: the corpus sits at 3/102 and 2/52, and
    a constant that called either suspicious would call every retail agent
    suspicious too.
    """
    amounts = df["amount"]
    n = len(amounts)
    buckets = {f"multiples_of_{d}": int((amounts % d == 0).sum()) for d in (10, 50, 100, 1000)}
    exact = int((amounts % 1 == 0).sum())
    return {
        "transactions": n,
        "whole_currency_units": exact,
        "whole_currency_rate": round(exact / n, 3) if n else 0.0,
        **buckets,
        "rate_multiples_of_100": round(buckets["multiples_of_100"] / n, 3) if n else 0.0,
    }


def cap_utilisation(df: pd.DataFrame, caps: dict[str, float]) -> dict:
    """How close each payment ran to the authorisation it was drawn on.

    F64 is an agent feeling for its ceiling — but a cap is a budget, and
    spending most of a budget is what a shopping agent is FOR. Measured on the
    corpus the median draw is 0.92 of the cap with 28 of 47 transactions
    inside the top decile, all of it ordinary. So this returns the
    distribution, never a proximity flag: a model shown "median 0.92, one
    transaction at 99%" can see that near-cap is this agent's normal, where a
    model shown "22 transactions near the cap" cannot.
    """
    rows = [(t, caps[t]) for t in df.index if t in caps]
    pairs = [(float(df.loc[t, "amount"]), caps[t]) for t, _ in rows]
    ratios = sorted(round(a / c, 3) for a, c in pairs if c)
    if not ratios:
        return {"evaluable": False, "reason": "no transaction resolves to an authorisation cap"}
    band = lambda lo, hi: sum(1 for r in ratios if lo <= r < hi)  # noqa: E731
    return {
        "evaluable": True,
        "transactions_with_a_cap": len(ratios),
        "median_utilisation": ratios[len(ratios) // 2],
        "max_utilisation": ratios[-1],
        "over_cap": sum(1 for r in ratios if r > 1.0),
        "distribution": {"at_or_over_99pct": band(0.99, 1e9), "95_to_99pct": band(0.95, 0.99),
                         "90_to_95pct": band(0.90, 0.95), "under_90pct": band(0.0, 0.90)},
    }


def hourly_distribution(df: pd.DataFrame) -> dict:
    hours = df["timestamp"].dt.hour
    return {str(h): int(c) for h, c in hours.value_counts().sort_index().items()}


def new_payee_concentration(df: pd.DataFrame, *, merchants: dict[str, dict],
                            window_start: str) -> dict:
    """F55's signal: each counterparty's share of the LATEST month's
    in-window spend, and whether the regulator's merchant register first saw
    it inside the review window. A payee that did not exist a month ago
    holding a share an established supplier took years to earn is the
    supervisable shape; the verdict on it is Log's judgement (LOG-CON-01)."""
    in_window = df[df["run_ref"].notna()] if "run_ref" in df else df.iloc[0:0]
    if in_window.empty:
        return {"latest_month": None, "total": 0.0, "counterparties": []}
    months = in_window["timestamp"].apply(lambda ts: ts.strftime("%Y-%m"))
    latest = months.max()
    recent = in_window[months == latest]
    total = float(recent["amount"].sum()) or 1.0
    start = window_start[:10]
    rows = []
    for cp, group in recent.groupby("counterparty_id"):
        record = merchants.get(cp, {})
        first_seen = record.get("first_seen")
        rows.append({
            "counterparty_id": cp,
            "counterparty_name": str(group["counterparty_name"].iloc[0]),
            "share_pct": round(100.0 * float(group["amount"].sum()) / total, 1),
            "total": round(float(group["amount"].sum()), 2),
            "count": int(len(group)),
            "registry_first_seen": first_seen,
            "new_in_window": bool(first_seen and first_seen >= start),
            "watchlist_flags": list(record.get("watchlist_flags", [])),
        })
    rows.sort(key=lambda r: -r["share_pct"])
    return {"latest_month": latest, "total": round(total, 2), "counterparties": rows}
