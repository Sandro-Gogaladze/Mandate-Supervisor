"""What the API calls: run a sweep, compare two, promote a draft.

Promotion is the one act here that is real supervision rather than
rehearsal, so it is the one thing that reaches the ledger — carrying the
`sweep_id` it rested on. A future regulator asking "what did you know when
you tightened this rule?" gets an answer instead of a commit message.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from ledger import LedgerStore, get_default_store
from registry.loader import RULESETS_DIR
from schemas import Ruleset, Sweep, SweepComparison

from .drafts import active_ruleset, get_draft, list_drafts, ruleset_digest
from .store import SweepStore, compare, new_sweep_id
from .sweep import now, pins, run_sweep

PUBLISHED_DIR = RULESETS_DIR / "published"


async def start_sweep(*, ruleset_ref: str, store: SweepStore, live: bool = False,
                      model=None) -> Sweep:
    """Run `ruleset_ref` — a draft id, or `<domain>` for the book in force —
    over the whole labelled corpus."""
    overrides: dict[str, Ruleset] = {}
    if "@" in ruleset_ref:
        draft = get_draft(ruleset_ref)
        domain, label, digest = draft.domain, draft.label, draft.digest
        overrides[domain] = draft.ruleset
    else:
        domain = ruleset_ref
        book = active_ruleset(domain)
        label, digest = f"in force · v{book.version}", ruleset_digest(book)

    sweep = Sweep(sweep_id=new_sweep_id(), domain=domain, ruleset_ref=ruleset_ref,
                  ruleset_digest=digest, label=label,
                  pins=pins(mode="live" if live else "mechanical"), started_at=now())
    store.save(sweep)
    try:
        result = await run_sweep(rulesets=overrides or None, live=live, model=model)
        sweep = sweep.model_copy(update={"result": result, "finished_at": now()})
    except Exception as exc:  # a failed sweep is a recorded outcome, not a hole
        sweep = sweep.model_copy(update={"error": f"{type(exc).__name__}: {exc}",
                                         "finished_at": now()})
    return store.save(sweep)


def compare_sweeps(base_id: str, candidate_id: str, *, store: SweepStore) -> SweepComparison:
    base, candidate = store.get(base_id), store.get(candidate_id)
    if base is None or candidate is None:
        raise ValueError("both sweeps must exist")
    return compare(base, candidate)


def promote(*, draft_id: str, sweep_id: str, promoted_by: str, rationale: str,
            store: SweepStore, ledger: LedgerStore | None = None) -> dict:
    """Publish a draft as the book in force.

    Gated the way every consequential act in this system is gated: a named
    person, a rationale, and the evidence attached. The sweep must be of this
    exact draft and on current pins — promoting on the strength of a
    scorecard taken against a different corpus would be worse than promoting
    with no evidence at all, because it would look like evidence.
    """
    draft = get_draft(draft_id)
    sweep = store.get(sweep_id)
    if sweep is None:
        raise ValueError("no such sweep")
    if sweep.ruleset_ref != draft_id or sweep.ruleset_digest != draft.digest:
        raise ValueError("that sweep did not measure this draft as it now stands")
    if sweep.result is None:
        raise ValueError("that sweep produced no result")
    current_pins = pins(mode=sweep.pins.mode)
    if sweep.pins.corpus_digest != current_pins.corpus_digest:
        raise ValueError("the corpus changed since that sweep — re-run it")
    if not rationale.strip():
        raise ValueError("a promotion needs a rationale")

    base = active_ruleset(draft.domain)
    version = _next_version(base.version)
    published = draft.ruleset.model_copy(update={
        "version": version,
        "as_of": datetime.now(timezone.utc).date().isoformat(),
    })

    # Keep the outgoing book readable rather than overwriting it: the version
    # graph is then a fact on disk, not something reconstructed from git.
    PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
    live_path = RULESETS_DIR / f"{draft.domain}.json"
    shutil.copy2(live_path, PUBLISHED_DIR / f"{draft.domain}@{base.version}.json")
    live_path.write_text(
        json.dumps(published.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")

    (ledger or get_default_store()).append(
        case_id=f"registry:{draft.domain}", event_type="ruleset_promoted",
        payload={"domain": draft.domain, "from_version": base.version,
                 "to_version": version, "draft_id": draft_id,
                 "ruleset_digest": ruleset_digest(published), "sweep_id": sweep_id,
                 "rationale": rationale, "edits": draft.edits,
                 "evidence": {"overall": sweep.result.overall.model_dump(),
                              "clean_run_false_positives": len(sweep.result.clean_run_false_positives),
                              "dossiers_correct": sum(d.correct for d in sweep.result.dossiers)}},
        actor=f"human:{promoted_by}")
    return {"domain": draft.domain, "from_version": base.version, "to_version": version}


def _next_version(current: str) -> str:
    """2026.9 → 2026.10. Minor bump within the year; a new year is a manual
    decision, not something a promotion should guess at."""
    try:
        year, minor = current.split(".")
        return f"{year}.{int(minor) + 1}"
    except ValueError:
        return f"{current}+1"


def version_graph(domain: str, *, store: SweepStore) -> dict:
    """What the left-hand pane renders: the book in force, every published
    version still on disk, and every draft — each with its latest sweep."""
    book = active_ruleset(domain)
    drafts = []
    for draft in list_drafts(domain):
        sweep = store.latest_for(draft.draft_id)
        drafts.append({"draft": draft.model_dump(mode="json"),
                       "sweep_id": sweep.sweep_id if sweep else None,
                       "swept": sweep is not None and sweep.result is not None,
                       "mode": sweep.pins.mode if sweep else None})
    superseded = sorted(
        (p.stem.split("@", 1)[1] for p in PUBLISHED_DIR.glob(f"{domain}@*.json")),
        reverse=True) if PUBLISHED_DIR.exists() else []
    active_sweep = store.latest_for(domain)
    return {
        "domain": domain,
        "active": {"version": book.version, "as_of": book.as_of,
                   "rules": len(book.rules),
                   "sweep_id": active_sweep.sweep_id if active_sweep else None,
                   # How that scorecard was taken. Two sweeps in different
                   # modes refuse to be compared, so the pane needs this to
                   # warn before someone presses Compare.
                   "mode": active_sweep.pins.mode if active_sweep else None},
        "superseded": superseded,
        "drafts": drafts,
    }
