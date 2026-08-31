"""Ad hoc case submissions — a supervisor uploading a mandate chain +
transaction history bundle that arrived out of band, rather than only
reviewing the seven pre-loaded synthetic corpus cases (PLAN item 10 UI
follow-up).

Deliberately reuses the exact on-disk shape `data/loader.py` already
knows how to read: an uploaded bundle is validated once here, written to
`data/uploads/<case_id>.json`, and from that point on is indistinguishable
from a corpus case to everything downstream (`ingestion.normalize_case`,
`pipeline.graph.run_case`) — no special-casing needed in the pipeline
itself. A manifest-shaped entry (matching `load_manifest()`'s per-case
dict) is kept alongside so `api/main.py` can merge corpus + uploaded cases
with one code path.

Unlike the corpus, an uploaded case usually has no `label`/`narrative` —
those are eval-only ground truth a real submission never carries (see
schemas/case.py) — and no hand-written one-line `summary`; both are
synthesized here from the bundle's own data so the case queue still has
something to show.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import ValidationError

from data.loader import load_manifest, strip_qa_notes
from schemas import CaseBundle

UPLOADS_DIR = Path(__file__).resolve().parent / "uploads"


class CaseUploadError(ValueError):
    """The uploaded file isn't valid JSON, doesn't match the case schema,
    or reuses a case_id that already exists."""


def _summarize(case: CaseBundle) -> str:
    tx_count = len(case.transaction_history)
    purpose = case.mandate_chain.intent.authorization_scope.purpose_category.replace("_", " ")
    return f"{tx_count} transaction{'s' if tx_count != 1 else ''} · {purpose} · submitted for review"


def _manifest_entry(case: CaseBundle, file_name: str) -> dict:
    return {
        "case_id": case.case_id,
        "file": f"uploads/{file_name}",
        "label": case.label,
        "firm": case.firm.name,
        "summary": case.narrative or _summarize(case),
    }


def list_uploaded_cases() -> list[dict]:
    if not UPLOADS_DIR.exists():
        return []
    entries = []
    for path in sorted(UPLOADS_DIR.glob("*.json")):
        raw = strip_qa_notes(json.loads(path.read_text(encoding="utf-8")))
        try:
            case = CaseBundle.model_validate(raw)
        except ValidationError:
            continue
        entries.append(_manifest_entry(case, path.name))
    return entries


def save_uploaded_case(raw: dict) -> dict:
    """Validates `raw` against the case schema and persists it. Returns a
    manifest-shaped entry (same shape `load_manifest()` yields per case) on
    success; raises `CaseUploadError` with a message safe to show a user
    otherwise.

    Strips the same `_*_note` QA-only annotations `data/loader.py` strips
    from the curated corpus before persisting — without this, re-uploading
    one of the existing sample case files verbatim (the queue's own
    suggested way to try this without a bundle on hand) fails schema
    validation on a field a real submission was never going to carry
    anyway, confirmed live."""
    cleaned = strip_qa_notes(raw)
    try:
        case = CaseBundle.model_validate(cleaned)
    except ValidationError as exc:
        # Pydantic's default str(exc) is multi-line and references internal
        # field paths — fine for a case officer used to reading rejected
        # forms, and far more actionable than a generic "invalid file".
        raise CaseUploadError(f"This file doesn't match the case bundle schema:\n{exc}") from exc

    if not re.fullmatch(r"[A-Za-z0-9._-]+", case.case_id):
        raise CaseUploadError(f"case_id {case.case_id!r} must be a plain identifier (letters, digits, . _ -).")

    existing_ids = {entry["case_id"] for entry in load_manifest()} | {e["case_id"] for e in list_uploaded_cases()}
    if case.case_id in existing_ids:
        raise CaseUploadError(f"A case with id {case.case_id!r} already exists in the queue.")

    UPLOADS_DIR.mkdir(exist_ok=True)
    file_name = f"{case.case_id}.json"
    dest = UPLOADS_DIR / file_name
    dest.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
    return _manifest_entry(case, file_name)
