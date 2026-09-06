"""Where sweeps are kept, and how two of them are compared.

Its own SQLite file, deliberately **not** the case ledger. The ledger is the
audit trail of real supervision; a sandbox experiment is not that, and mixing
them would let a rehearsal look like a decision. The one sandbox act that
*is* supervision — promoting a rulebook — goes on the ledger, and nothing
else does.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from pathlib import Path

from schemas import (
    Flip,
    RuleDelta,
    Sweep,
    SweepComparison,
    SweepPins,
    SweepResult,
)

# Overridable exactly as the ledger's path is (ledger/store.py), so a
# container can put both SQLite files on one writable volume instead of
# inside the image, where they would not survive the container.
DEFAULT_PATH = Path(
    os.environ.get(
        "MANDATE_SANDBOX_PATH",
        Path(__file__).resolve().parent.parent / "data" / "sandbox.db",
    )
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS sweeps (
  sweep_id   TEXT PRIMARY KEY,
  domain     TEXT NOT NULL,
  started_at TEXT NOT NULL,
  payload    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sweeps_by_domain ON sweeps(domain, started_at);
"""


class SweepStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or DEFAULT_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def save(self, sweep: Sweep) -> Sweep:
        with self._lock, self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO sweeps VALUES (?, ?, ?, ?)",
                         (sweep.sweep_id, sweep.domain, sweep.started_at,
                          json.dumps(sweep.model_dump(mode="json"))))
        return sweep

    def get(self, sweep_id: str) -> Sweep | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM sweeps WHERE sweep_id = ?",
                               (sweep_id,)).fetchone()
        return Sweep.model_validate(json.loads(row["payload"])) if row else None

    def list(self, domain: str | None = None, limit: int = 50) -> list[Sweep]:
        sql = "SELECT payload FROM sweeps"
        args: list = []
        if domain:
            sql += " WHERE domain = ?"
            args.append(domain)
        sql += " ORDER BY started_at DESC LIMIT ?"
        args.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [Sweep.model_validate(json.loads(r["payload"])) for r in rows]

    def latest_for(self, ruleset_ref: str) -> Sweep | None:
        return next((s for s in self.list(limit=200) if s.ruleset_ref == ruleset_ref), None)


def new_sweep_id() -> str:
    return f"swp-{uuid.uuid4().hex[:10]}"


def _keys(result: SweepResult) -> tuple[set, set]:
    """(caught, missed) as comparable (dossier, run, failure) triples."""
    missed = {(m.dossier_id, m.run_ref, m.failure) for m in result.missed}
    # `overall.tp` counts the caught ones; reconstruct them from per-rule hits
    # is unnecessary — caught = labelled minus missed, and `missed` carries
    # every labelled item the sweep did not detect.
    return missed, {(u.dossier_id, u.run_ref, u.failure) for u in result.unexpected}


def compare(base: Sweep, candidate: Sweep) -> SweepComparison:
    """What changed. A rulebook is judged by its deltas, not its absolutes.

    Two sweeps are comparable exactly when everything except the rulebook
    matches — same corpus, same code, same mode. Comparing across a corpus
    change would attribute the data's difference to the policy.
    """
    reason = _incomparable(base.pins, candidate.pins)
    if reason or base.result is None or candidate.result is None:
        return SweepComparison(base=base, candidate=candidate, comparable=False,
                               incomparable_reason=reason or "a sweep has no result")

    base_missed, base_fp = _keys(base.result)
    cand_missed, cand_fp = _keys(candidate.result)

    flips = [
        *[Flip(dossier_id=k[0], run_ref=k[1], failure=k[2], direction="caught")
          for k in sorted(base_missed - cand_missed, key=str)],
        *[Flip(dossier_id=k[0], run_ref=k[1], failure=k[2], direction="lost")
          for k in sorted(cand_missed - base_missed, key=str)],
        *[Flip(dossier_id=k[0], run_ref=k[1], failure=k[2], direction="new_false_positive")
          for k in sorted(cand_fp - base_fp, key=str)],
        *[Flip(dossier_id=k[0], run_ref=k[1], failure=k[2], direction="fixed_false_positive")
          for k in sorted(base_fp - cand_fp, key=str)],
    ]

    deltas = []
    for rule_id in sorted(set(base.result.per_rule) | set(candidate.result.per_rule)):
        b = base.result.per_rule.get(rule_id)
        a = candidate.result.per_rule.get(rule_id)
        if b is None or a is None or b.model_dump() != a.model_dump():
            deltas.append(RuleDelta(rule_id=rule_id, before=b, after=a))

    before_outcomes = {d.dossier_id: d for d in base.result.dossiers}
    changes = []
    for after in candidate.result.dossiers:
        before = before_outcomes.get(after.dossier_id)
        if before and before.actual != after.actual:
            changes.append({"dossier_id": after.dossier_id, "before": before.actual,
                            "after": after.actual, "expected": after.expected,
                            "now_correct": after.correct})

    return SweepComparison(base=base, candidate=candidate, comparable=True,
                           flips=flips, rule_deltas=deltas, dossier_changes=changes)


def _incomparable(a: SweepPins, b: SweepPins) -> str | None:
    if a.corpus_digest != b.corpus_digest:
        return "different corpus — the labelled data changed between these sweeps"
    if a.mode != b.mode:
        return f"different mode — {a.mode} vs {b.mode}"
    if a.code_revision != b.code_revision:
        return f"different code revision — {a.code_revision} vs {b.code_revision}"
    return None
