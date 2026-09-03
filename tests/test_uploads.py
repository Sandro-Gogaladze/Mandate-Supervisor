import pytest

# PARKED — migration-plan.md Phase 2/3.
#
# These cover case upload, which is real and still wanted. They are parked because
# their FIXTURE is gone: every one built its case from data/cases/*.json, and
# the corpus is now two dossiers with a different shape.
#
# Parked rather than deleted, and loudly rather than quietly: the logic under
# test did not stop mattering, and a silently shrinking suite is how a
# migration loses coverage nobody notices. Each comes back when the pipeline
# consumes a Dossier and a dossier fixture exists to replace the case one.
pytestmark = pytest.mark.skip(reason="fixture removed with the case corpus — migration Phase 2/3")

"""data/uploads.py — ad hoc case submissions (PLAN item 10 UI follow-up:
"how is a user supposed to use this, he can't upload a new case")."""
from __future__ import annotations

import json

import pytest

from data import uploads
from data.loader import DATA_DIR, load_raw_case_json


@pytest.fixture(autouse=True)
def _isolated_uploads_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "UPLOADS_DIR", tmp_path / "uploads")
    yield


def _sample_raw(case_id: str = "CASE-UPLOAD-TEST") -> dict:
    """A real corpus file's raw contents, renamed off its corpus case_id —
    most tests here want a submission that doesn't collide with the
    existing queue; test_case_id_colliding_with_corpus_rejected covers the
    case that deliberately doesn't rename it."""
    raw = load_raw_case_json(DATA_DIR / "cases/case-001-compliant.json")
    raw["case_id"] = case_id
    return raw


def test_save_uploaded_case_persists_and_returns_manifest_entry():
    raw = _sample_raw()
    entry = uploads.save_uploaded_case(raw)
    assert entry["case_id"] == raw["case_id"]
    assert entry["firm"] == raw["firm"]["name"]
    assert entry["file"] == f"uploads/{raw['case_id']}.json"
    assert (uploads.UPLOADS_DIR / f"{raw['case_id']}.json").exists()


def test_uploaded_case_appears_in_list():
    raw = _sample_raw()
    uploads.save_uploaded_case(raw)
    listed = uploads.list_uploaded_cases()
    assert [e["case_id"] for e in listed] == [raw["case_id"]]


def test_duplicate_case_id_rejected():
    raw = _sample_raw()
    uploads.save_uploaded_case(raw)
    with pytest.raises(uploads.CaseUploadError, match="already exists"):
        uploads.save_uploaded_case(raw)


def test_case_id_colliding_with_corpus_rejected():
    # Not just a duplicate *upload* — reusing a case_id already in the
    # curated corpus manifest must be rejected too, or the two files would
    # silently shadow each other in the merged case list.
    raw = load_raw_case_json(DATA_DIR / "cases/case-001-compliant.json")
    assert raw["case_id"] == "CASE-2026-001"  # already in data/corpus_manifest.json
    with pytest.raises(uploads.CaseUploadError, match="already exists"):
        uploads.save_uploaded_case(raw)


def test_reuploading_a_sample_case_verbatim_works():
    # The dialog's own suggested workflow: "open any case in the queue and
    # use its data as a template" — but every real corpus file carries
    # QA-only `_*_note` fields at defect locations that the wire schema
    # (extra="forbid") rejects outright. Confirmed live: uploading
    # case-003 unmodified 400'd on `mandate_chain.payment._chain_note`
    # before this was stripped the same way data/loader.py strips it for
    # the corpus itself.
    raw = load_raw_case_json(DATA_DIR / "cases/case-003-broken-chain.json")
    assert any(k.startswith("_") for k in raw["mandate_chain"]["payment"]), (
        "test fixture assumption broken: case-003 no longer carries a QA note here"
    )
    raw["case_id"] = "CASE-UPLOAD-FROM-SAMPLE"
    entry = uploads.save_uploaded_case(raw)
    assert entry["case_id"] == "CASE-UPLOAD-FROM-SAMPLE"


def test_schema_invalid_upload_rejected_with_clear_message():
    with pytest.raises(uploads.CaseUploadError, match="doesn't match the case bundle schema"):
        uploads.save_uploaded_case({"not": "a case bundle"})


def test_unsafe_case_id_rejected():
    raw = _sample_raw()
    raw["case_id"] = "../../etc/passwd"
    with pytest.raises(uploads.CaseUploadError, match="plain identifier"):
        uploads.save_uploaded_case(raw)


def test_summary_synthesized_when_narrative_absent():
    raw = _sample_raw()
    raw["case_id"] = "CASE-UPLOAD-NO-NARRATIVE"
    raw["narrative"] = None
    entry = uploads.save_uploaded_case(raw)
    assert "24 transactions" in entry["summary"]


def test_list_uploaded_cases_empty_when_dir_missing():
    assert uploads.list_uploaded_cases() == []


def test_list_skips_files_that_no_longer_validate(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "UPLOADS_DIR", tmp_path / "uploads")
    uploads.UPLOADS_DIR.mkdir()
    (uploads.UPLOADS_DIR / "broken.json").write_text(json.dumps({"not": "valid"}), encoding="utf-8")
    assert uploads.list_uploaded_cases() == []
