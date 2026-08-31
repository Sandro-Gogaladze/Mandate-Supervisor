"""FastAPI backend (PLAN item 10). Two concerns:

- The AG-UI/CopilotKit endpoint (`/agent`) — wraps pipeline/graph.py's
  compiled StateGraph directly via `ag_ui_langgraph`, confirmed against the
  official CopilotKit LangGraph+FastAPI example
  (github.com/CopilotKit/CopilotKit/tree/main/examples/integrations/
  langgraph-fastapi) before building this. The frontend starts a run by
  setting `case_path` as initial agent state (`useCoAgent`); everything
  from there streams over AG-UI automatically — no bespoke SSE protocol.
- A handful of plain REST endpoints (`/cases`, `/cases/{id}`, `/graph`) for
  what AG-UI doesn't cover: listing cases (from the corpus manifest, since
  the ledger — PLAN item 15 — doesn't exist yet) and the graph's own
  structure for React Flow, generated from `graph.get_graph()` and never
  hand-maintained, per CLAUDE.md.

A `MemorySaver` checkpointer is used here (and only here — pipeline/graph.py's
own tests/run_case() don't need one) because CopilotKit's AG-UI adapter
tracks each run by thread id; per-process, in-memory, disposable, matching
CLAUDE.md's checkpointer philosophy ("never treat it as the audit trail").
"""
from __future__ import annotations

import json
from pathlib import Path

from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.memory import MemorySaver

from data.loader import DATA_DIR, load_manifest
from data.uploads import CaseUploadError, list_uploaded_cases, save_uploaded_case
from pipeline.graph import build_graph

app = FastAPI(title="Mandate Supervisor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_graph = build_graph(checkpointer=MemorySaver())

add_langgraph_fastapi_endpoint(
    app=app,
    # ag_ui_langgraph's own LangGraphAgent, not copilotkit.LangGraphAGUIAgent:
    # that subclass's inherited clone() passes enable_legacy_on_interrupt_event
    # to a narrower __init__ that doesn't accept it (a real version-mismatch
    # bug between copilotkit==0.1.95 and ag-ui-langgraph==0.0.43, confirmed
    # via a live 500 before switching) — the base class's clone()/__init__()
    # are self-consistent and this app doesn't need CopilotKit's extra layer.
    agent=LangGraphAgent(
        name="mandate_supervisor",
        description="Reviews one AI payment agent's mandate chain and transaction history.",
        graph=_graph,
        # PLAN item 13: terminate interrupted runs with the structured AG-UI
        # outcome (RunFinishedEvent outcome={"type": "interrupt", ...}) so
        # @ag-ui/client populates `pendingInterrupts` and the UI can resume
        # via RunAgentInput.resume[] — the human gate's whole transport.
        emit_interrupt_outcome=True,
    ),
    path="/agent",
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


def _all_case_entries() -> list[dict]:
    """Corpus (curated, labeled demo scenarios) + uploaded (real, unlabeled
    submissions) — both resolve `file` the same way (relative to DATA_DIR),
    so every other endpoint can treat them identically. Uploaded entries
    are listed first: they're what a case officer just submitted, and
    should surface above the standing demo queue, not get buried under it."""
    return list_uploaded_cases() + load_manifest()


@app.get("/cases")
async def list_cases() -> list[dict]:
    return [
        {
            "case_id": entry["case_id"],
            "firm": entry["firm"],
            "label": entry.get("label"),
            "summary": entry["summary"],
            "case_path": str((DATA_DIR / entry["file"]).resolve()),
        }
        for entry in _all_case_entries()
    ]


@app.get("/cases/{case_id}")
async def get_case(case_id: str) -> dict:
    for entry in _all_case_entries():
        if entry["case_id"] == case_id:
            path = (DATA_DIR / entry["file"]).resolve()
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            return {
                "case_id": entry["case_id"],
                "firm": entry["firm"],
                "label": entry.get("label"),
                "summary": entry["summary"],
                "case_path": str(path),
                "raw": raw,
            }
    raise HTTPException(status_code=404, detail=f"No case with id {case_id!r}")


@app.post("/cases/upload")
async def upload_case(file: UploadFile) -> dict:
    """A case officer submitting a mandate chain + transaction history that
    arrived out of band, rather than only reviewing the pre-loaded demo
    queue. Validates against the same schema ingestion enforces (so a
    rejection here is a real, actionable schema error, not a generic
    upload failure), then persists via data.uploads so every other
    endpoint — and the pipeline itself — sees it exactly like a corpus
    case."""
    body = await file.read()
    try:
        raw = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"{file.filename} is not valid JSON: {exc}") from exc

    try:
        entry = save_uploaded_case(raw)
    except CaseUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "case_id": entry["case_id"],
        "firm": entry["firm"],
        "label": entry.get("label"),
        "summary": entry["summary"],
        "case_path": str((DATA_DIR / entry["file"]).resolve()),
    }


@app.get("/graph")
async def graph_structure() -> dict:
    """React Flow's node/edge shape, generated from the graph's own
    structure — never hand-maintained, per CLAUDE.md."""
    drawable = _graph.get_graph()
    nodes = [
        {"id": node_id, "label": node_id}
        for node_id in drawable.nodes
        if node_id not in ("__start__", "__end__")
    ]
    edges = [
        {"source": edge.source, "target": edge.target, "conditional": edge.conditional}
        for edge in drawable.edges
        if edge.source not in ("__start__",) and edge.target not in ()
    ]
    return {"nodes": nodes, "edges": edges}
