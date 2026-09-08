"""The step-event contract the supervision map depends on.

ag_ui_langgraph derives STEP_STARTED/STEP_FINISHED from `langgraph_node`
metadata *transitions* on the event stream. The UI lights map nodes from
those step names through its STEP_ALIAS table. This suite pins both ends
server-side: the exact node-transition sequence per run type, and that
every step name the backend can emit is either a map node id or an aliased
plumbing step.
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from pipeline.graph import build_drafting_graph, build_investigation_graph, build_triage_graph
from schemas import ReviewerDirective
from tests.corpus import HAL, seed
from tests.fakes import make_graph_fake
from tests.test_investigator import ScriptedFake

# Mirror of dashboard/src/components/CaseReview.tsx::STEP_ALIAS — keep in
# sync by hand; this test exists so a drift breaks visibly.
STEP_ALIAS: dict[str, str | None] = {
    "orchestrate": "orchestrator", "record": "orchestrator", "ingest": "orchestrator",
    "specialists_done": None, "critic": "findings",
    "load_record": "draft_report",
}
MAP_NODE_IDS = {
    "orchestrator", "mandate", "kya", "log", "drift", "investigator",
    "findings", "synthesizer", "draft_report", "grounding_check", "human_gate",
}


async def node_transitions(graph, initial, config=None) -> list[str]:
    seq: list[str] = []
    current = None
    async for ev in graph.astream_events(initial, config or {}, version="v2"):
        node = (ev.get("metadata") or {}).get("langgraph_node")
        if node and node != current:
            seq.append(node)
            current = node
    return seq


MAP_NODE_IDS.update({"consent", "counterparty", "provenance", "injection", "control_assurance", "systemic"})

def assert_all_steps_light_something(transitions: list[str]) -> None:
    for step in transitions:
        target = STEP_ALIAS[step] if step in STEP_ALIAS else step
        if target is None:
            continue  # plumbing the map deliberately ignores
        assert target in MAP_NODE_IDS, f"step {step!r} maps to {target!r}, which is not a map node"


def _triage_initial(cid, **extra):
    return {"case_id": cid, "facts": [], "assessments": [], "findings": [], "observations": [],
            "messages": [], "first_pass": True, **extra}


def _question_initial(cid, message, **extra):
    return {"case_id": cid, "facts": [], "assessments": [], "findings": [], "observations": [],
            "messages": [], "first_pass": False, "officer_message": message, "officer": "Ana", **extra}


async def test_triage_stream_clean_case(store) -> None:
    cid = seed(store, HAL)
    seq = await node_transitions(build_triage_graph(model=make_graph_fake(), store=store), _triage_initial(cid))
    assert_all_steps_light_something(seq)
    assert seq[:2] == ["ingest", "orchestrate"]
    assert seq[-5:] == ["specialists_done", "control_assurance", "critic", "synthesizer", "record"]
    assert {"mandate", "kya", "log", "drift"} <= set(seq)



async def test_directed_triage_streams_only_the_named_agent(store) -> None:
    cid = seed(store)
    graph = build_triage_graph(model=make_graph_fake(), store=store)
    await graph.ainvoke(_triage_initial(cid))
    seq = await node_transitions(graph, _triage_initial(
        cid, reviewer_directive=ReviewerDirective(instructions="look again", target_agents=["log"])))
    assert_all_steps_light_something(seq)
    assert set(seq) & {"mandate", "kya", "drift"} == set() and "log" in seq
    assert seq[:2] == ["ingest", "orchestrate"]


async def test_investigation_stream_reply_only(store) -> None:
    cid = seed(store, HAL)
    await build_triage_graph(model=make_graph_fake(), store=store).ainvoke(_triage_initial(cid))
    fake = make_graph_fake({"route_supervisor_request": {
        "intent": "reply", "targets": [], "instruction": "", "context_blocks": [],
        "message_to_officer": "Nothing on record."}})
    seq = await node_transitions(build_investigation_graph(model=fake, store=store),
                                 _question_initial(cid, "what did KYA find?"))
    assert seq == ["ingest", "orchestrate", "record"]
    assert {STEP_ALIAS[s] for s in seq} == {"orchestrator"}


async def test_investigation_stream_dispatches_investigator(store) -> None:
    cid = seed(store)
    await build_triage_graph(model=make_graph_fake(), store=store).ainvoke(_triage_initial(cid))

    class Hybrid:
        def __init__(self):
            self.router = make_graph_fake({"route_supervisor_request": {
                "intent": "dispatch", "targets": ["investigator.lookup"],
                "instruction": "profile MER-QVC-8801", "context_blocks": [],
                "message_to_officer": "Investigator on it."}})
            self.inv = ScriptedFake([
                [("get_counterparty_profile", {"counterparty_id": "MER-QVC-8801"})],
                [("record_investigation_answer", {"answer": "4 tx", "cited_evidence": [], "observations": []})],
            ])

        def bind(self, **kw):
            tools = [t["name"] for t in kw.get("tools", [])]
            return self.inv.bind(**kw) if "get_transactions" in tools else self.router.bind(**kw)

    seq = await node_transitions(build_investigation_graph(model=Hybrid(), store=store),
                                 _question_initial(cid, "who is MER-QVC-8801?"))
    assert seq == ["ingest", "orchestrate", "investigator", "specialists_done", "synthesizer", "record"]
    assert_all_steps_light_something(seq)


async def test_investigation_stream_dispatches_specialist(store) -> None:
    cid = seed(store)
    await build_triage_graph(model=make_graph_fake(), store=store).ainvoke(_triage_initial(cid))
    fake = make_graph_fake({"route_supervisor_request": {
        "intent": "dispatch", "targets": ["log.analyze"], "instruction": "re-check concentration",
        "context_blocks": [], "message_to_officer": "Asking Log."}})
    seq = await node_transitions(build_investigation_graph(model=fake, store=store),
                                 _question_initial(cid, "is spend concentrated?"))
    assert seq == ["ingest", "orchestrate", "log", "specialists_done", "control_assurance", "critic", "synthesizer", "record"]
    assert_all_steps_light_something(seq)


async def test_drafting_stream_holds_at_gate_then_resumes(store) -> None:
    cid = seed(store)
    fake = make_graph_fake()
    await build_triage_graph(model=fake, store=store).ainvoke(_triage_initial(cid))
    graph = build_drafting_graph(model=fake, store=store, checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "stream-gate"}}
    seq = await node_transitions(graph, {"case_id": cid, "messages": []}, cfg)
    assert seq == ["load_record", "draft_report", "grounding_check", "human_gate"]
    assert_all_steps_light_something(seq)
    resumed = await node_transitions(graph, Command(resume={
        "action": "approve", "reviewer": "Ana", "comment": None, "directive": None}), cfg)
    assert resumed == ["human_gate"]


async def test_drafting_stream_reaches_the_gate_even_when_grounding_complains(store) -> None:
    """Grounding is advisory: the run walks the same path either way, and the
    officer who asked for a report always gets one to decide on."""
    cid = seed(store, HAL)
    await build_triage_graph(model=make_graph_fake(), store=store).ainvoke(_triage_initial(cid))
    fake = make_graph_fake({"draft_case_report": {
        "overall_assessment": "x",
        "sections": [{"title": "Ghost", "body": "b", "cited_finding_ids": ["F-INVENTED"]}],
        "open_observations_note": None}})
    graph = build_drafting_graph(model=fake, store=store, checkpointer=MemorySaver())
    seq = await node_transitions(graph, {"case_id": cid, "messages": []},
                                 {"configurable": {"thread_id": "stream-flagged"}})
    assert seq == ["load_record", "draft_report", "grounding_check", "human_gate"]
    assert_all_steps_light_something(seq)
