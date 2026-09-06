"""The case ledger — SQLite, append-only, hash-chained (architecture-v2 §10).

The primary tamper control is that this class exposes **no update and no
delete method at all**; the SQL triggers are defence in depth for anything
that reaches the database by another route.

Hashing reuses data/canonical.py::payload_hash — the same canonical
serialization that signs the mandate corpus. One definition of "the bytes of
this object" across signing and chaining; no second implementation to drift.

The chain is global across all cases (prev_hash links by seq, not per-case),
so a deleted or reordered event anywhere breaks verification everywhere —
the stronger property for an audit record.

Appends serialize: a per-path process lock plus BEGIN IMMEDIATE, with
MAX(seq) re-read inside the transaction. Four specialist nodes finishing
simultaneously in a LangGraph fan-out is the real concurrent case and must
not fork the chain.
"""
from __future__ import annotations

import json
import hashlib
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from data.canonical import payload_hash

from .events import EVENT_TYPES, LedgerEvent

GENESIS_HASH = "sha256:" + "0" * 64

# Runtime data, not source — gitignored, sits next to the corpus it records.
LEDGER_PATH = Path(
    os.environ.get(
        "MANDATE_LEDGER_PATH",
        Path(__file__).resolve().parent.parent / "data" / "ledger.db",
    )
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (digest TEXT PRIMARY KEY, content BLOB NOT NULL);
CREATE TRIGGER IF NOT EXISTS artifacts_no_update BEFORE UPDATE ON artifacts
BEGIN SELECT RAISE(ABORT, 'artifacts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS artifacts_no_delete BEFORE DELETE ON artifacts
BEGIN SELECT RAISE(ABORT, 'artifacts are immutable'); END;
CREATE TABLE IF NOT EXISTS events (
  seq          INTEGER PRIMARY KEY,
  case_id      TEXT NOT NULL,
  run_id       TEXT,
  event_type   TEXT NOT NULL,
  payload      TEXT NOT NULL,
  actor        TEXT NOT NULL,
  recorded_at  TEXT NOT NULL,
  prev_hash    TEXT NOT NULL,
  hash         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_by_case ON events(case_id, seq);
CREATE INDEX IF NOT EXISTS events_by_run  ON events(run_id, seq);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
"""

# One lock per database path, shared across every LedgerStore instance in
# the process — two stores opened on the same file must still serialize.
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path)
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


def event_hash(
    *,
    seq: int,
    case_id: str,
    run_id: str | None,
    event_type: str,
    payload: dict,
    actor: str,
    recorded_at: str,
    prev_hash: str,
    run_ref: str | None = None,
) -> str:
    return payload_hash(
        {
            **({"run_ref": run_ref} if run_ref else {}),
            "seq": seq,
            "case_id": case_id,
            "run_id": run_id,
            "event_type": event_type,
            "payload": payload,
            "actor": actor,
            "recorded_at": recorded_at,
            "prev_hash": prev_hash,
        },
        exclude_keys=(),
    )


def _row_to_event(row: sqlite3.Row) -> LedgerEvent:
    return LedgerEvent(
        seq=row["seq"],
        case_id=row["case_id"],
        run_id=row["run_id"],
        run_ref=row["run_ref"],
        event_type=row["event_type"],
        payload=json.loads(row["payload"]),
        actor=row["actor"],
        recorded_at=row["recorded_at"],
        prev_hash=row["prev_hash"],
        hash=row["hash"],
    )


class LedgerStore:
    def __init__(self, path: Path | str = LEDGER_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = _lock_for(self.path)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            if "run_ref" not in {r[1] for r in conn.execute("PRAGMA table_info(events)")}:
                conn.execute("ALTER TABLE events ADD COLUMN run_ref TEXT")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    # -- write ------------------------------------------------------------

    def append(
        self,
        *,
        case_id: str,
        event_type: str,
        payload: dict,
        actor: str,
        run_id: str | None = None,
        run_ref: str | None = None,
    ) -> LedgerEvent:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event_type {event_type!r}")
        recorded_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT seq, hash FROM events ORDER BY seq DESC LIMIT 1"
                ).fetchone()
                seq = (row["seq"] + 1) if row else 1
                prev_hash = row["hash"] if row else GENESIS_HASH
                digest = event_hash(
                    seq=seq, case_id=case_id, run_id=run_id, event_type=event_type,
                    payload=payload, actor=actor, recorded_at=recorded_at,
                    prev_hash=prev_hash, run_ref=run_ref,
                )
                conn.execute(
                    "INSERT INTO events (seq, case_id, run_id, event_type, payload,"
                    " actor, recorded_at, prev_hash, hash, run_ref)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        seq, case_id, run_id, event_type,
                        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
                        actor, recorded_at, prev_hash, digest, run_ref,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return LedgerEvent(
            seq=seq, case_id=case_id, run_id=run_id, event_type=event_type,
            payload=payload, actor=actor, recorded_at=recorded_at,
            prev_hash=prev_hash, hash=digest, run_ref=run_ref,
        )

    def put_artifact(self, content: bytes) -> str:
        digest = 'sha256:' + hashlib.sha256(content).hexdigest()
        with self._lock, self._connect() as conn:
            conn.execute('INSERT OR IGNORE INTO artifacts VALUES (?, ?)', (digest, content))
        return digest

    def artifact(self, digest: str) -> bytes:
        with self._connect() as conn:
            row = conn.execute('SELECT content FROM artifacts WHERE digest=?', (digest,)).fetchone()
        if row is None: raise ValueError(f'Missing run artifact {digest}')
        content = bytes(row[0])
        if 'sha256:' + hashlib.sha256(content).hexdigest() != digest:
            raise ValueError(f'Artifact digest mismatch: {digest}')
        return content

    # -- read -------------------------------------------------------------

    def events_for(self, case_id: str) -> list[LedgerEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE case_id = ? ORDER BY seq", (case_id,)
            ).fetchall()
        return [_row_to_event(r) for r in rows]

    def events_for_run(self, run_id: str) -> list[LedgerEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE run_id = ? ORDER BY seq", (run_id,)
            ).fetchall()
        return [_row_to_event(r) for r in rows]

    def all_events(self) -> list[LedgerEvent]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM events ORDER BY seq").fetchall()
        return [_row_to_event(r) for r in rows]

    def all_case_ids(self) -> list[str]:
        """Dossier case ids, in first-seen order so the queue is stable.

        Not every stream on this ledger is a case. Registry governance shares
        it on purpose — a ruleset promotion is written under `registry:<domain>`
        (sandbox/service.py) precisely so it is hash-chained and auditable like
        everything else. Those ids are not dossiers, and projecting them as
        cases put a phantom "unknown" firm in the queue and in every
        cross-dossier sweep. A dossier id never contains ':'; a namespaced one
        always does. `all_stream_ids()` still returns everything, and `verify()`
        walks all_events(), so the chain itself is untouched by this filter."""
        return [cid for cid in self.all_stream_ids() if ":" not in cid]

    def all_stream_ids(self) -> list[str]:
        """Every stream on the ledger, cases and non-case namespaces alike."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT case_id, MIN(seq) AS first_seq FROM events"
                " GROUP BY case_id ORDER BY first_seq"
            ).fetchall()
        return [r["case_id"] for r in rows]

    def has_case(self, case_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM events WHERE case_id = ? LIMIT 1", (case_id,)
            ).fetchone()
        return row is not None

    # -- integrity --------------------------------------------------------

    def verify(self) -> list[str]:
        """Recomputes every hash and checks every link. [] means intact."""
        problems: list[str] = []
        prev_hash = GENESIS_HASH
        expected_seq = 1
        for event in self.all_events():
            if event.seq != expected_seq:
                problems.append(
                    f"seq gap: expected {expected_seq}, found {event.seq} — "
                    f"an event was deleted or reordered"
                )
                expected_seq = event.seq
            if event.prev_hash != prev_hash:
                problems.append(
                    f"event {event.seq}: prev_hash does not match event {event.seq - 1}'s hash"
                )
            recomputed = event_hash(
                seq=event.seq, case_id=event.case_id, run_id=event.run_id,
                event_type=event.event_type, payload=event.payload,
                actor=event.actor, recorded_at=event.recorded_at,
                prev_hash=event.prev_hash, run_ref=event.run_ref,
            )
            if recomputed != event.hash:
                problems.append(f"event {event.seq}: hash does not recompute — payload altered")
            basis = event.payload.get('review_basis', {})
            digests = [*event.payload.get('run_artifacts', {}).values(), *basis.get('rulebook_artifacts', {}).values()]
            if basis.get('policy_artifact'): digests.append(basis['policy_artifact'])
            for digest in digests:
                try:
                    self.artifact(digest)
                except ValueError as exc:
                    problems.append(f"event {event.seq}: {exc}")
            prev_hash = event.hash
            expected_seq += 1
        return problems

    # -- export -----------------------------------------------------------

    def export_jsonl(self, case_id: str | None = None) -> Iterator[str]:
        events = self.events_for(case_id) if case_id else self.all_events()
        for event in events:
            yield json.dumps(event.model_dump(), sort_keys=True, ensure_ascii=True)


_DEFAULT_STORE: LedgerStore | None = None


def get_default_store() -> LedgerStore:
    """Process-wide store at LEDGER_PATH. Everything that doesn't inject its
    own store (tests do; the API and graphs may) shares this one."""
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = LedgerStore()
    return _DEFAULT_STORE
