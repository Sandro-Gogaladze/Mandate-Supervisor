"""The conversational orchestrator + investigation graph on the dossier."""
from __future__ import annotations

from agents.orchestrator import close_out, first_pass_decision, route
from ledger import LedgerStore
from ledger.projection import project_case
from pipeline.graph import run_investigation, run_triage
from tests.corpus import HAL, KST, seed
from tests.fakes import CLEAN_VERDICT, FakeChatModel, make_graph_fake
from tests.test_investigator import ScriptedFake
from agents.llm import message_text


async def _triaged(store: LedgerStore, path=KST) -> str:
    case_id = seed(store, path)
    await run_triage(case_id, model=make_graph_fake(), store=store)
    return case_id


def _record(store, case_id):
    return project_case(store.events_for(case_id))


def test_first_pass_routing_is_deterministic_and_complete() -> None:
    decision = first_pass_decision()

    assert decision.intent == "dispatch"
    # Systemic is in the first-pass set: "is this agent part of something
    # larger?" is context for the verdict, not an afterthought to it. Control
    # Assurance is absent because the graph runs it after the fan-out (its
    # rules need the peers' facts), and the Red Team because it generates
    # probes rather than reading the submission.
    assert decision.targets == [
        "mandate.review", "kya.review", "provenance.review", "injection.review",
        "counterparty.review", "consent.review", "log.analyze", "drift.analyze",
        "systemic.review",
    ]


async def test_route_output_is_a_routing_decision_not_case_prose(store) -> None:
    case_id = await _triaged(store)
    fake = FakeChatModel({"route_supervisor_request": {
        "intent": "dispatch", "targets": ["log.analyze"],
        "instruction": "Re-examine the concentration the officer is asking about.",
        "context_blocks": [], "message_to_officer": "I'll ask Log to look at that."}})
    decision = await route("Is this agent structuring?", _record(store, case_id), model=fake)
    assert decision.intent == "dispatch" and decision.targets == ["log.analyze"]
    # a routing decision: skills with briefings and a message — no field for a verdict
    assert set(decision.model_dump()) == {"reasoning", "intent", "message_to_officer", "dispatches", "raw"}
    assert decision.dispatches[0].instruction.startswith("Re-examine")


async def test_invented_skills_are_dropped_and_degrade_to_reply(store) -> None:
    case_id = await _triaged(store)
    fake = FakeChatModel({"route_supervisor_request": {
        "intent": "dispatch", "targets": ["portfolio.sweep", "web.search"],
        "instruction": "x", "context_blocks": [], "message_to_officer": "On it."}})
    decision = await route("sweep everything", _record(store, case_id), model=fake)
    assert decision.intent == "reply" and decision.targets == []


async def test_reply_intent_answers_without_dispatching_anyone(store) -> None:
    case_id = await _triaged(store, HAL)
    fake = make_graph_fake({"route_supervisor_request": {
        "intent": "reply", "targets": [], "instruction": "", "context_blocks": [],
        "message_to_officer": "KYA found nothing; the score is on the record."}})
    calls_before = list(fake.call_log)
    record, reply = await run_investigation(case_id, "what did KYA find?", officer="Ana", model=fake, store=store)
    assert fake.call_log[len(calls_before):] == ["route_supervisor_request"]
    assert reply == "KYA found nothing; the score is on the record."
    events = [e.event_type for e in store.events_for(case_id) if e.run_id and e.run_id.startswith("inv-")]
    assert events == ["run_started", "question_asked", "dispatch_planned", "orchestrator_replied", "run_completed"]


async def test_dispatch_to_a_specialist_records_briefing_and_a_superseding_assessment(store) -> None:
    case_id = await _triaged(store)
    anomalous = {"anomalous": True,
                 "explanation": "The largest counterparty holds 2735.0 of 20113.5 across 102 transactions.",
                 "cited_evidence": "total 2735.0 of 20113.5", "transaction_ids": ["TXN-KST-0001"]}
    fake = make_graph_fake({
        "route_supervisor_request": {
            "intent": "dispatch", "targets": ["log.analyze"],
            "instruction": "The officer asks whether spend is concentrated — look again.",
            "context_blocks": ["score"], "message_to_officer": "Dispatching Log with your question."},
        "record_log_analysis": {"structuring": CLEAN_VERDICT, "concentration": anomalous,
                                "velocity": CLEAN_VERDICT, "other_observations": []},
    })
    record, reply = await run_investigation(case_id, "is spend concentrated?", officer="Ana", model=fake, store=store)
    current = [a for a in record.assessments if a.rule_id == "LOG-CON-01" and a.round == 2]
    assert len(current) == 1 and current[0].verdict == "breach" and current[0].supersedes.endswith(":r1")
    inv_run = record.runs[-1]
    dispatch = next(d for d in inv_run.dispatches if d.target == "log")
    assert dispatch.target == "log" and "concentrated" in dispatch.instruction
    assert "candidate_structuring_clusters" in dispatch.context_blocks
    assert dispatch.context_blocks["supplementary_context"][0]["block_id"] == "score"
    assert "concentrated" in message_text(fake.last_messages_for("record_log_analysis")[0])
    assert record.risk_score.total > 3.4
    critic_events = [e for e in store.events_for(case_id)
                     if e.event_type == "critic_checked" and e.run_id == inv_run.run_id]
    assert any(e.payload["target"] == "log" and e.payload["passed"] for e in critic_events)


