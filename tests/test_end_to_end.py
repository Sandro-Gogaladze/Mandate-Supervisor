"""The demo, as a test (architecture-v2 §20): submit → triage → open →
question → directed pass → draft → sign — then the chain verifies and the
projected status is `issued`. If this passes, the story the judges see is
real end to end, against fakes, with zero live calls."""
from __future__ import annotations

import json

from data.loader import CASES_DIR, load_raw_case_json
from ledger import LedgerStore
from ledger.projection import project_case
from ledger.seed import submit_case
from pipeline.graph import resolve_gate, run_investigation, run_triage, start_drafting
from schemas import ReviewerDirective
from tests.fakes import CLEAN_VERDICT, make_graph_fake
from tests.test_investigator import ScriptedFake


class DemoModel:
    """Routes model calls: the orchestrator/specialists/drafter go through
    the comprehensive graph fake; the investigator (recognisable by its
    bound lookup tools) through a scripted loop."""

    def __init__(self):
        anomalous = {
            "anomalous": True,
            "explanation": "Payments of 2900.0, 2850.0 and 2950.0 sum to 8700.0, each under the 3000.0 threshold.",
            "cited_evidence": "cluster sum 8700.0 vs threshold 3000.0",
        }
        self.graph_fake = make_graph_fake({
            "route_supervisor_request": {
                "intent": "dispatch", "targets": ["investigator.lookup"],
                "instruction": "Profile the counterparty receiving the same-day payments.",
                "context_blocks": ["score"],
                "message_to_officer": "I'll have the investigator profile that counterparty.",
            },
            # the directed pass flips Log's judgment — a genuinely new finding
            "record_log_analysis": {
                "structuring": anomalous, "concentration": CLEAN_VERDICT,
                "velocity": CLEAN_VERDICT, "other_observations": [],
            },
        })
        self.investigator_fake = ScriptedFake([
            [("get_counterparty_profile", {"counterparty_id": "MER-GIE-001"})],
            [("record_investigation_answer", {
                "answer": "All three same-day payments go to one counterparty; totals in line with prior single settlements.",
                "cited_evidence": ["3 payments", "same counterparty"],
                "observations": [],
            })],
        ])

    def bind(self, **kwargs):
        tools = [t["name"] for t in kwargs.get("tools", [])]
        if "get_transactions" in tools:
            return self.investigator_fake.bind(**kwargs)
        return self.graph_fake.bind(**kwargs)


async def test_the_full_supervision_story(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.db")
    model = DemoModel()

    # 1 · submit — the bundle lands in the ledger, whole
    case_id = submit_case(store, load_raw_case_json(CASES_DIR / "case-005-structuring.json"))

    # 2 · triage, automatically — Log's fake stays clean this pass, so the
    # first pass surfaces nothing (the officer will dig)
    first_pass = make_graph_fake()
    record = await run_triage(case_id, model=first_pass, store=store)
    assert record.status == "triaged"
    assert record.findings == []

    # 3 · the officer opens the case
    store.append(case_id=case_id, event_type="case_opened", payload={}, actor="human:Ana Dvaladze")

    # 4 · a question — orchestrator routes to the investigator
    record, reply = await run_investigation(
        case_id, "who receives the three same-day payments?", officer="Ana Dvaladze",
        model=model, store=store,
    )
    assert "investigator" in reply.lower()
    assert len(record.answers) == 1
    assert record.status == "under_review"

    # 5 · a directed pass — Log re-examines with the officer's concern and
    # this time judges the cluster deliberate
    record = await run_triage(
        case_id, model=model, store=store,
        directive=ReviewerDirective(
            instructions="Treat the same-day cluster as potential threshold avoidance and judge it explicitly.",
            target_agents=["log"],
        ),
    )
    assert any(f.type == "transaction_structuring_detected" for f in record.findings)
    assert record.risk_score.total > 0

    # 6 · the report, on demand — grounded, held at the gate
    graph, config, state = await start_drafting(case_id, model=model, store=store)
    (intr,) = state["__interrupt__"]
    assert intr.value["reason"] == "report_approval"
    assert project_case(store.events_for(case_id)).status == "pending_decision"

    # 7 · the named signature
    end = await resolve_gate(graph, config, {
        "action": "approve", "reviewer": "Ana Dvaladze",
        "comment": "Structuring confirmed on directed review.", "directive": None,
    })
    assert end["report_status"] == "issued"

    # The record: five runs' worth of events, every actor attributed, the
    # chain intact, the status derived — not stored — as issued.
    record = project_case(store.events_for(case_id))
    assert record.status == "issued"
    assert [r.kind for r in record.runs] == ["triage", "investigation", "triage", "drafting"]
    assert record.decisions[-1].reviewer == "Ana Dvaladze"
    assert store.verify() == []

    actors = {e.actor for e in store.events_for(case_id)}
    assert "human:Ana Dvaladze" in actors
    assert "agent:log" in actors and "agent:investigator" in actors and "agent:orchestrator" in actors

    # and the export round-trips as data
    lines = list(store.export_jsonl(case_id))
    assert all(json.loads(line)["case_id"] == case_id for line in lines)
