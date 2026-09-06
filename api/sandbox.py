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
from sandbox.service import compare_sweeps, promote, start_sweep, version_graph
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
    # A sweep runs the real pipeline, model calls included. Anything less
    # cannot measure a judged rule, and a scorecard that silently omits a
    # third of the book is worse than no scorecard. The library default stays
    # mechanical for tests and offline use; a sweep asked for through the API
    # is the one an officer will read, so it measures everything.
    live: bool = True


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
    async def graph(domain: str):
        try:
            return version_graph(domain, store=sweeps)
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
            async with _sweep_lock:
                sweep = await start_sweep(ruleset_ref=body.ruleset_ref, store=sweeps,
                                          live=body.live, model=model)
        except DraftError as exc:
            raise HTTPException(404, str(exc))
        return sweep.model_dump(mode="json")

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
