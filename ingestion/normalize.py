"""Normalization into the internal schema — PLAN item 3, third/fourth bullets.

`normalize_case()` is what the rest of the pipeline (Orchestrator, PLAN
item 4+) will actually call: it verifies a submission and always returns an
`IngestedCase` — a pipeline-ready `CaseBundle` (label/narrative stripped)
plus whatever `Finding`s verification produced. A broken chain or a bad
signature shows up as a non-empty `findings` list, never an exception —
that's what "graceful handling of a broken chain" means concretely.

A schema-invalid submission is a different failure class (garbage that
can't be normalized at all, not a flagged-but-processable one) and still
raises `CaseLoadError` from `data.loader` — ingestion doesn't swallow that.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from data.loader import DATA_DIR, load_case_for_pipeline, load_manifest, load_raw_case_json
from ingestion.verify import VerificationContext, build_verification_context, verify_case
from schemas import CaseBundle, Finding


@dataclass
class IngestedCase:
    case: CaseBundle
    findings: list[Finding] = field(default_factory=list)
    # The raw (QA-note-including) case dict — kept so a specialist agent can
    # re-verify against an arbitrary ruleset later (e.g. policy sandbox mode,
    # PLAN item 14, evaluating a draft ruleset instead of the active one).
    # Cryptographic verification must run against this, not `case`, which
    # has been stripped for pipeline consumption — see ingestion/verify.py.
    raw: dict = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        return not self.findings


def normalize_case(path: Path | str, context: VerificationContext | None = None) -> IngestedCase:
    context = context or build_verification_context()
    raw = load_raw_case_json(path)
    findings = verify_case(raw, context)
    case = load_case_for_pipeline(path)
    return IngestedCase(case=case, findings=findings, raw=raw)


def normalize_case_payload(raw: dict, context: VerificationContext | None = None) -> IngestedCase:
    """Same as normalize_case(), but from an in-memory raw dict — what the
    triage graph uses now that the bundle comes out of the ledger's
    case_submitted event rather than a filesystem path (architecture-v2
    §14.1; closes the client-controlled-path read the old case_path had).
    Cryptographic verification still runs against the raw dict — the QA
    notes were part of what was signed."""
    from pydantic import ValidationError

    from data.loader import CaseLoadError, strip_qa_notes
    from schemas import CaseBundle

    context = context or build_verification_context()
    findings = verify_case(raw, context)
    try:
        case = CaseBundle.model_validate(strip_qa_notes(raw))
    except ValidationError as exc:
        raise CaseLoadError(f"submitted case failed schema validation:\n{exc}") from exc
    case = case.model_copy(update={"label": None, "narrative": None})
    return IngestedCase(case=case, findings=findings, raw=raw)


def normalize_corpus() -> list[IngestedCase]:
    """Every case in data/corpus_manifest.json, ingested. Builds the
    verification context once and reuses it across all cases."""
    context = build_verification_context()
    return [normalize_case(DATA_DIR / entry["file"], context) for entry in load_manifest()]
