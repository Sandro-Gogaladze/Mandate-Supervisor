"""`python -m ledger.verify [path]` — walk the whole chain, report problems.

Exit code 0 with "intact" on a clean chain; exit code 1 listing every broken
link otherwise. The same check is exposed at GET /ledger/verify because
"prove the record hasn't been tampered with" is a demo beat, not just a
maintenance task.
"""
from __future__ import annotations

import sys

from .store import LEDGER_PATH, LedgerStore


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = argv[0] if argv else LEDGER_PATH
    store = LedgerStore(path)
    events = store.all_events()
    problems = store.verify()
    if problems:
        print(f"{path}: chain BROKEN — {len(problems)} problem(s) across {len(events)} event(s)")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"{path}: chain intact — {len(events)} event(s) verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
