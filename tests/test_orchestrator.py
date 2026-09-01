"""Stage 8 — the conversational orchestrator + investigation graph."""
from __future__ import annotations

from agents.orchestrator import route
from data.loader import CASES_DIR, load_raw_case_json
from ledger import LedgerStore
from ledger.projection import project_case
from ledger.seed import submit_case
from pipeline.graph import run_investigation, run_triage
from tests.fakes import FakeChatModel, make_graph_fake
from tests.test_investigator import ScriptedFake

import pytest


@pytest.fixture
def store(tmp_path) -> LedgerStore:
    return LedgerStore(tmp_path / "ledger.db")


async def _triaged(store: LedgerStore, name: str = "case-006-drift.json") -> str:
    case_id = submit_case(store, load_raw_case_json(CASES_DIR / name))
    await run_triage(case_id, model=make_graph_fake(), store=store)
    return case_id


def _record(store: LedgerStore, case_id: str):
    return project_case(store.events_for(case_id))


# -- route() unit level ------------------------------------------------------


async def test_route_output_is_a_routing_decision_not_case_prose(store) -> None:
    """§9.7 structurally: the orchestrator's one tool has no field for a
    verdict — asked for an opinion, all it can emit is intent/targets/
    instruction/message."""
    case_id = await _triaged(store)
    fake = FakeChatModel({"route_supervisor_request": {
        "intent": "dispatch", "targets": ["log.analyze"],
        "instruction": "Re-examine the counterparty shift the officer is asking about.",
        "context_blocks": [], "message_to_officer": "I'll ask Log to look at that.",
    }})
    decision = await route("Is this firm structuring?", _record(store, case_id), model=fake)
    assert decision.intent == "dispatch"
    assert decision.targets == ["log.analyze"]
    assert set(decision.model_dump()) == {
        "intent", "targets", "instruction", "context_blocks", "message_to_officer",
    }  # no field through which an opinion on the firm could flow


async def test_invented_skills_are_dropped_and_degrade_to_reply(store) -> None:
    case_id = await _triaged(store)
    fake = FakeChatModel({"route_supervisor_request": {
        "intent": "dispatch", "targets": ["portfolio.sweep", "web.search"],
        "instruction": "x", "context_blocks": [], "message_to_officer": "On it.",
    }})
    decision = await route("sweep everything", _record(store, case_id), model=fake)
    assert decision.intent == "reply"
    assert decision.targets == []


# -- the investigation graph -------------------------------------------------


async def test_reply_intent_answers_without_dispatching_anyone(store) -> None:
    case_id = await _triaged(store)
    fake = make_graph_fake({"route_supervisor_request": {
        "intent": "reply", "targets": [], "instruction": "", "context_blocks": [],
        "message_to_officer": "KYA found nothing; the score is on the record.",
    }})
    calls_before = list(fake.call_log)
    record, reply = await run_investigation(case_id, "what did KYA find?", officer="Ana", model=fake, store=store)

    new_calls = fake.call_log[len(calls_before):]
    assert new_calls == ["route_supervisor_request"]  # nobody else ran
    assert reply == "KYA found nothing; the score is on the record."
    events = [e.event_type for e in store.events_for(case_id) if e.run_id and e.run_id.startswith("inv-")]
    assert events == ["run_started", "question_asked", "orchestrator_replied", "run_completed"]
    replied = next(e for e in store.events_for(case_id) if e.event_type == "orchestrator_replied")
    assert replied.payload["message"] == "KYA found nothing; the score is on the record."
    assert replied.payload["intent"] == "reply"
    assert store.events_for(case_id)[-1].event_type == "run_completed"


