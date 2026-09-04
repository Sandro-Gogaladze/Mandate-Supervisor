"""FastAPI backend (architecture-v2 §18). Three concerns:

- **Three AG-UI endpoints**, one per run kind, each wrapping its compiled
  graph via `ag_ui_langgraph`: `/agent/triage` (the multi-agent showpiece),
  `/agent/session` (the conversational orchestrator), `/agent/drafter`
  (draft → grounding → the human gate, with `emit_interrupt_outcome=True`
  so the client resumes the gate via `RunAgentInput.resume[]`). The
  frontend addresses a case by `case_id` in initial agent state — never by
  filesystem path; the old client-controlled `case_path` file read is gone.
- **REST over the ledger**: the queue and case detail are projections of
  the append-only record (`ledger/projection.py`), sorted by risk score —
  the concept note's "prioritised queue", literally. Run listings, run
  diffs, prompt defaults, chain verification, JSONL export.
- **Intake**: a dossier is uploaded as a zip of its directory and verified
  at the door (data/uploads.py) before `case_submitted` is appended. Triage
  is supervisor-initiated — from the case room or by asking the orchestrator
  — never automatic.

Checkpointers here are AG-UI thread plumbing: per-process, in-memory,
disposable. The ledger is the record; deleting a checkpointer loses only an
in-flight run's resumability.
"""
from __future__ import annotations

import logging

from ag_ui_langgraph import LangGraphAgent as _LangGraphAgent, add_langgraph_fastapi_endpoint
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel

from agents.llm import LLMUnavailable
from agents.prompts import PROMPTS_BY_RUN_KIND, load_prompt
from ledger import get_default_store
from ledger.projection import diff_runs, project_case, visible_events
from ledger.seed import latest_submission, seed_corpus
from pipeline.graph import (
    build_drafting_graph,
    build_investigation_graph,
    build_triage_graph,
    run_triage,
)
from registry.loader import load_all_rulesets, load_failure_catalogue

logger = logging.getLogger(__name__)

