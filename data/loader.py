"""Loader/validator for the synthetic corpus.

Two eval-only annotation layers exist in data/cases/*.json that a real
submission will never carry:

- top-level `label` / `narrative` (docs/phases/01-synthetic-data.md §2.7)
- nested `_*_note` fields sprinkled at the exact defect location
  (e.g. `_chain_note`, `_kya_note`) for human QA readability

Both get stripped before a case is validated against the wire schema, so
the schema stays a true model of what ingestion will actually receive.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from schemas import CaseBundle

DATA_DIR = Path(__file__).resolve().parent
CASES_DIR = DATA_DIR / "cases"
MANIFEST_PATH = DATA_DIR / "corpus_manifest.json"


class CaseLoadError(RuntimeError):
    """A case file failed to parse or failed schema validation."""


def strip_qa_notes(value: Any) -> Any:
    """Recursively drop any dict key starting with '_' (QA-only annotations)."""
    if isinstance(value, dict):
        return {
            key: strip_qa_notes(val)
            for key, val in value.items()
            if not key.startswith("_")
        }
    if isinstance(value, list):
        return [strip_qa_notes(item) for item in value]
    return value


def _read_case_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return strip_qa_notes(raw)


def load_raw_case_json(path: Path | str) -> dict:
    """The case file exactly as written on disk — QA notes and all, no
    schema validation. This is what was actually signed (see
    scripts/sign_corpus.py), so cryptographic verification must recompute
    canonical hashes against *this*, not the QA-note-stripped view every
    other loader function returns."""
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def load_labeled_case(path: Path | str) -> CaseBundle:
    """Load a case with its eval-only `label`/`narrative` intact.

    For the eval harness only (PLAN item 16) — never hand this to a pipeline
    node.
    """
    path = Path(path)
    raw = _read_case_json(path)
    try:
        return CaseBundle.model_validate(raw)
    except ValidationError as exc:
        raise CaseLoadError(f"{path.name} failed schema validation:\n{exc}") from exc


def load_case_for_pipeline(path: Path | str) -> CaseBundle:
    """Load a case as the pipeline will actually see it: no label, no narrative."""
    case = load_labeled_case(path)
    return case.model_copy(update={"label": None, "narrative": None})


def load_manifest() -> list[dict]:
    with MANIFEST_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)["cases"]


def iter_corpus_labeled() -> list[tuple[dict, CaseBundle]]:
    """Every (manifest_entry, labeled CaseBundle) pair in the corpus."""
    return [
        (entry, load_labeled_case(DATA_DIR / entry["file"]))
        for entry in load_manifest()
    ]


def validate_corpus() -> list[str]:
    """Validate every case in the manifest against the schema, and cross-check
    case_id/label consistency between the manifest and the case file itself.

    Returns a list of problem descriptions; empty means the corpus is clean.
    """
    problems: list[str] = []
    for entry in load_manifest():
        file_path = DATA_DIR / entry["file"]
        if not file_path.exists():
            problems.append(f"{entry['file']}: manifest references a missing file")
            continue
        try:
            case = load_labeled_case(file_path)
        except CaseLoadError as exc:
            problems.append(str(exc))
            continue
        if case.case_id != entry["case_id"]:
            problems.append(
                f"{entry['file']}: case_id mismatch "
                f"(manifest={entry['case_id']!r}, file={case.case_id!r})"
            )
        if case.label != entry["label"]:
            problems.append(
                f"{entry['file']}: label mismatch "
                f"(manifest={entry['label']!r}, file={case.label!r})"
            )
    return problems
