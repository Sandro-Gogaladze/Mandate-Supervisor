from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ledger import LedgerStore
from tests import corpus

ROOT = Path(__file__).resolve().parent.parent
# The rulebook in force and the drafts beside it are the policy instrument, not
# scratch space. Everything else a test writes goes to tmp_path already; these
# two directories are the ones a test can reach by accident, because the
# sandbox writes to them by design.
POLICY_DIRS = (ROOT / "registry" / "rulesets", ROOT / "registry" / "drafts")


def _policy_snapshot() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for directory in POLICY_DIRS if directory.exists()
        for path in sorted(directory.rglob("*.json"))
    }


@pytest.fixture(scope="session", autouse=True)
def policy_stays_read_only():
    """A test run must not change the rules it is testing against.

    This was not hypothetical. The sandbox's draft fixture wrote into the real
    `registry/drafts/`, so a run that died before teardown left a draft behind
    and every later run failed on `a draft called 'test fixture' already
    exists` — a green suite turning red with no code change. Promotion is the
    same hazard with a worse blast radius: `sandbox.service.promote` rewrites
    the ruleset in force, and only the fact that every promotion test asserts
    a raise has so far kept a test run from republishing policy.

    Asserted at session end rather than fixed only at the call site, because
    the next component that writes to `registry/` will not think to ask.
    """
    before = _policy_snapshot()
    yield
    after = _policy_snapshot()
    if before == after:
        return
    changed = sorted(
        [f"{f} changed" for f in before.keys() & after.keys() if before[f] != after[f]]
        + [f"{f} written" for f in after.keys() - before.keys()]
        + [f"{f} deleted" for f in before.keys() - after.keys()])
    raise AssertionError(
        "the test run modified checked-in policy — point the writer at tmp_path:\n  "
        + "\n  ".join(changed))


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
