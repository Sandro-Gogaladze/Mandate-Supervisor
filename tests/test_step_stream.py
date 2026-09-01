"""The step-event contract the supervision map depends on.

ag_ui_langgraph derives STEP_STARTED/STEP_FINISHED from `langgraph_node`
metadata *transitions* on the event stream (agent.py:354/392 — one active
step at a time). The UI lights map nodes from those step names through its
STEP_ALIAS table. This suite pins both ends server-side:

- the exact node-transition sequence per run type (so a graph refactor that
  changes what streams breaks HERE, loudly, not silently on the map), and
- that every step name the backend can emit is either a map node id or an
  aliased plumbing step (so a renamed node can't silently stop lighting).

Zero live calls — FakeChatModel + tmp ledger, same event source as the
real AG-UI adapter.
"""
from __future__ import annotations

import pytest

from data.loader import CASES_DIR, load_raw_case_json
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from ledger import LedgerStore
from ledger.seed import submit_case
from pipeline.graph import (
    build_drafting_graph,
    build_investigation_graph,
    build_triage_graph,
)
from schemas import ReviewerDirective
from tests.fakes import make_graph_fake
from tests.test_investigator import ScriptedFake

# Mirror of dashboard/src/components/CaseReview.tsx::STEP_ALIAS — keep in
# sync by hand; this test exists so a drift breaks visibly.
STEP_ALIAS = {
    "orchestrate": "orchestrator",
    "load_context": "orchestrator",
    "record": "orchestrator",
    "ingest": "orchestrator",
    "dispatch": "orchestrator",
    "bump_round": "orchestrator",
    "escalate_check": "findings",
    "critic": "findings",
    "risk_score": "orchestrator",
    "load_record": "draft_report",
}
# Mirror of the /graph/full node ids (minus "supervisor", the one node that
# never receives step events — it lights only via the gate's awaiting state).
MAP_NODE_IDS = {
    "orchestrator", "mandate", "kya", "log", "drift", "investigator",
    "findings", "synthesizer", "draft_report", "grounding_check", "human_gate",
}


async def node_transitions(graph, initial, config=None) -> list[str]:
    """Ordered `langgraph_node` values as they change — exactly what the
    AG-UI adapter keys its step events on."""
    seq: list[str] = []
    current = None
    async for ev in graph.astream_events(initial, config or {}, version="v2"):
        node = (ev.get("metadata") or {}).get("langgraph_node")
        if node and node != current:
            seq.append(node)
            current = node
    return seq


def assert_all_steps_light_something(transitions: list[str]) -> None:
    for step in transitions:
        target = STEP_ALIAS.get(step, step)
        assert target in MAP_NODE_IDS, (
            f"step {step!r} maps to {target!r}, which is not a map node — "
            f"the supervision map would silently not light for it"
        )


@pytest.fixture
def store(tmp_path) -> LedgerStore:
    return LedgerStore(tmp_path / "ledger.db")


def _seed(store, name):
    return submit_case(store, load_raw_case_json(CASES_DIR / name))


def _triage_initial(cid, **extra):
    return {"case_id": cid, "findings": [], "observations": [], "messages": [], **extra}


async def test_triage_stream_clean_case(store) -> None:
    cid = _seed(store, "case-001-compliant.json")
    graph = build_triage_graph(model=make_graph_fake(), store=store)
    seq = await node_transitions(graph, _triage_initial(cid))

    assert_all_steps_light_something(seq)
    assert seq[:2] == ["ingest", "dispatch"]
    # the settled tail is always escalate/critic/synthesizer/score, in order
    assert seq[-4:] == ["escalate_check", "critic", "synthesizer", "risk_score"]
    # all four specialists streamed (fake proposes all four; floor keeps them)
    assert {"mandate", "kya", "log", "drift"} <= set(seq)
    assert "bump_round" not in seq  # no observations → no escalation round


async def test_triage_stream_with_escalation(store) -> None:
    cid = _seed(store, "case-006-drift.json")
    fake = make_graph_fake({"record_observations": {"observations": [
        {"note": "Issuer name looks unusual.", "cited_field": "issuer_name"}]}})
    graph = build_triage_graph(model=fake, store=store)
    seq = await node_transitions(graph, _triage_initial(cid))

    assert_all_steps_light_something(seq)
    # the loop is visible in the stream: settle → bump → re-dispatched agent
    # → settle again — and bump_round aliases onto dispatch (a re-dispatch)
    bump = seq.index("bump_round")
    assert "kya" in seq[bump:], "the escalated agent must stream after bump_round"
    assert seq.count("escalate_check") == 2
    assert seq[-3:] == ["critic", "synthesizer", "risk_score"]


async def test_directed_triage_streams_only_the_named_agent(store) -> None:
    cid = _seed(store, "case-005-structuring.json")
    graph = build_triage_graph(model=make_graph_fake(), store=store)
    await graph.ainvoke(_triage_initial(cid))

    seq = await node_transitions(graph, _triage_initial(
        cid, reviewer_directive=ReviewerDirective(instructions="look again", target_agents=["log"]),
    ))
    assert_all_steps_light_something(seq)
    assert set(seq) & {"mandate", "kya", "drift"} == set()
    assert "log" in seq
    assert "dispatch" not in seq[2:]  # no LLM proposal on a directed pass


