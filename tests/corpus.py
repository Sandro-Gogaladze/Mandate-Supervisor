"""The dossier fixtures every graph and agent test builds on.

The corpus IS the fixture: three hand-authored, signed dossiers. Loaded
dossiers are shared read-only; a test that needs a variant makes one with
`model_copy` (`thin()`, `with_raw()`) and never mutates the shared object.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from data.dossier_loader import load, load_for_pipeline
from ledger import LedgerStore
from ledger.seed import submit_dossier
from schemas.dossier import LoadedDossier

ROOT = Path(__file__).resolve().parent.parent
KST = ROOT / "data" / "dossiers" / "DOSSIER-KST-2026-001"
HAL = ROOT / "data" / "dossiers" / "DOSSIER-HAL-2026-001"
LRK = ROOT / "data" / "dossiers" / "DOSSIER-LRK-2026-001"


def kst() -> LoadedDossier:
    return load(KST)


def hal() -> LoadedDossier:
    return load(HAL)


def lrk() -> LoadedDossier:
    return load(LRK)


def seed(store: LedgerStore, path: Path = KST, *, dossier: LoadedDossier | None = None) -> str:
    """Submit a dossier to `store` as the pipeline sees it — ground truth never opened."""
    return submit_dossier(store, dossier or load_for_pipeline(path))


def thin(dossier: LoadedDossier, n: int = 10) -> LoadedDossier:
    """The same dossier with only its first `n` ledger rows — below Drift's
    baseline minimum, above Log's."""
    return dossier.model_copy(update={"transaction_history": dossier.transaction_history[:n]})


def with_raw(dossier: LoadedDossier, mutate) -> LoadedDossier:
    """A copy whose RAW submission has been edited by `mutate(raw_dossier,
    raw_runs)` — the thing intake verifies, as opposed to the typed view."""
    raw_dossier, raw_runs = deepcopy(dossier.raw_dossier), deepcopy(dossier.raw_runs)
    mutate(raw_dossier, raw_runs)
    return dossier.model_copy(update={"raw_dossier": raw_dossier, "raw_runs": raw_runs})
