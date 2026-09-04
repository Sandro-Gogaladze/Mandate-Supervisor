"""Getting dossiers INTO the ledger.

A dossier enters supervision as a `case_submitted` event carrying the whole
submission — dossier.json as filed, every run, the institution's ledger, and
a registry-resolved `firm` block (ingestion/normalize.py::submission_payload).
That makes the ledger self-contained and replayable: delete data/dossiers/
and every past run still verifies. It is also what lets the triage graph read
the submission by case id instead of trusting a client-supplied path.

The loader verified the run index against the file digests before anything
was appended; the hash chain vouches for the payload from then on.
"""
from __future__ import annotations

import json
from data.canonical import canonical_bytes

from data.dossier_loader import list_dossiers, load_for_pipeline
from ingestion.normalize import submission_payload
from schemas.dossier import LoadedDossier

from .store import LedgerStore


def submit_dossier(store: LedgerStore, loaded: LoadedDossier, *, actor: str = "system:seed") -> str:
    payload = submission_payload(loaded)
    artifacts = {}
    for run in payload.pop("runs"):
        rid = run["run_id"]
        content = loaded.run_file_bytes.get(rid)
        if content is None or json.loads(content) != run:
            content = canonical_bytes(run, exclude_keys=())
        artifacts[rid] = store.put_artifact(content)
    payload["run_artifacts"] = artifacts
    store.append(case_id=payload["case_id"], event_type="dossier_submitted", payload=payload, actor=actor)
    return payload["case_id"]


def seed_corpus(store: LedgerStore) -> list[str]:
    """Every corpus dossier that isn't in the ledger yet gets submitted —
    without its ground truth, which the pipeline path never opens. Boot-time
    idempotent: re-running against a populated ledger appends nothing."""
    seeded = []
    for path in list_dossiers():
        loaded = load_for_pipeline(path)
        if not store.has_case(loaded.dossier.dossier_id):
            submit_dossier(store, loaded)
            seeded.append(loaded.dossier.dossier_id)
    return seeded


def latest_submission(store: LedgerStore, case_id: str) -> dict:
    """The submission payload from the most recent case_submitted event — an
    institution can resubmit corrected data, and triage always reads the
    latest."""
    submissions = [e for e in store.events_for(case_id) if e.event_type in ("case_submitted", "dossier_submitted")]
    if not submissions:
        raise ValueError(
            f"case {case_id!r} has no case_submitted event in the ledger — nothing to triage"
        )
    payload = dict(submissions[-1].payload)
    if "run_artifacts" in payload:
        payload["runs"] = [json.loads(store.artifact(digest)) for digest in payload["run_artifacts"].values()]
    return payload
