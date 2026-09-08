"""The policy sandbox's HTTP surface.

Sweeps are the expensive verb here — a mechanical sweep runs the whole
pipeline over every labelled dossier. They are serialised behind one lock so
a page that fires two at once queues rather than competing for the same
temporary ledgers.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ledger import LedgerStore
from agents.catalog import RULESET_LOADERS
from sandbox.drafts import DraftError, create_draft, delete_draft, edit_rule, get_draft, list_drafts
from sandbox.service import (
    compare_sweeps, existing_sweep, promote, start_sweep, version_graph,
)
from sandbox.store import SweepStore

# One sweep at a time, process-wide.
_sweep_lock = asyncio.Lock()

DOMAIN_LABELS = {
    "kya": "Identity & Authority",
    "mandate": "Mandate Fidelity",
    "consent": "Consent & Harm",
    "provenance": "Decision Provenance",
    "injection": "Manipulation",
    "counterparty": "Counterparty",
    "log": "Transaction Patterns",
    "drift": "Behavioural Drift",
    "control_assurance": "Control Assurance",
    "systemic": "Portfolio & Systemic",
}


class DraftRequest(BaseModel):
    domain: str
    label: str
    created_by: str = "officer"
    notes: str | None = None


class EditRequest(BaseModel):
    rule_id: str
    status: str | None = None
    severity_weight: float | None = None
    params: dict | None = None


class SweepRequest(BaseModel):
    ruleset_ref: str
    # Mechanical unless asked otherwise, matching the console and the library.
    # This defaulted to True on the argument that an officer reading a
    # scorecard wants the judged rules scored too — true, but it made the
    # cheapest possible request (`{"ruleset_ref": "kya"}`) the one that costs
    # six minutes and real model spend. A default nobody can regret pressing
    # is worth more than a default that is right when it is deliberate, and
    # the console now names the mode on every call either way.
    live: bool = False
    # Measure again even though this exact rulebook already has a scorecard
    # taken over the same corpus, policy and pipeline. The default returns
    # that one instead: nothing that could move the numbers has moved, and a
    # live sweep costs six minutes and real spend. In live mode a second
    # reading is still worth asking for — it is the only way to see how much
    # of a comparison is model variance.
    force: bool = False


class PromoteRequest(BaseModel):
    draft_id: str
    sweep_id: str
    promoted_by: str
    rationale: str


def create_sandbox_router(ledger: LedgerStore, *, store: SweepStore | None = None,
                          model=None) -> APIRouter:
    router = APIRouter(prefix="/sandbox", tags=["sandbox"])
    sweeps = store or SweepStore()

    @router.get("/domains")
    async def domains():
        out = []
        for name, loader in RULESET_LOADERS.items():
            book = loader()
            if book is None:
                continue
            out.append({
                "domain": name,
                "label": DOMAIN_LABELS.get(name, name),
                "version": book.version,
                "rules": len(book.rules),
                "judged": sum(1 for r in book.rules if r.evaluation == "judged"),
                "tunable": sum(1 for r in book.rules if r.params),
            })
        return sorted(out, key=lambda d: -d["rules"])

    @router.get("/graph/{domain}")
    async def graph(domain: str, mode: str | None = None):
        """`mode` shows each version the scorecard it has IN THAT MODE. The
        console passes the mode its Sweep button is set to, so the numbers on
        screen are always ones the next sweep can be compared against."""
        try:
            return version_graph(domain, store=sweeps, mode=mode)
        except DraftError as exc:
            raise HTTPException(404, str(exc))

    @router.get("/rulebook/{ref}")
    async def rulebook(ref: str):
        """A draft by id, or the book in force for a domain."""
        try:
            if "@" in ref:
                draft = get_draft(ref)
                return {"ref": ref, "editable": True, "label": draft.label,
                        "ruleset": draft.ruleset.model_dump(mode="json"),
                        "edits": draft.edits, "domain": draft.domain,
                        # What a sweep pins. The console compares it against
                        # the stored scorecard's digest to tell whether that
                        # scorecard still describes these rules.
                        "ruleset_digest": draft.digest}
            from sandbox.drafts import active_ruleset
            book = active_ruleset(ref)
            from sandbox.drafts import ruleset_digest
            return {"ref": ref, "editable": False, "label": f"in force · v{book.version}",
                    "ruleset": book.model_dump(mode="json"), "edits": [], "domain": ref,
                    "ruleset_digest": ruleset_digest(book)}
        except DraftError as exc:
            raise HTTPException(404, str(exc))

    @router.get("/drafts")
    async def drafts(domain: str | None = None):
        return [d.model_dump(mode="json") for d in list_drafts(domain)]

    @router.post("/drafts")
    async def new_draft(body: DraftRequest):
        try:
            draft = create_draft(domain=body.domain, label=body.label,
                                 created_by=body.created_by, notes=body.notes)
        except DraftError as exc:
            raise HTTPException(400, str(exc))
        return draft.model_dump(mode="json")

    @router.patch("/drafts/{draft_id}")
    async def patch_draft(draft_id: str, body: EditRequest):
        try:
            draft = edit_rule(draft_id, body.rule_id, status=body.status,
                              severity_weight=body.severity_weight, params=body.params)
        except DraftError as exc:
            raise HTTPException(400, str(exc))
        except Exception as exc:  # a rejected parameter shape
            raise HTTPException(422, str(exc))
        return draft.model_dump(mode="json")

    @router.delete("/drafts/{draft_id}")
    async def remove_draft(draft_id: str):
        try:
            delete_draft(draft_id)
        except DraftError as exc:
            raise HTTPException(404, str(exc))
        return {"deleted": draft_id}

    @router.get("/sweeps")
    async def sweep_list(domain: str | None = None, limit: int = 50):
        return [s.model_dump(mode="json") for s in sweeps.list(domain, limit)]

    @router.get("/sweeps/{sweep_id}")
    async def sweep_detail(sweep_id: str):
        sweep = sweeps.get(sweep_id)
        if sweep is None:
            raise HTTPException(404, "no such sweep")
        return sweep.model_dump(mode="json")

    @router.post("/sweeps")
    async def run(body: SweepRequest):
        try:
            # Checked before the lock: a reused scorecard is a SQL lookup and
            # has no business queueing behind somebody else's six-minute sweep.
            stored = None if body.force else existing_sweep(
                ruleset_ref=body.ruleset_ref, store=sweeps, live=body.live)
            if stored is not None:
                # The console says so. A Sweep button that returns in a second
                # where it usually takes six minutes has to explain itself, or
                # the reader concludes it did not run.
                return {**stored.model_dump(mode="json"), "reused": True}
            async with _sweep_lock:
                sweep = await start_sweep(ruleset_ref=body.ruleset_ref, store=sweeps,
                                          live=body.live, model=model, reuse=False)
        except DraftError as exc:
            raise HTTPException(404, str(exc))
        return {**sweep.model_dump(mode="json"), "reused": False}

    @router.get("/compare")
    async def comparison(base: str, candidate: str):
        try:
            return compare_sweeps(base, candidate, store=sweeps).model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(404, str(exc))

    @router.post("/promote")
    async def do_promote(body: PromoteRequest):
        try:
            return promote(draft_id=body.draft_id, sweep_id=body.sweep_id,
                           promoted_by=body.promoted_by, rationale=body.rationale,
                           store=sweeps, ledger=ledger)
        except DraftError as exc:
            raise HTTPException(404, str(exc))
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    return router
