"""Read a dossier directory back into one object.

    data/dossiers/DOSSIER-BRL-2026-001/
      dossier.json          the case: what all the runs share, plus the index
      runs/*.json           one file per run, each self-describing
      transactions.json     the institution's ledger
      ground_truth.json     eval only

`load_for_pipeline` simply does not read ground_truth.json. That is the whole
mechanism — withholding the answer key is a file that goes unread, not a
`.model_copy(update={"ground_truth": None})` somebody can forget to call.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from schemas.dossier import Dossier, GroundTruth, LoadedDossier, Run
from schemas.transaction import TransactionLogEntry

DOSSIERS_DIR = Path(__file__).resolve().parent / "dossiers"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load(directory: Path | str, *, with_ground_truth: bool = True) -> LoadedDossier:
    d = Path(directory)
    dossier = Dossier.model_validate(_read(d / "dossier.json"))

    runs, bad = [], []

    # Scan the directory as well as the index. Walking only the index means a
    # run file dropped in afterwards is silently ignored here while anything
    # that globs the directory would happily read it — the two views of "which
    # runs are in this dossier" must not be allowed to disagree.
    on_disk = {p.name for p in (d / "runs").glob("*.json")} if (d / "runs").exists() else set()
    indexed_files = {Path(ref.file).name for ref in dossier.run_index}
    for orphan in sorted(on_disk - indexed_files):
        bad.append(f"runs/{orphan}: present on disk but not in the run index")

    for ref in dossier.run_index:
        path = d / ref.file
        if not path.exists():
            bad.append(f"{ref.run_id}: indexed file {ref.file} is missing")
            continue
        if (actual := digest(path)) != ref.sha256:
            # The index is an attestation. A run edited after filing is exactly
            # what this is here to catch, so it is an error, not a warning.
            bad.append(f"{ref.run_id}: content digest {actual[:19]}… "
                       f"does not match the index")
        runs.append(Run.model_validate(_read(path)))
    if bad:
        raise ValueError("run index does not match the run files:\n  " + "\n  ".join(bad))

    for r in runs:
        if r.dossier_id != dossier.dossier_id:
            raise ValueError(f"{r.run_id} belongs to {r.dossier_id}, not {dossier.dossier_id}")

    txns = [TransactionLogEntry.model_validate(t)
            for t in _read(d / "transactions.json")["transaction_history"]]

    gt = None
    if with_ground_truth and (d / "ground_truth.json").exists():
        gt = GroundTruth.model_validate(_read(d / "ground_truth.json"))

    return LoadedDossier(dossier=dossier, runs=runs, transaction_history=txns, ground_truth=gt)


def load_for_pipeline(directory: Path | str) -> LoadedDossier:
    """As the pipeline must see it. The answer key is never opened."""
    return load(directory, with_ground_truth=False)


def list_dossiers() -> list[Path]:
    return sorted(p for p in DOSSIERS_DIR.iterdir() if (p / "dossier.json").exists()) \
        if DOSSIERS_DIR.exists() else []
