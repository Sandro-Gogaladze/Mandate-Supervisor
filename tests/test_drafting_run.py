"""Stage 7 — the drafting run and the human gate (architecture-v2 §14.3).

The seven gate tests from the old single-graph test_pipeline.py, unchanged
in substance: the gate still holds on interrupt(), still validates decisions
server-side, still caps reruns. What changed is topology — a `rerun`
decision now records the directive and ENDS the run; the caller starts a
directed triage. The handoff is proven end-to-end here.
"""
from __future__ import annotations

import pytest

from data.loader import CASES_DIR, load_raw_case_json
from ledger import LedgerStore
from ledger.projection import project_case
from ledger.seed import submit_case
from pipeline.graph import resolve_gate, run_triage, start_drafting
from schemas import ReviewerDirective
from tests.fakes import make_graph_fake


@pytest.fixture
def store(tmp_path) -> LedgerStore:
    return LedgerStore(tmp_path / "ledger.db")


async def _triaged(store: LedgerStore, name: str, fake) -> str:
    case_id = submit_case(store, load_raw_case_json(CASES_DIR / name))
    await run_triage(case_id, model=fake, store=store)
    return case_id


async def test_grounded_run_pauses_at_the_human_gate(store) -> None:
    fake = make_graph_fake()
    case_id = await _triaged(store, "case-002-mandate-breaching.json", fake)
    _, _, state = await start_drafting(case_id, model=fake, store=store)

    (intr,) = state["__interrupt__"]
    assert intr.value["reason"] == "report_approval"
    assert intr.value["rerun_allowed"] is True
    assert state["draft_report"] is not None
    # while the gate holds, the ledger already shows pending_decision
    assert project_case(store.events_for(case_id)).status == "pending_decision"


async def test_drafting_recomputes_the_score_and_grounds_against_ledger_findings(store) -> None:
    fake = make_graph_fake()
    case_id = await _triaged(store, "case-002-mandate-breaching.json", fake)
    _, _, state = await start_drafting(case_id, model=fake, store=store)

    report = state["draft_report"]
    record = project_case(store.events_for(case_id))
    cited = {fid for s in report.sections for fid in s.cited_finding_ids}
    assert cited == {f.finding_id for f in record.findings}
    assert state["grounding_problems"] == []
    score = state["risk_score"]
    assert score.total == round(sum(f.severity_weight or 0.0 for f in record.findings), 4)
    # the drafting run recomputed and recorded its own score event
    score_events = [e for e in store.events_for(case_id) if e.event_type == "score_computed"]
    assert len(score_events) == 2  # one from triage, one from drafting


async def test_approve_resolves_the_gate_and_issues(store) -> None:
    fake = make_graph_fake()
    case_id = await _triaged(store, "case-002-mandate-breaching.json", fake)
    graph, config, _ = await start_drafting(case_id, model=fake, store=store)

    end = await resolve_gate(graph, config, {
        "action": "approve", "reviewer": "N. Officer", "comment": "Clear breach.", "directive": None,
    })
    assert end["report_status"] == "issued"
    assert "__interrupt__" not in end

    record = project_case(store.events_for(case_id))
    assert record.status == "issued"
    assert record.decisions[-1].reviewer == "N. Officer"
    assert record.decisions[-1].decided_at  # stamped server-side
    decision_events = [e for e in store.events_for(case_id) if e.event_type == "decision_recorded"]
    assert decision_events[-1].actor == "human:N. Officer"
    assert store.verify() == []


async def test_reject_resolves_without_issuing(store) -> None:
    fake = make_graph_fake()
    case_id = await _triaged(store, "case-002-mandate-breaching.json", fake)
    graph, config, _ = await start_drafting(case_id, model=fake, store=store)

    end = await resolve_gate(graph, config, {
        "action": "reject", "reviewer": "N. Officer", "comment": "Not convincing.", "directive": None,
    })
    assert end["report_status"] == "rejected"
    assert project_case(store.events_for(case_id)).status == "closed_rejected"


async def test_invalid_decision_reinterrupts_with_an_error(store) -> None:
    fake = make_graph_fake()
    case_id = await _triaged(store, "case-002-mandate-breaching.json", fake)
    graph, config, _ = await start_drafting(case_id, model=fake, store=store)

    paused = await resolve_gate(graph, config, {"action": "approve"})  # no reviewer name
    (intr,) = paused["__interrupt__"]
    assert "reviewer" in intr.value["error"]

    end = await resolve_gate(graph, config, {
        "action": "approve", "reviewer": "N. Officer", "comment": None, "directive": None,
    })
    assert end["report_status"] == "issued"


