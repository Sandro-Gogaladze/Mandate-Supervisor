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

# What a sweep measured, lifted out of the payload so it can be queried.
# `latest_for` used to answer "has this version been swept?" by reading the
# most recent 200 sweeps and filtering in Python, which was both a scan and a
# horizon: this store is meant to accumulate — a live sweep costs six minutes
# and nothing here is ever deleted — so the 201st sweep would have started
# hiding older scorecards from the version graph.
MIGRATIONS = (
    ("ruleset_ref", "ALTER TABLE sweeps ADD COLUMN ruleset_ref TEXT"),
    ("ruleset_digest", "ALTER TABLE sweeps ADD COLUMN ruleset_digest TEXT"),
    # The two modes never compare with each other, so "the scorecard this
    # version has" is only answerable per mode.
    ("mode", "ALTER TABLE sweeps ADD COLUMN mode TEXT"),
)


class SweepStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or DEFAULT_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Add the queryable columns and backfill them from stored payloads.

        Backfill rather than re-run: every sweep already in this file cost
        minutes to produce, and the values are right there in its JSON.
        """
        have = {row["name"] for row in conn.execute("PRAGMA table_info(sweeps)")}
        missing = [(column, ddl) for column, ddl in MIGRATIONS if column not in have]
        if not missing:
            return
        for _, ddl in missing:
            conn.execute(ddl)
        for row in conn.execute("SELECT sweep_id, payload FROM sweeps").fetchall():
            payload = json.loads(row["payload"])
            conn.execute("UPDATE sweeps SET ruleset_ref = ?, ruleset_digest = ?, mode = ? "
                         "WHERE sweep_id = ?",
                         (payload.get("ruleset_ref"), payload.get("ruleset_digest"),
                          payload.get("pins", {}).get("mode"), row["sweep_id"]))

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def save(self, sweep: Sweep) -> Sweep:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sweeps "
                "(sweep_id, domain, started_at, payload, ruleset_ref, ruleset_digest, mode) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (sweep.sweep_id, sweep.domain, sweep.started_at,
                 json.dumps(sweep.model_dump(mode="json")),
                 sweep.ruleset_ref, sweep.ruleset_digest, sweep.pins.mode))
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

    def latest_for(self, ruleset_ref: str, digest: str | None = None,
                   mode: str | None = None) -> Sweep | None:
        """The most recent sweep of this version — optionally of this exact
        rulebook, and in this mode.

        A version graph that says "swept" on the strength of a scorecard taken
        before the last edit is worse than saying nothing. And since a
        mechanical sweep refuses to compare against a live one, the mode an
        officer is working in is the only one whose scorecards are of any use
        to them.
        """
        sql = "SELECT payload FROM sweeps WHERE ruleset_ref = ?"
        args: list = [ruleset_ref]
        if digest is not None:
            sql += " AND ruleset_digest = ?"
            args.append(digest)
        if mode is not None:
            sql += " AND mode = ?"
            args.append(mode)
        sql += " ORDER BY started_at DESC LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(sql, args).fetchone()
        return Sweep.model_validate(json.loads(row["payload"])) if row else None

    def equivalent(self, *, ruleset_ref: str, ruleset_digest: str,
                   pins: SweepPins) -> Sweep | None:
        """A finished sweep that would answer this question identically.

        Same version, same rulebook bytes, same corpus, same policy, same
        engine, same mode: re-running it can only reproduce it (mechanically)
        or add model noise to it (live). Either way the officer already paid
        for this answer once.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM sweeps WHERE ruleset_ref = ? AND ruleset_digest = ? "
                "ORDER BY started_at DESC", (ruleset_ref, ruleset_digest)).fetchall()
        for row in rows:
            sweep = Sweep.model_validate(json.loads(row["payload"]))
            if sweep.result is not None and not sweep.error and sweep.pins == pins:
                return sweep
        return None


def new_sweep_id() -> str:
    return f"swp-{uuid.uuid4().hex[:10]}"


def _keys(result: SweepResult) -> tuple[set, set]:
    """(missed, unsupported) as comparable (dossier, run, failure) triples.

    These are the two sides a flip is made of: a labelled defect this rulebook
    let through, and a claim it made that the corpus does not carry.
    """
    return ({(m.dossier_id, m.run_ref, m.failure) for m in result.missed},
            {(u.dossier_id, u.run_ref, u.failure) for u in result.unexpected})


def compare(base: Sweep, candidate: Sweep) -> SweepComparison:
    """What changed. A rulebook is judged by its deltas, not its absolutes.

    Two sweeps are comparable exactly when everything except the rulebook
    matches — same corpus, same policy, same engine, same mode. Comparing
    across any of those would attribute their difference to the rulebook.
    """
    reason = incomparable_reason(base.pins, candidate.pins)
    if reason or base.result is None or candidate.result is None:
        return SweepComparison(base=base, candidate=candidate, comparable=False,
                               incomparable_reason=reason or "a sweep has no result")

    base_missed, base_fp = _keys(base.result)
    cand_missed, cand_fp = _keys(candidate.result)

    # Failures only a model-judged rule can establish. Those flip between two
    # runs of the SAME rulebook, so they are marked and kept out of the
    # verdict rather than being read as this draft's doing.
    judged = set(base.result.model_judged_failures) | set(candidate.result.model_judged_failures)

    def flip(key: tuple, direction: str) -> Flip:
        return Flip(dossier_id=key[0], run_ref=key[1], failure=key[2],
                    direction=direction, judged=key[2] in judged)

    flips = [
        *[flip(k, "caught") for k in sorted(base_missed - cand_missed, key=str)],
        *[flip(k, "lost") for k in sorted(cand_missed - base_missed, key=str)],
        *[flip(k, "new_false_positive") for k in sorted(cand_fp - base_fp, key=str)],
        *[flip(k, "fixed_false_positive") for k in sorted(base_fp - cand_fp, key=str)],
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


def incomparable_reason(a: SweepPins, b: SweepPins) -> str | None:
    """Why these two cannot be diffed, in the terms an officer can act on.

    Ordered by how much of the scorecard each one invalidates, and named
    precisely: "different code revision — 096c9ee vs 1786114" told a reader
    that a commit had happened, not that anything they were looking at had
    changed, and the commit usually had not touched the pipeline at all.
    """
    if a.mode != b.mode:
        return (f"different mode — {a.mode} vs {b.mode}. A mechanical sweep never "
                "runs the model-judged rules, so it is scoring a different question")
    if a.corpus_digest != b.corpus_digest:
        return "different corpus — the labelled data changed between these sweeps"
    if not (a.policy_digest and b.policy_digest and a.engine_digest and b.engine_digest):
        return ("one of these sweeps was taken before the sandbox recorded what it "
                "stood on, so there is no way to tell whether the rest of the policy "
                "or the pipeline has moved since — re-sweep it")
    if a.policy_digest != b.policy_digest:
        return ("the rest of the policy moved — another rulebook, the scoring "
                "weights, the failure catalogue or a regulator registry changed "
                "between these sweeps, so the difference is not this draft's")
    if a.engine_digest != b.engine_digest:
        return "the detection pipeline changed — these two scorecards came from different code"
    return None