async def test_investigation_stream_reply_only(store) -> None:
    cid = _seed(store, "case-001-compliant.json")
    await build_triage_graph(model=make_graph_fake(), store=store).ainvoke(_triage_initial(cid))
    fake = make_graph_fake({"route_supervisor_request": {
        "intent": "reply", "targets": [], "instruction": "", "context_blocks": [],
        "message_to_officer": "Nothing on record."}})
    graph = build_investigation_graph(model=fake, store=store)
    seq = await node_transitions(graph, {
        "case_id": cid, "officer_message": "what did KYA find?", "officer": "Ana",
        "findings": [], "observations": [], "messages": []})

    assert seq == ["load_context", "orchestrate", "record"]
    # every step folds onto the orchestrator: a reply lights the hub, only the hub
    assert {STEP_ALIAS[s] for s in seq} == {"orchestrator"}


async def test_investigation_stream_dispatches_investigator(store) -> None:
    cid = _seed(store, "case-006-drift.json")
    await build_triage_graph(model=make_graph_fake(), store=store).ainvoke(_triage_initial(cid))

    class Hybrid:
        def __init__(self):
            self.router = make_graph_fake({"route_supervisor_request": {
                "intent": "dispatch", "targets": ["investigator.lookup"],
                "instruction": "profile MER-BEF-005", "context_blocks": [],
                "message_to_officer": "Investigator on it."}})
            self.inv = ScriptedFake([
                [("get_counterparty_profile", {"counterparty_id": "MER-BEF-005"})],
                [("record_investigation_answer",
                  {"answer": "17 tx", "cited_evidence": [], "observations": []})],
            ])

        def bind(self, **kw):
            tools = [t["name"] for t in kw.get("tools", [])]
            return self.inv.bind(**kw) if "get_transactions" in tools else self.router.bind(**kw)

    graph = build_investigation_graph(model=Hybrid(), store=store)
    seq = await node_transitions(graph, {
        "case_id": cid, "officer_message": "who is MER-BEF-005?", "officer": "Ana",
        "findings": [], "observations": [], "messages": []})
    assert seq == ["load_context", "orchestrate", "investigator", "record"]
    assert_all_steps_light_something(seq)


async def test_investigation_stream_dispatches_specialist(store) -> None:
    cid = _seed(store, "case-005-structuring.json")
    await build_triage_graph(model=make_graph_fake(), store=store).ainvoke(_triage_initial(cid))
    fake = make_graph_fake({"route_supervisor_request": {
        "intent": "dispatch", "targets": ["log.analyze"],
        "instruction": "re-check the cluster", "context_blocks": [],
        "message_to_officer": "Asking Log."}})
    graph = build_investigation_graph(model=fake, store=store)
    seq = await node_transitions(graph, {
        "case_id": cid, "officer_message": "recheck same-day payments", "officer": "Ana",
        "findings": [], "observations": [], "messages": []})
    # architecture-v2 §14.2: a re-briefed specialist's output goes through
    # the same critic + synthesizer tail as a triage pass
    assert seq == ["load_context", "orchestrate", "log", "critic", "synthesizer", "record"]
    assert_all_steps_light_something(seq)


async def test_drafting_stream_holds_at_gate_then_resumes(store) -> None:
    cid = _seed(store, "case-002-mandate-breaching.json")
    fake = make_graph_fake()
    await build_triage_graph(model=fake, store=store).ainvoke(_triage_initial(cid))
    graph = build_drafting_graph(model=fake, store=store, checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "stream-gate"}}

    seq = await node_transitions(graph, {"case_id": cid, "messages": []}, cfg)
    assert seq == ["load_record", "draft_report", "grounding_check", "human_gate"]
    assert_all_steps_light_something(seq)

    resumed = await node_transitions(graph, Command(resume={
        "action": "approve", "reviewer": "Ana", "comment": None, "directive": None}), cfg)
    assert resumed == ["human_gate"]  # the held node completes, nothing else re-runs


async def test_drafting_stream_blocked_never_reaches_the_gate(store) -> None:
    cid = _seed(store, "case-001-compliant.json")
    await build_triage_graph(model=make_graph_fake(), store=store).ainvoke(_triage_initial(cid))
    fake = make_graph_fake({"draft_case_report": {
        "overall_assessment": "x",
        "sections": [{"title": "Ghost", "body": "b", "cited_finding_ids": ["F-INVENTED"]}],
        "open_observations_note": None}})
    graph = build_drafting_graph(model=fake, store=store, checkpointer=MemorySaver())
    seq = await node_transitions(graph, {"case_id": cid, "messages": []},
                                 {"configurable": {"thread_id": "stream-blocked"}})
    assert seq == ["load_record"] + ["draft_report", "grounding_check"] * 3
    assert "human_gate" not in seq  # nothing approvable — the gate never lights
