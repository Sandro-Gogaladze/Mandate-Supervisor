"""Stage 1 — the ledger core (docs/architecture-v2.md §10)."""
from __future__ import annotations

import json
import sqlite3
import threading

import pytest

from ledger import GENESIS_HASH, LedgerStore


@pytest.fixture
def store(tmp_path) -> LedgerStore:
    return LedgerStore(tmp_path / "ledger.db")


def _submit(store: LedgerStore, case_id: str = "CASE-T-001", **kw):
    defaults = dict(
        case_id=case_id, event_type="case_submitted",
        payload={"case_id": case_id, "firm": {"name": "Test Firm"}},
        actor="system:seed",
    )
    defaults.update(kw)
    return store.append(**defaults)


def test_append_read_round_trip(store) -> None:
    e1 = _submit(store)
    e2 = store.append(
        case_id="CASE-T-001", event_type="case_opened", payload={},
        actor="human:Ana Dvaladze", run_id=None,
    )
    events = store.events_for("CASE-T-001")
    assert [e.seq for e in events] == [1, 2]
    assert events[0].payload == e1.payload
    assert events[0].prev_hash == GENESIS_HASH
    assert events[1].prev_hash == e1.hash
    assert events[1].actor == "human:Ana Dvaladze"
    assert e2.recorded_at  # stamped by the store


def test_chain_verifies_clean(store) -> None:
    _submit(store)
    for i in range(5):
        store.append(
            case_id="CASE-T-001", event_type="observation_recorded",
            payload={"case_id": "CASE-T-001", "agent": "log", "note": f"n{i}", "cited_evidence": "e"},
            actor="agent:log", run_id="run-1",
        )
    assert store.verify() == []


def test_tampered_payload_fails_verify(store) -> None:
    _submit(store)
    _submit(store, event_type="case_opened", payload={}, actor="human:Ana")
    # Reach the DB behind the store's back, with the triggers dropped —
    # simulating an attacker with direct file access.
    conn = sqlite3.connect(store.path)
    conn.execute("DROP TRIGGER events_no_update")
    conn.execute(
        "UPDATE events SET payload = ? WHERE seq = 1",
        (json.dumps({"case_id": "CASE-T-001", "firm": {"name": "Innocent Firm"}}),),
    )
    conn.commit()
    conn.close()
    problems = store.verify()
    assert any("hash does not recompute" in p for p in problems)


def test_deleted_event_fails_verify(store) -> None:
    _submit(store)
    _submit(store, event_type="case_opened", payload={}, actor="human:Ana")
    _submit(store, event_type="case_closed", payload={"reason": "test"}, actor="human:Ana")
    conn = sqlite3.connect(store.path)
    conn.execute("DROP TRIGGER events_no_delete")
    conn.execute("DELETE FROM events WHERE seq = 2")
    conn.commit()
    conn.close()
    problems = store.verify()
    assert any("seq gap" in p for p in problems) or any("prev_hash" in p for p in problems)


def test_update_and_delete_raise_via_triggers(store) -> None:
    _submit(store)
    conn = sqlite3.connect(store.path)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE events SET actor = 'human:mallory' WHERE seq = 1")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM events WHERE seq = 1")
    conn.close()


def test_store_exposes_no_update_or_delete() -> None:
    mutators = [n for n in dir(LedgerStore) if "update" in n.lower() or "delete" in n.lower()]
    assert mutators == []


def test_unknown_event_type_rejected(store) -> None:
    with pytest.raises(ValueError, match="unknown event_type"):
        store.append(case_id="C", event_type="case_edited", payload={}, actor="system:x")


def test_threaded_appends_do_not_fork_the_chain(tmp_path) -> None:
    """Two store instances on the same file, hammered from 8 threads — the
    real shape of a LangGraph fan-out where four specialist nodes finish at
    once. The chain must come out linear and intact."""
    path = tmp_path / "ledger.db"
    stores = [LedgerStore(path), LedgerStore(path)]
    errors: list[Exception] = []

    def work(i: int) -> None:
        try:
            for j in range(10):
                stores[i % 2].append(
                    case_id=f"CASE-{i}", event_type="observation_recorded",
                    payload={"case_id": f"CASE-{i}", "agent": "log", "note": f"{i}-{j}", "cited_evidence": "e"},
                    actor="agent:log", run_id=f"run-{i}",
                )
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    events = stores[0].all_events()
    assert len(events) == 80
    assert [e.seq for e in events] == list(range(1, 81))
    assert stores[0].verify() == []


def test_jsonl_export_round_trips(store) -> None:
    _submit(store)
    _submit(store, case_id="CASE-T-002")
    lines = list(store.export_jsonl())
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert [p["seq"] for p in parsed] == [1, 2]
    only_one = list(store.export_jsonl("CASE-T-002"))
    assert len(only_one) == 1
    assert json.loads(only_one[0])["case_id"] == "CASE-T-002"


def test_actor_prefix_enforced() -> None:
    from ledger.events import LedgerEvent

    with pytest.raises(ValueError, match="actor"):
        LedgerEvent(
            seq=1, case_id="C", run_id=None, event_type="case_opened",
            payload={}, actor="mallory", recorded_at="t", prev_hash="p", hash="h",
        )


def test_events_for_run_filters(store) -> None:
    _submit(store)
    store.append(case_id="CASE-T-001", event_type="run_started",
                 payload={"run_id": "r1", "kind": "triage"}, actor="system:triage", run_id="r1")
    store.append(case_id="CASE-T-001", event_type="run_started",
                 payload={"run_id": "r2", "kind": "triage"}, actor="system:triage", run_id="r2")
    assert [e.run_id for e in store.events_for_run("r1")] == ["r1"]
    assert store.all_case_ids() == ["CASE-T-001"]
