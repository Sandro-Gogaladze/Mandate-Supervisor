"""The demo, as a test: submit → triage → open → question → directed pass →
draft → sign — then the chain verifies and the projected status is `issued`.
If this passes, the story the judges see is real end to end, against fakes,
with zero live calls."""
from __future__ import annotations

import json

from ledger import LedgerStore
from ledger.projection import project_case
from pipeline.graph import resolve_gate, run_investigation, run_triage, start_drafting
from schemas import ReviewerDirective
from tests.corpus import seed
from tests.fakes import CLEAN_VERDICT, make_graph_fake
from tests.test_investigator import ScriptedFake


class DemoModel:
    """Routes model calls: the orchestrator/specialists/drafter go through
    the comprehensive graph fake; the investigator (recognisable by its
    bound lookup tools) through a scripted loop."""

    def __init__(self):
        anomalous = {
            "anomalous": True,
            "explanation": "Quickvale Direct takes 2312.0 of 20113.5, first seen weeks before the window closed.",
            "cited_evidence": "total 2312.0",
            "transaction_ids": ["TXN-KST-0045"],
        }
        self.graph_fake = make_graph_fake({
            "route_supervisor_request": {
                "intent": "dispatch", "targets": ["investigator.lookup"],
                "instruction": "Profile the counterparty that appeared late in the window.",
                "context_blocks": ["score"],
                "message_to_officer": "I'll have the investigator profile that counterparty.",
            },
            "record_log_analysis": {
                "structuring": CLEAN_VERDICT, "concentration": anomalous,
                "velocity": CLEAN_VERDICT, "other_observations": [],
            },
        })
        self.investigator_fake = ScriptedFake([
            [("get_counterparty_profile", {"counterparty_id": "MER-QVC-8801"})],
            [("record_investigation_answer", {
                "answer": "Quickvale Direct: 4 settled transactions, beneficial owner unresolved.",
                "cited_evidence": ["4 transactions", "beneficial_owner_unresolved"],
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

    # 1 · submit — the dossier lands in the ledger, whole, ground truth withheld
    case_id = seed(store)

    # 2 · triage — the floor finds the planted mandate and credential defects
    record = await run_triage(case_id, model=make_graph_fake(), store=store)
    assert record.status == "triaged"
    assert {a.rule_id for a in record.assessments if a.verdict == "breach" and a.agent in ("mandate", "kya")} == {
        "KYA-LIF-04", "MND-CAP-01", "MND-CAP-02", "MND-CAP-05", "MND-USE-01"}

    # 3 · the officer opens the case
    store.append(case_id=case_id, event_type="case_opened", payload={}, actor="human:Ana Dvaladze")

    # 4 · a question — orchestrator routes to the investigator
    record, reply = await run_investigation(
        case_id, "who is the counterparty that appeared in August?", officer="Ana Dvaladze",
        model=model, store=store,
    )
    assert "investigator" in reply.lower() and len(record.answers) == 1
    assert record.status == "under_review"

    # 5 · a directed pass — Log re-examines and this time judges concentration reportable
    before = record.risk_score.total
    record = await run_triage(
        case_id, model=model, store=store,
        directive=ReviewerDirective(
            instructions="Treat the late-arriving counterparty's share as potential concentration.",
            target_agents=["log"]),
    )
    assert any(a.rule_id == "LOG-CON-01" and a.verdict == "breach" for a in record.assessments)
    assert record.risk_score.total > before

    # 6 · the report, on demand — grounded, held at the gate
    graph, config, state = await start_drafting(case_id, model=model, store=store)
    (intr,) = state["__interrupt__"]
    assert intr.value["reason"] == "report_approval"
    assert project_case(store.events_for(case_id)).status == "pending_decision"

    # 7 · the named signature
    end = await resolve_gate(graph, config, {
        "action": "approve", "reviewer": "Ana Dvaladze",
        "comment": "Concentration confirmed on directed review.", "directive": None,
    })
    assert end["report_status"] == "issued"

    record = project_case(store.events_for(case_id))
    assert record.status == "issued"
    assert [r.kind for r in record.runs] == ["triage", "investigation", "triage", "drafting"]
    assert record.decisions[-1].reviewer == "Ana Dvaladze"
    assert store.verify() == []
    actors = {e.actor for e in store.events_for(case_id)}
    assert {"human:Ana Dvaladze", "agent:log", "agent:investigator", "agent:orchestrator"} <= actors
    lines = list(store.export_jsonl(case_id))
    assert all(json.loads(line)["case_id"] == case_id for line in lines)
