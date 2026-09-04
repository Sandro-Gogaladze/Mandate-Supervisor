from __future__ import annotations

import pytest

from ledger import LedgerStore
from tests import corpus


@pytest.fixture(scope="session")
def kst():
    return corpus.kst()


@pytest.fixture(scope="session")
def hal():
    return corpus.hal()


@pytest.fixture
def store(tmp_path) -> LedgerStore:
    return LedgerStore(tmp_path / "ledger.db")


# ---------------------------------------------------------------------------
# Parked while the pipeline migrates to the Dossier shape (migration-plan.md).
#
# Listed by name rather than matched by glob, deliberately: a glob would
# silently swallow any new test that happened to match, and the whole point of
# parking rather than deleting is that the missing coverage stays visible and
# counted. Twenty-two modules were parked when the case corpus was deleted;
# Phases 2 and 3 brought every one back or retired it. The list is empty and
# stays here so the next migration has somewhere honest to put its debt.
# ---------------------------------------------------------------------------
collect_ignore: list[str] = []
