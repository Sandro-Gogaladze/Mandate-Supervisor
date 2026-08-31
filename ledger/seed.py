"""Getting cases INTO the ledger.

A case enters supervision as a `case_submitted` event carrying the full raw
bundle — QA notes and all, since that is what was cryptographically signed.
That makes the ledger self-contained and replayable: delete data/cases/ and
every past run still verifies. It is also what lets the triage graph read
the bundle by case_id instead of trusting a client-supplied filesystem path.
"""
from __future__ import annotations

from data.loader import DATA_DIR, load_manifest, load_raw_case_json

from .store import LedgerStore


def submit_case(store: LedgerStore, raw: dict, *, actor: str = "system:seed") -> str:
    case_id = raw["case_id"]
    store.append(case_id=case_id, event_type="case_submitted", payload=raw, actor=actor)
    return case_id


def seed_corpus(store: LedgerStore) -> list[str]:
    """Every corpus case that isn't in the ledger yet gets submitted. Boot-time
    idempotent: re-running against a populated ledger appends nothing."""
    seeded = []
    for entry in load_manifest():
        raw = load_raw_case_json(DATA_DIR / entry["file"])
        if not store.has_case(raw["case_id"]):
            submit_case(store, raw)
            seeded.append(raw["case_id"])
    return seeded


def latest_submission(store: LedgerStore, case_id: str) -> dict:
    """The raw bundle from the most recent case_submitted event — a firm can
    resubmit corrected data, and triage always reads the latest."""
    submissions = [
        e for e in store.events_for(case_id) if e.event_type == "case_submitted"
    ]
    if not submissions:
        raise ValueError(
            f"case {case_id!r} has no case_submitted event in the ledger — "
            f"nothing to triage"
        )
    return submissions[-1].payload