async def test_dispatch_to_the_investigator_records_answer_and_trail(store) -> None:
    case_id = await _triaged(store)

    class Hybrid:
        def __init__(self):
            self.router = make_graph_fake({"route_supervisor_request": {
                "intent": "dispatch", "targets": ["investigator.lookup"],
                "instruction": "When did MER-QVC-8801 first appear and how big is it now?",
                "context_blocks": [], "message_to_officer": "I'll have the investigator look it up."}})
            self.investigator = ScriptedFake([
                [("get_counterparty_profile", {"counterparty_id": "MER-QVC-8801"})],
                [("record_investigation_answer", {
                    "answer": "First seen 2026-08-05; 4 transactions totalling 2312.0.",
                    "cited_evidence": ["first_seen 2026-08-05", "total 2312.0"], "observations": []})],
            ])

        def bind(self, **kwargs):
            tools = [t["name"] for t in kwargs.get("tools", [])]
            return self.investigator.bind(**kwargs) if "get_transactions" in tools else self.router.bind(**kwargs)

    record, reply = await run_investigation(case_id, "who is Quickvale?", officer="Ana", model=Hybrid(), store=store)
    (answer,) = record.answers
    assert [t.tool for t in answer.tool_calls] == ["get_counterparty_profile"]
    assert record.status == "under_review" and record.open_questions == []
    inv_events = [e for e in store.events_for(case_id) if e.run_id and e.run_id.startswith("inv-")]
    assert not any(e.event_type in ("finding_recorded", "assessment_recorded") for e in inv_events)
    assert store.verify() == []


async def test_asking_for_the_review_again_is_a_dispatch_of_every_review_skill(store) -> None:
    """There is no separate 'run triage' intent: 'run it again' is the
    orchestrator dispatching the first-pass set through the same graph."""
    case_id = await _triaged(store, HAL)
    fake = make_graph_fake({"route_supervisor_request": {
        "reasoning": "a full pass", "intent": "run_triage", "dispatches": [],
        "message_to_officer": "Starting a full pass now."}})
    record, reply = await run_investigation(case_id, "run the full review again", officer="Ana", model=fake, store=store)
    assert reply == "Starting a full pass now."
    replied = [e for e in store.events_for(case_id) if e.event_type == "orchestrator_replied"][-1]
    assert replied.payload["intent"] == "dispatch" and len(replied.payload["targets"]) == 9
    assert record.runs[-1].kind == "investigation" and record.runs[-1].completed_at


async def test_draft_report_intent_passes_through_for_the_caller(store) -> None:
    case_id = await _triaged(store, HAL)
    fake = make_graph_fake({"route_supervisor_request": {
        "reasoning": "they want the report", "intent": "draft_report", "dispatches": [],
        "message_to_officer": "Drafting the report now."}})
    record, reply = await run_investigation(case_id, "draft the report", officer="Ana", model=fake, store=store)
    assert reply == "Drafting the report now."
    assert [e for e in store.events_for(case_id) if e.event_type == "orchestrator_replied"][-1].payload["intent"] == "draft_report"


async def test_control_assurance_cannot_be_dispatched_and_invented_runs_are_dropped(store) -> None:
    case_id = await _triaged(store, HAL)
    fake = FakeChatModel({"route_supervisor_request": {
        "reasoning": "x", "intent": "dispatch", "message_to_officer": "on it",
        "dispatches": [{"skill": "control_assurance.review", "instruction": "check"},
                       {"skill": "log.analyze", "instruction": "look", "run_scope": ["RUN-2026-0813-0015", "RUN-NOT-REAL"]}]}})
    decision = await route("check the controls on run 15", _record(store, case_id), model=fake,
                           known_runs={"RUN-2026-0813-0015"})
    assert decision.targets == ["log.analyze"]
    assert decision.dispatches[0].run_scope == ["RUN-2026-0813-0015"]


