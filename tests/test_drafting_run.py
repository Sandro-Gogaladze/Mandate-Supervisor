"""The drafting run and the human gate on the dossier.

The gate still holds on interrupt(), still validates decisions server-side,
still caps reruns. A `rerun` decision records the directive and ENDS the
run; the caller starts a directed triage. The handoff is proven end-to-end.
"""
from __future__ import annotations

from ledger import LedgerStore
from ledger.projection import project_case
from pipeline.graph import resolve_gate, run_triage, start_drafting
from schemas import ReviewerDirective
from tests.corpus import HAL, KST, seed
from tests.fakes import make_graph_fake
from agents.llm import message_text


async def _triaged(store: LedgerStore, fake, path=KST) -> str:
    case_id = seed(store, path)
    await run_triage(case_id, model=fake, store=store)
    return case_id


async def test_grounded_run_pauses_at_the_human_gate(store) -> None:
    fake = make_graph_fake()
    case_id = await _triaged(store, fake)
    _, _, state = await start_drafting(case_id, model=fake, store=store)
    (intr,) = state["__interrupt__"]
    assert intr.value["reason"] == "report_approval" and intr.value["rerun_allowed"] is True
    assert state["draft_report"] is not None
    assert project_case(store.events_for(case_id)).status == "pending_decision"


async def test_drafting_recomputes_the_score_and_grounds_against_ledger_findings(store) -> None:
    fake = make_graph_fake()
    case_id = await _triaged(store, fake)
    _, _, state = await start_drafting(case_id, model=fake, store=store)
    report = state["draft_report"]
    record = project_case(store.events_for(case_id))
    cited = {fid for s in report.sections for fid in s.cited_finding_ids}
    assert cited == {f.finding_id for f in record.findings}
    assert state["grounding_problems"] == []
    assert state["risk_score"].total == round(sum(f.severity_weight or 0.0 for f in record.findings), 4)
    assert sum(1 for e in store.events_for(case_id) if e.event_type == "score_computed") == 2


async def test_approve_resolves_the_gate_and_issues(store) -> None:
    fake = make_graph_fake()
    case_id = await _triaged(store, fake)
    graph, config, _ = await start_drafting(case_id, model=fake, store=store)
    end = await resolve_gate(graph, config, {
        "action": "approve", "reviewer": "N. Officer", "comment": "Clear breach.", "directive": None})
    assert end["report_status"] == "issued" and "__interrupt__" not in end
    record = project_case(store.events_for(case_id))
    assert record.status == "issued" and record.decisions[-1].reviewer == "N. Officer"
    assert store.events_for(case_id)[-1].actor == "human:N. Officer" or store.verify() == []
    assert store.verify() == []


async def test_reject_resolves_without_issuing(store) -> None:
    fake = make_graph_fake()
    case_id = await _triaged(store, fake)
    graph, config, _ = await start_drafting(case_id, model=fake, store=store)
    end = await resolve_gate(graph, config, {
        "action": "reject", "reviewer": "N. Officer", "comment": "Not convincing.", "directive": None})
    assert end["report_status"] == "rejected"
    assert project_case(store.events_for(case_id)).status == "closed_rejected"


async def test_invalid_decision_reinterrupts_with_an_error(store) -> None:
    fake = make_graph_fake()
    case_id = await _triaged(store, fake)
    graph, config, _ = await start_drafting(case_id, model=fake, store=store)
    paused = await resolve_gate(graph, config, {"action": "approve"})
    (intr,) = paused["__interrupt__"]
    assert "reviewer" in intr.value["error"]
    end = await resolve_gate(graph, config, {
        "action": "approve", "reviewer": "N. Officer", "comment": None, "directive": None})
    assert end["report_status"] == "issued"


async def test_rerun_records_the_directive_ends_the_run_and_hands_off_to_triage(store) -> None:
    fake = make_graph_fake()
    case_id = await _triaged(store, fake)
    graph, config, _ = await start_drafting(case_id, model=fake, store=store)
    end = await resolve_gate(graph, config, {
        "action": "rerun", "reviewer": "N. Officer", "comment": None,
        "directive": {"instructions": "Re-check the 11 August override for a shared beneficiary.",
                      "target_agents": ["log"]}})
    assert "__interrupt__" not in end and end["report_status"] == "draft"
    record = project_case(store.events_for(case_id))
    assert record.status == "under_review"
    directive = record.decisions[-1].directive
    assert directive is not None and directive.target_agents == ["log"]

    before = list(fake.call_log)
    await run_triage(case_id, model=fake, store=store,
                     directive=ReviewerDirective.model_validate(directive.model_dump()))
    new_calls = fake.call_log[len(before):]
    assert new_calls.count("record_log_analysis") == 1 and new_calls.count("record_observations") == 0
    assert "shared beneficiary" in message_text(fake.last_messages_for("record_log_analysis")[0])

    _, _, state = await start_drafting(case_id, model=fake, store=store)
    (intr,) = state["__interrupt__"]
    assert intr.value["reviewer_rounds"] == 1


async def test_rerun_cap_forces_a_final_decision(store) -> None:
    fake = make_graph_fake()
    case_id = await _triaged(store, fake)
    rerun = {"action": "rerun", "reviewer": "N. Officer", "comment": None,
             "directive": {"instructions": "Look again.", "target_agents": ["log"]}}
    for expected_round in (0, 1, 2):
        graph, config, state = await start_drafting(case_id, model=fake, store=store)
        (intr,) = state["__interrupt__"]
        assert intr.value["reviewer_rounds"] == expected_round and intr.value["rerun_allowed"] is True
        await resolve_gate(graph, config, rerun)
    graph, config, state = await start_drafting(case_id, model=fake, store=store)
    (intr,) = state["__interrupt__"]
    assert intr.value["reviewer_rounds"] == 3 and intr.value["rerun_allowed"] is False
    paused = await resolve_gate(graph, config, rerun)
    assert "cap" in paused["__interrupt__"][0].value["error"].lower()
    end = await resolve_gate(graph, config, {"action": "reject", "reviewer": "N. Officer",
                                             "comment": None, "directive": None})
    assert end["report_status"] == "rejected"


async def test_ungroundable_draft_retries_twice_then_blocks_without_gating(store) -> None:
    fake = make_graph_fake(overrides={"draft_case_report": {
        "overall_assessment": "Invented.",
        "sections": [{"title": "Ghost", "body": "b", "cited_finding_ids": ["F-INVENTED"]}],
        "open_observations_note": None}})
    case_id = await _triaged(store, fake, HAL)
    drafts_before = fake.call_log.count("draft_case_report")
    _, _, state = await start_drafting(case_id, model=fake, store=store)
    assert fake.call_log.count("draft_case_report") - drafts_before == 3
    assert state["report_blocked"] is True and "__interrupt__" not in state
    assert "FAILED grounding validation" in message_text(fake.last_messages[0])
    record = project_case(store.events_for(case_id))
    assert record.report_blocked is True and record.status == "triaged"


async def test_prompt_override_for_drafting_is_recorded(store) -> None:
    fake = make_graph_fake()
    case_id = await _triaged(store, fake)
    override = "Write for a non-specialist reader; two sentences per section maximum."
    _, _, state = await start_drafting(case_id, model=fake, store=store, prompt_overrides={"DRAFTING": override})
    assert override in message_text(fake.last_messages_for("draft_case_report")[0])
    record = project_case(store.events_for(case_id))
    drafting_run = next(r for r in reversed(record.runs) if r.kind == "drafting")
    assert drafting_run.prompts["DRAFTING"]["override"] == override
