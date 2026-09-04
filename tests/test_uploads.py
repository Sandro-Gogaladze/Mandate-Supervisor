"""data/uploads.py — a dossier directory as a zip, verified at the door."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from data import uploads
from tests.corpus import HAL, KST


@pytest.fixture(autouse=True)
def _isolated_uploads_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "UPLOADS_DIR", tmp_path / "uploads")
    yield


def _zip_of(directory: Path, *, folder: str | None = None, include_ground_truth: bool = False,
            mutate=None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path in sorted(directory.rglob("*.json")):
            rel = path.relative_to(directory)
            if rel.name == "ground_truth.json" and not include_ground_truth:
                continue
            data = path.read_bytes()
            if mutate:
                data = mutate(rel, data)
            zf.writestr(f"{folder}/{rel}" if folder else str(rel), data)
    return buf.getvalue()


def test_a_dossier_zip_is_verified_and_persisted():
    loaded = uploads.save_uploaded_dossier(_zip_of(KST))
    assert loaded.dossier.dossier_id == "DOSSIER-KST-2026-001" and len(loaded.runs) == 50
    assert loaded.ground_truth is None
    assert (uploads.UPLOADS_DIR / "DOSSIER-KST-2026-001" / "runs").is_dir()
    assert [p.name for p in uploads.list_uploaded_dossiers()] == ["DOSSIER-KST-2026-001"]


def test_a_top_level_folder_in_the_zip_is_fine():
    loaded = uploads.save_uploaded_dossier(_zip_of(HAL, folder="DOSSIER-HAL-2026-001"))
    assert loaded.dossier.dossier_id == "DOSSIER-HAL-2026-001"


def test_the_answer_key_is_discarded_not_stored():
    uploads.save_uploaded_dossier(_zip_of(KST, include_ground_truth=True))
    assert not (uploads.UPLOADS_DIR / "DOSSIER-KST-2026-001" / "ground_truth.json").exists()


def test_a_tampered_run_is_rejected_at_the_door_naming_the_run():
    def tamper(rel, data):
        if rel.name == "RUN-2026-0811-0043.json":
            return data.replace(b"708.0", b"408.0", 1)
        return data
    with pytest.raises(uploads.DossierUploadError, match="RUN-2026-0811-0043"):
        uploads.save_uploaded_dossier(_zip_of(KST, mutate=tamper))
    assert uploads.list_uploaded_dossiers() == []  # nothing half-stored


def test_a_run_missing_from_the_zip_is_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path in sorted(KST.rglob("*.json")):
            rel = path.relative_to(KST)
            if rel.name in ("ground_truth.json", "RUN-2026-0811-0043.json"):
                continue
            zf.writestr(str(rel), path.read_bytes())
    with pytest.raises(uploads.DossierUploadError, match="missing"):
        uploads.save_uploaded_dossier(buf.getvalue())


def test_duplicate_dossier_id_rejected():
    uploads.save_uploaded_dossier(_zip_of(KST))
    with pytest.raises(uploads.DossierUploadError, match="already exists"):
        uploads.save_uploaded_dossier(_zip_of(KST))
    with pytest.raises(uploads.DossierUploadError, match="already exists"):
        uploads.save_uploaded_dossier(_zip_of(HAL), existing_ids={"DOSSIER-HAL-2026-001"})


def test_not_a_zip_and_not_a_dossier_are_rejected_with_a_reason():
    with pytest.raises(uploads.DossierUploadError, match="not a zip"):
        uploads.save_uploaded_dossier(b"{not a zip}")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "hello")
    with pytest.raises(uploads.DossierUploadError, match="exactly one dossier.json"):
        uploads.save_uploaded_dossier(buf.getvalue())


def test_unsafe_archive_paths_are_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("dossier.json", "{}")
        zf.writestr("../evil.json", "{}")
    with pytest.raises(uploads.DossierUploadError, match="unsafe path"):
        uploads.save_uploaded_dossier(buf.getvalue())


def test_list_uploaded_dossiers_empty_when_dir_missing():
    assert uploads.list_uploaded_dossiers() == []