async def test_first_pass_does_not_call_router_and_runs_every_review_skill(store) -> None:
    case_id = seed(store, HAL)
    fake = make_graph_fake({"route_supervisor_request": {
        "reasoning": "skipping drift, the baseline is thin", "intent": "dispatch", "message_to_officer": "Running seven.",
        "dispatches": [{"skill": s, "instruction": ""} for s in
                       ("mandate.review", "kya.review", "provenance.review", "injection.review",
                        "counterparty.review", "consent.review", "log.analyze")]}})
    record = await run_triage(case_id, model=fake, store=store)
    plan = record.runs[-1].plan
    assert plan.first_pass and plan.not_dispatched == []
    assert "route_supervisor_request" not in fake.call_log
    assert {d.target for d in record.runs[-1].dispatches} >= {
        "mandate", "kya", "provenance", "injection", "counterparty",
        "consent", "log", "drift", "control_assurance",
    }


async def test_an_orchestrator_call_that_fails_completes_the_turn_and_says_so(store) -> None:
    """The model, the network or the account can fail. The run still ends,
    the failure is on the record, and the officer is told nothing ran."""
    class Broken:
        def bind(self, **_kw):
            return self

        async def ainvoke(self, *_a, **_kw):
            raise RuntimeError("Your credit balance is too low to access the Anthropic API.")

    case_id = await _triaged(store, HAL)
    record, reply = await run_investigation(
        case_id, "re-check the unusual payment", officer="Ana", model=Broken(), store=store,
    )
    run = record.runs[-1]
    assert run.kind == "investigation"
    assert run.completed_at and run.plan.intent == "reply" and run.plan.skills == []
    assert "could not reach the model" in reply
    events = [e for e in store.events_for(case_id) if e.run_id == run.run_id]
    failed = next(e for e in events if e.event_type == "specialist_failed")
    assert failed.payload["agent"] == "orchestrator" and failed.payload["error"] == "RuntimeError"
    replied = next(e for e in events if e.event_type == "orchestrator_replied")
    assert "could not reach the model" in replied.payload["message"] and replied.payload["targets"] == []
    assert not any(e.event_type == "dispatch_recorded" for e in events)


# ---------------------------------------------------------------------------
# The closing brief
# ---------------------------------------------------------------------------


async def test_the_orchestrator_closes_the_turn_over_the_finished_record(store) -> None:
    """After the specialists, the critic and the synthesizer, the orchestrator
    speaks once — over a recommendation that is already on the record, with
    counts it was handed rather than counts it worked out."""
    case_id = await _triaged(store)
    events = store.events_for(case_id)
    order = [e.event_type for e in events]
    brief = next(e for e in events if e.event_type == "orchestrator_summarised")
    rec = next(e for e in events if e.event_type == "authorisation_computed")

    assert brief.actor == "agent:orchestrator"
    # It cannot describe a recommendation that does not exist yet.
    assert order.index("authorisation_computed") < order.index("orchestrator_summarised")
    assert brief.payload["breach_count"] == len(rec.payload["factors"])
    assert brief.payload["disposition"] == rec.payload["disposition"]
    real = {f.rule_id for f in _record(store, case_id).findings}
    assert set(brief.payload["main_risks"]) <= real


async def test_a_closing_brief_cannot_name_a_rule_no_finding_supports(store) -> None:
    case_id = await _triaged(store)
    record = _record(store, case_id)
    rec = next(e for e in store.events_for(case_id) if e.event_type == "authorisation_computed").payload
    fake = FakeChatModel({"record_closing_brief": {
        "reasoning": "…", "message_to_officer": "Two breaches; open the findings list.",
        "main_risks": ["MND-CAP-01", "NOT-A-RULE"]}})

    brief = await close_out(rec, record.findings, score=record.risk_score, model=fake)

    assert "NOT-A-RULE" not in brief.main_risks
    assert set(brief.main_risks) <= {f.rule_id for f in record.findings}
    # The counts stay code's either way — the model never supplied them.
    assert brief.breach_count == len(rec["factors"])


async def test_a_closing_brief_that_fails_costs_a_sentence_not_the_run(store) -> None:
    """It reads a record that is already final, so its failure must not take
    the recommendation, the score or the run down with it."""
    class BrokenAtTheEnd:
        """Every call the graph makes works, except the closing brief."""

        def __init__(self, inner, broken: bool = False) -> None:
            self.inner, self.broken = inner, broken

        def bind(self, **kwargs):
            tools = kwargs.get("tools") or []
            return BrokenAtTheEnd(self.inner.bind(**kwargs),
                                  bool(tools) and tools[0]["name"] == "record_closing_brief")

        async def ainvoke(self, messages):
            if self.broken:
                raise RuntimeError("overloaded_error")
            return await self.inner.ainvoke(messages)

    case_id = seed(store, KST)
    await run_triage(case_id, model=BrokenAtTheEnd(make_graph_fake()), store=store)

    events = [e.event_type for e in store.events_for(case_id)]
    assert "orchestrator_summarised" not in events
    assert "authorisation_computed" in events and events[-1] == "run_completed"
    assert _record(store, case_id).risk_score is not None
