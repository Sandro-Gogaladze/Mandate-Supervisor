"""Ad hoc dossier submissions — an institution filing a dossier that arrived
out of band, rather than only reviewing the two pre-loaded corpus dossiers.

A dossier is a directory, not a file (HANDOFF §7.5): dossier.json, the run
files, transactions.json. An upload is that directory as a zip. It is
**verified at the door** by the same loader the corpus goes through
(data/dossier_loader.py): every run_index digest must match its file, no run
may be missing, none may be present that the index does not name, the
schema must validate. A submission failing any of these is rejected with
the reason, not stored and flagged later — the index is an attestation, and
accepting one that contradicts itself destroys the point of having one.

A submission never carries the answer key: a ground_truth.json inside an
upload is discarded, not stored.

Migration Phase 8 adds streamed intake, per-institution authentication and
the S2 record. This is the smallest thing that keeps the intake path alive
on the dossier shape.
"""
from __future__ import annotations

import io
import re
import shutil
import tempfile
import zipfile
from collections.abc import Iterable
from pathlib import Path

from data.dossier_loader import load
from schemas.dossier import LoadedDossier

UPLOADS_DIR = Path(__file__).resolve().parent / "uploads"

_SAFE_ID = re.compile(r"[A-Za-z0-9._-]+")


class DossierUploadError(ValueError):
    """The upload is not a zip, is not a dossier, fails verification at the
    door, or reuses a dossier_id that already exists."""


def _members(zf: zipfile.ZipFile) -> list[str]:
    names = [n for n in zf.namelist() if not n.endswith("/")]
    for n in names:
        parts = Path(n).parts
        if n.startswith("/") or "\\" in n or ".." in parts or any(p.startswith("/") for p in parts):
            raise DossierUploadError(f"unsafe path in archive: {n!r}")
    return names


def save_uploaded_dossier(data: bytes, *, existing_ids: Iterable[str] = (), institution_id: str | None = None) -> LoadedDossier:
    """Verifies `data` (a zip of a dossier directory) at the door and
    persists it under data/uploads/<dossier_id>/. Returns the loaded dossier,
    ground truth withheld. Raises `DossierUploadError` with a message safe to
    show a user otherwise."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise DossierUploadError("This upload is not a zip archive of a dossier directory.") from exc

    with zf:
        names = _members(zf)
        if len(names) != len(set(names)):
            raise DossierUploadError("Duplicate archive members are not accepted.")
        if sum(i.file_size for i in zf.infolist()) > 64 * 1024 * 1024:
            raise DossierUploadError("Uncompressed dossier exceeds 64 MB.")
        roots = [Path(n).parent for n in names if Path(n).name == "dossier.json"
                 and len(Path(n).parts) <= 2]
        if len(roots) != 1:
            raise DossierUploadError(
                "A dossier zip must contain exactly one dossier.json, at the root or inside one "
                "top-level folder."
            )
        root = roots[0]
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".incoming-", dir=UPLOADS_DIR))
        try:
            for n in names:
                rel = Path(n)
                if root != Path("."):
                    if root not in rel.parents:
                        continue  # outside the dossier folder — ignored
                    rel = rel.relative_to(root)
                if rel.name == "ground_truth.json":
                    continue  # a submission never carries the answer key
                dest = staging / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(n))
            try:
                loaded = load(staging, with_ground_truth=False)
                if institution_id and loaded.dossier.institution_id != institution_id:
                    raise ValueError("dossier institution_id does not match the authenticated submitting institution")
                from ingestion.normalize import normalize_dossier

                integrity = normalize_dossier(loaded).integrity
                failures = integrity.signature_failures + integrity.chain_links_broken
                if failures:
                    raise ValueError("invalid signatures or chain links: " + "; ".join(failures))
            except (ValueError, OSError, KeyError) as exc:
                # ValidationError and JSONDecodeError are ValueErrors; a
                # missing transactions.json is an OSError. All are "rejected
                # at the door, and here is why".
                raise DossierUploadError(f"Rejected at the door: {exc}") from exc
            dossier_id = loaded.dossier.dossier_id
            if not _SAFE_ID.fullmatch(dossier_id):
                raise DossierUploadError(
                    f"dossier_id {dossier_id!r} must be a plain identifier (letters, digits, . _ -).")
            if dossier_id in set(existing_ids) or (UPLOADS_DIR / dossier_id).exists():
                raise DossierUploadError(f"A dossier with id {dossier_id!r} already exists.")
            final = UPLOADS_DIR / dossier_id
            staging.rename(final)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    return load(final, with_ground_truth=False)


def list_uploaded_dossiers() -> list[Path]:
    if not UPLOADS_DIR.exists():
        return []
    return sorted(p for p in UPLOADS_DIR.iterdir()
                  if p.is_dir() and not p.name.startswith(".") and (p / "dossier.json").exists())