async def test_dispatch_to_a_specialist_records_briefing_and_findings(store) -> None:
    case_id = await _triaged(store, "case-005-structuring.json")
    anomalous = {
        "anomalous": True,
        "explanation": "Cluster of 2900.0/2850.0/2950.0 splits one 8700.0 settlement.",
        "cited_evidence": "sum 8700.0 vs threshold 3000.0",
    }
    clean = {"anomalous": False, "explanation": "n", "cited_evidence": "e"}
    fake = make_graph_fake({
        "route_supervisor_request": {
            "intent": "dispatch", "targets": ["log.analyze"],
            "instruction": "The officer asks whether the same-day payments share a beneficiary — look again.",
            "context_blocks": ["score"], "message_to_officer": "Dispatching Log with your question.",
        },
        "record_log_analysis": {
            "structuring": anomalous, "concentration": clean, "velocity": clean, "other_observations": [],
        },
    })
    record, reply = await run_investigation(
        case_id, "do the same-day payments share a beneficiary?", officer="Ana", model=fake, store=store,
    )

    # the specialist judged against its rules and produced a real Finding
    assert any(f.type == "transaction_structuring_detected" for f in record.findings)
    # the briefing was recorded with the officer-derived instruction and the
    # orchestrator-named block attached over the canonical base
    inv_run = record.runs[-1]
    assert inv_run.kind == "investigation"
    (dispatch,) = inv_run.dispatches
    assert dispatch.target == "log"
    assert "share a beneficiary" in dispatch.instruction
    blocks = dispatch.context_blocks
    assert "candidate_structuring_clusters" in blocks  # evidence floor intact
    assert blocks["supplementary_context"][0]["block_id"] == "score"
    # the instruction reached the model's system prompt
    assert "share a beneficiary" in fake.last_messages_for("record_log_analysis")[0].content
    # and the score was recomputed since findings changed
    assert record.risk_score.total > 0
    # the run's output went through the critic, scoped to THIS run
    critic_events = [e for e in store.events_for(case_id)
                     if e.event_type == "critic_checked" and e.run_id == inv_run.run_id]
    assert any(e.payload["target"] == "log" for e in critic_events)


async def test_dispatch_to_the_investigator_records_answer_and_trail(store) -> None:
    case_id = await _triaged(store)

    class Hybrid:
        """route via FakeChatModel; investigator via ScriptedFake."""

        def __init__(self):
            self.router = make_graph_fake({"route_supervisor_request": {
                "intent": "dispatch", "targets": ["investigator.lookup"],
                "instruction": "When did MER-BEF-005 first appear and how big is it now?",
                "context_blocks": [], "message_to_officer": "I'll have the investigator look it up.",
            }})
            self.investigator = ScriptedFake([
                [("get_counterparty_profile", {"counterparty_id": "MER-BEF-005"})],
                [("record_investigation_answer", {
                    "answer": "First seen 2026-07-11; 17 transactions totalling 5558.40.",
                    "cited_evidence": ["first_seen 2026-07-11", "total 5558.40"],
                    "observations": [],
                })],
            ])

        def bind(self, **kwargs):
            tools = [t["name"] for t in kwargs.get("tools", [])]
            if "get_transactions" in tools:
                return self.investigator.bind(**kwargs)
            return self.router.bind(**kwargs)

    record, reply = await run_investigation(
        case_id, "who is Batumi Express Freight?", officer="Ana", model=Hybrid(), store=store,
    )

    (answer,) = record.answers
    assert answer.question == "When did MER-BEF-005 first appear and how big is it now?"
    assert [t.tool for t in answer.tool_calls] == ["get_counterparty_profile"]
    assert record.status == "under_review"  # question answered, case live
    assert record.open_questions == []
    # the investigator produced no findings — score untouched at 0 events
    inv_events = [e for e in store.events_for(case_id) if e.run_id and e.run_id.startswith("inv-")]
    assert not any(e.event_type == "finding_recorded" for e in inv_events)
    assert store.verify() == []


async def test_run_triage_intent_passes_through_for_the_caller(store) -> None:
    """"run the full review" in chat: the orchestrator routes, the CALLER
    (the UI) starts the triage run — nothing dispatches inside this graph."""
    case_id = await _triaged(store)
    fake = make_graph_fake({"route_supervisor_request": {
        "intent": "run_triage", "targets": [], "instruction": "", "context_blocks": [],
        "message_to_officer": "Starting a full triage pass now.",
    }})
    calls_before = list(fake.call_log)
    record, reply = await run_investigation(case_id, "run the full review again", officer="Ana", model=fake, store=store)
    assert fake.call_log[len(calls_before):] == ["route_supervisor_request"]
    assert reply == "Starting a full triage pass now."
    replied = [e for e in store.events_for(case_id) if e.event_type == "orchestrator_replied"][-1]
    assert replied.payload["intent"] == "run_triage"