async def test_rerun_records_the_directive_ends_the_run_and_hands_off_to_triage(store) -> None:
    fake = make_graph_fake()
    case_id = await _triaged(store, "case-005-structuring.json", fake)
    graph, config, _ = await start_drafting(case_id, model=fake, store=store)

    end = await resolve_gate(graph, config, {
        "action": "rerun", "reviewer": "N. Officer", "comment": None,
        "directive": {"instructions": "Re-check the same-day cluster for a shared beneficiary.",
                      "target_agents": ["log"]},
    })
    # the drafting run ENDED — no re-interrupt, directive on the record
    assert "__interrupt__" not in end
    assert end["report_status"] == "draft"
    record = project_case(store.events_for(case_id))
    assert record.status == "under_review"  # live again, awaiting the directed pass
    directive = record.decisions[-1].directive
    assert directive is not None and directive.target_agents == ["log"]

    # the caller's handoff: a directed triage run with the recorded directive
    before = list(fake.call_log)
    await run_triage(case_id, model=fake, store=store,
                     directive=ReviewerDirective.model_validate(directive.model_dump()))
    new_calls = fake.call_log[len(before):]
    assert new_calls.count("record_log_analysis") == 1
    assert new_calls.count("record_observations") == 0
    assert "shared beneficiary" in fake.last_messages_for("record_log_analysis")[0].content

    # and a fresh drafting run knows one rerun round was spent
    _, _, state = await start_drafting(case_id, model=fake, store=store)
    (intr,) = state["__interrupt__"]
    assert intr.value["reviewer_rounds"] == 1


async def test_rerun_cap_forces_a_final_decision(store) -> None:
    fake = make_graph_fake()
    case_id = await _triaged(store, "case-002-mandate-breaching.json", fake)

    rerun = {
        "action": "rerun", "reviewer": "N. Officer", "comment": None,
        "directive": {"instructions": "Look again.", "target_agents": ["log"]},
    }
    for expected_round in (0, 1, 2):
        graph, config, state = await start_drafting(case_id, model=fake, store=store)
        (intr,) = state["__interrupt__"]
        assert intr.value["reviewer_rounds"] == expected_round
        assert intr.value["rerun_allowed"] is True
        await resolve_gate(graph, config, rerun)

    # three reruns spent — the 4th drafting run's gate refuses another
    graph, config, state = await start_drafting(case_id, model=fake, store=store)
    (intr,) = state["__interrupt__"]
    assert intr.value["reviewer_rounds"] == 3
    assert intr.value["rerun_allowed"] is False

    paused = await resolve_gate(graph, config, rerun)
    (intr,) = paused["__interrupt__"]
    assert "cap" in intr.value["error"].lower()

    end = await resolve_gate(graph, config, {
        "action": "reject", "reviewer": "N. Officer", "comment": None, "directive": None,
    })
    assert end["report_status"] == "rejected"


async def test_ungroundable_draft_retries_twice_then_blocks_without_gating(store) -> None:
    fake = make_graph_fake(overrides={
        "draft_case_report": {
            "overall_assessment": "Invented.",
            "sections": [{"title": "Ghost", "body": "b", "cited_finding_ids": ["F-INVENTED"]}],
            "open_observations_note": None,
        },
    })
    case_id = await _triaged(store, "case-001-compliant.json", fake)
    drafts_before = fake.call_log.count("draft_case_report")
    _, _, state = await start_drafting(case_id, model=fake, store=store)

    assert fake.call_log.count("draft_case_report") - drafts_before == 3  # 1 + 2 retries
    assert state["report_blocked"] is True
    assert "__interrupt__" not in state  # nothing approvable ever reached the gate
    assert "FAILED grounding validation" in fake.last_messages[0].content

    record = project_case(store.events_for(case_id))
    assert record.report_blocked is True
    assert record.status == "triaged"  # not pending_decision — nothing to decide
    blocked_events = [e for e in store.events_for(case_id) if e.event_type == "report_blocked"]
    assert len(blocked_events) == 1


async def test_prompt_override_for_drafting_is_recorded(store) -> None:
    fake = make_graph_fake()
    case_id = await _triaged(store, "case-002-mandate-breaching.json", fake)
    override = "Write for a non-specialist reader; two sentences per section maximum."
    _, _, state = await start_drafting(
        case_id, model=fake, store=store, prompt_overrides={"DRAFTING": override},
    )
    sent = fake.last_messages_for("draft_case_report")[0].content
    assert override in sent
    record = project_case(store.events_for(case_id))
    drafting_run = next(r for r in reversed(record.runs) if r.kind == "drafting")
    assert drafting_run.prompts["DRAFTING"]["override"] == override