app = FastAPI(title="Mandate Supervisor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# What the browser needs from a run is the decision, the findings and the
# score — not the dossier, the evidence pack or every fact. Left in, the
# adapter's node-exit snapshots and RAW event echoes sent 30 MB for one
# six-second question (measured: 18 MB RAW, 12 MB in four snapshots) and
# choked the page. RAW events are debugging echoes and are switched off;
# snapshots drop the heavy keys the console never reads.
_HEAVY_STATE_KEYS = frozenset({"dossier", "evidence", "facts", "assessments", "prompts", "dispatch_contexts"})


class LangGraphAgent(_LangGraphAgent):
    def __init__(self, **kwargs):
        kwargs.setdefault("emit_raw_events", False)
        super().__init__(**kwargs)

    def get_state_snapshot(self, state):
        state = super().get_state_snapshot(state)
        if isinstance(state, dict):
            state = {k: v for k, v in state.items() if k not in _HEAVY_STATE_KEYS}
        return state


_store = get_default_store()
seed_corpus(_store)
from api.dossiers import create_router
app.include_router(create_router(_store))

_triage_graph = build_triage_graph(store=_store, checkpointer=MemorySaver())
_session_graph = build_investigation_graph(store=_store, checkpointer=MemorySaver())
_drafting_graph = build_drafting_graph(store=_store, checkpointer=MemorySaver())

add_langgraph_fastapi_endpoint(
    app=app,
    agent=LangGraphAgent(
        name="mandate_supervisor",
        description="Runs a full triage pass over one case: eight domain peers, control assurance, critic, synthesizer, authorisation.",
        graph=_triage_graph,
    ),
    path="/agent/triage",
)
add_langgraph_fastapi_endpoint(
    app=app,
    agent=LangGraphAgent(
        name="supervisor_session",
        description="Routes one officer message: reply from the record, or dispatch a specialist / the investigator.",
        graph=_session_graph,
    ),
    path="/agent/session",
)
add_langgraph_fastapi_endpoint(
    app=app,
    agent=LangGraphAgent(
        name="report_drafter",
        description="Drafts the supervisory report, grounds it, and holds at the named-reviewer gate.",
        graph=_drafting_graph,
        # PLAN item 13's transport, unchanged: terminate the interrupted run
        # with the structured outcome so the client resumes via resume[].
        emit_interrupt_outcome=True,
    ),
    path="/agent/drafter",
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/failures")
async def list_failure_catalogue() -> dict:
    """The stable F1--F73 vocabulary plus its implemented rule coverage."""
    catalogue = load_failure_catalogue()
    mappings: dict[str, list[dict]] = {f.failure_id: [] for f in catalogue.failures}
    for ruleset in load_all_rulesets().values():
        for rule in ruleset.rules:
            for failure_id in rule.failures:
                if failure_id in mappings:
                    mappings[failure_id].append({
                        "rule_id": rule.rule_id,
                        "ruleset_id": ruleset.ruleset_id,
                        "ruleset_version": ruleset.version,
                        "rule_status": rule.status,
                        "evaluation": rule.evaluation,
                    })
    return {
        "catalogue_id": catalogue.catalogue_id,
        "version": catalogue.version,
        "as_of": catalogue.as_of,
        "failures": [
            {**failure.model_dump(), "mapped_rules": mappings[failure.failure_id],
             "non_rule_detector": ("systemic" if failure.failure_id in {"F57", "F67", "F69"}
                                   else None)}
            for failure in catalogue.failures
        ],
    }


def _submission_line(case_id: str) -> str | None:
    try:
        payload = latest_submission(_store, case_id)
    except ValueError:
        return None
    dossier = payload.get("dossier") or {}
    firm = payload.get("firm") or {}
    runs = len(payload.get("runs", []))
    return (f"{runs} run{'s' if runs != 1 else ''} · {dossier.get('agent_id', '?')} · "
            f"{dossier.get('submission_purpose', 'submission')} via {firm.get('institution_name', '?')}")


def _summary(record, case_id: str) -> dict:
    # Through the same filter the projection uses: a cleared case must not
    # keep advertising the disposition of the review that was cleared.
    events = visible_events(_store.events_for(case_id))
    recommendation = next((e.payload.get('disposition') for e in reversed(events) if e.event_type == 'authorisation_computed'), None)
    decision = next((e.payload.get('disposition') for e in reversed(events) if e.event_type == 'authorisation_decided'), None)
    return {
        'recommendation': recommendation, 'authorisation_decision': decision,
        "case_id": case_id,
        "firm": record.firm,
        "status": record.status,
        # Ground truth never reaches the pipeline or the queue; a real
        # submission carries no label.
        "label": None,
        "summary": record.submitted_summary or _submission_line(case_id)
        or f"{record.event_count} events on record",
        "risk_total": record.risk_score.total if record.risk_score else None,
        "risk_tier": record.risk_score.tier if record.risk_score else None,
        "findings_count": len(record.findings),
        "failure_occurrences_count": len(record.failure_occurrences),
        "observations_count": len(record.observations),
        "opened_by": record.opened_by,
        "last_event_at": record.last_event_at,
    }


@app.get("/cases")
async def list_cases() -> list[dict]:
    """The prioritised queue: highest risk first, unscored (still
    `submitted`) cases last, stable by first-seen within a band."""
    summaries = []
    for case_id in _store.all_case_ids():
        record = project_case(_store.events_for(case_id))
        summaries.append(_summary(record, case_id))
    summaries.sort(key=lambda s: (s["risk_total"] is None, -(s["risk_total"] or 0.0)))
    return summaries


def _record_or_404(case_id: str):
    events = _store.events_for(case_id)
    if not events:
        raise HTTPException(status_code=404, detail=f"No case with id {case_id!r}")
    return project_case(events)


@app.get("/cases/{case_id}")
async def get_case(case_id: str) -> dict:
    record = _record_or_404(case_id)
    return {
        **_summary(record, case_id),
        "record": record.model_dump(),
        "raw": latest_submission(_store, case_id),
    }


@app.get("/cases/{case_id}/runs")
async def list_runs(case_id: str) -> list[dict]:
    record = _record_or_404(case_id)
    return [run.model_dump() for run in record.runs]


@app.get("/cases/{case_id}/runs/{run_a}/diff/{run_b}")
async def run_diff(case_id: str, run_a: str, run_b: str) -> dict:
    record = _record_or_404(case_id)
    by_id = {run.run_id: run for run in record.runs}
    missing = [rid for rid in (run_a, run_b) if rid not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"No run(s) {missing} on case {case_id!r}")
    return diff_runs(by_id[run_a], by_id[run_b]).model_dump()


async def _background_triage(case_id: str) -> None:
    try:
        await run_triage(case_id, store=_store)
    except LLMUnavailable:
        logger.warning("No ANTHROPIC_API_KEY — case %s submitted without automatic triage", case_id)
    except Exception:
        logger.exception("Background triage failed for %s", case_id)


class _ActorBody(BaseModel):
    officer: str = "officer"
    reason: str | None = None


@app.post("/cases/{case_id}/open")
async def open_case(case_id: str, body: _ActorBody) -> dict:
    _record_or_404(case_id)
    _store.append(case_id=case_id, event_type="case_opened", payload={}, actor=f"human:{body.officer}")
    return _record_or_404(case_id).model_dump()


@app.post("/cases/{case_id}/close")
async def close_case(case_id: str, body: _ActorBody) -> dict:
    """Close, no action — a clean case's exit is a named decision, not a
    drafted document."""
    _record_or_404(case_id)
    _store.append(
        case_id=case_id, event_type="case_closed",
        payload={"reason": body.reason or "no action required"},
        actor=f"human:{body.officer}",
    )
    return _record_or_404(case_id).model_dump()


@app.post("/cases/{case_id}/triage")
async def trigger_triage(case_id: str, background: BackgroundTasks) -> dict:
    _record_or_404(case_id)
    background.add_task(_background_triage, case_id)
    return {"status": "triage started", "case_id": case_id}


@app.get("/prompts")
async def prompts() -> dict:
    """Every default prompt, split so the UI can show the editable body
    between its fixed preamble and contract. Per-run overrides ride the run
    request; nothing here is writable."""
    out = {}
    for kind, prompt_ids in PROMPTS_BY_RUN_KIND.items():
        for pid in prompt_ids:
            if pid in out:
                out[pid]["used_by"].append(kind)
                continue
            try:
                spec = load_prompt(pid)
            except KeyError:
                continue
            out[pid] = {**spec.model_dump(), "used_by": [kind]}
    return out


@app.get("/ledger/verify")
async def ledger_verify() -> dict:
    problems = _store.verify()
    return {
        "intact": not problems,
        "event_count": len(_store.all_events()),
        "problems": problems,
    }


@app.get("/ledger/{case_id}")
async def ledger_events(case_id: str, include_cleared: bool = False) -> list[dict]:
    """The case's events. A reset hides the review that preceded it, so the
    console shows a case with no review rather than a hidden one; the audit
    trail is untouched and `include_cleared=true` returns all of it (the
    timeline and the hash-chain verifier use that)."""
    events = _store.events_for(case_id)
    if not events:
        raise HTTPException(status_code=404, detail=f"No case with id {case_id!r}")
    if not include_cleared:
        events = visible_events(events)
    return [e.model_dump() for e in events]


@app.get("/ledger/{case_id}/export")
async def ledger_export(case_id: str) -> list[str]:
    if not _store.has_case(case_id):
        raise HTTPException(status_code=404, detail=f"No case with id {case_id!r}")
    return list(_store.export_jsonl(case_id))


_GRAPHS_BY_KIND = {
    "triage": _triage_graph,
    "investigation": _session_graph,
    "drafting": _drafting_graph,
}


def _graph_structure(graph) -> dict:
    drawable = graph.get_graph()
    nodes = [
        {"id": node_id, "label": node_id}
        for node_id in drawable.nodes
        if node_id not in ("__start__", "__end__")
    ]
    edges = [
        {"source": edge.source, "target": edge.target, "conditional": edge.conditional}
        for edge in drawable.edges
        if edge.source != "__start__" and edge.target != "__end__"
    ]
    return {"nodes": nodes, "edges": edges}


@app.get("/graph")
async def graph_structure() -> dict:
    """Back-compat: the triage graph — the multi-agent showpiece."""
    return _graph_structure(_triage_graph)


from pipeline.map import supervision_map


@app.get("/graph/full")
async def graph_full() -> dict:
    return supervision_map(_GRAPHS_BY_KIND)


@app.get("/graph/{kind}")
async def graph_structure_by_kind(kind: str) -> dict:
    if kind not in _GRAPHS_BY_KIND:
        raise HTTPException(status_code=404, detail=f"kind must be one of {sorted(_GRAPHS_BY_KIND)}")
    return _graph_structure(_GRAPHS_BY_KIND[kind])
