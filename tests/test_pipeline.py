"""Graph-level integration tests (PLAN items 4 and 9), against a single
comprehensive fake model covering every tool name used anywhere in the
graph — dispatch, KYA (reasoning + narration), Log, Drift, Mandate's
semantic check. No live API calls anywhere in this file: run_case() now
makes 5+ LLM calls per case (dispatch + up to 4 specialists, potentially
+escalation), so without an injectable model this suite would either need
a live key on every `pytest` run or silently make real, paid calls — both
wrong. See pipeline/graph.py::build_graph(model=...).
"""
from __future__ import annotations

import json

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from data.loader import CASES_DIR
from pipeline.graph import build_graph, run_case
from tests.fakes import FakeChatModel

_CLEAN = {"anomalous": False, "explanation": "n/a", "cited_evidence": "n/a"}


def _grounded_draft(messages) -> dict:
    """Payload-aware fake draftsman: cites exactly the finding_ids the case
    actually produced (a static dict can't be grounded for every case), so
    grounding passes first try and the graph exits the drafting loop
    without retries in every pre-existing test."""
    payload = json.loads(messages[-1].content)
    ids = [f["finding_id"] for f in payload["findings"]]
    sections = (
        [{"title": "Findings", "body": "See cited findings.", "cited_finding_ids": ids}] if ids else []
    )
    note = "Unverified items for officer review." if payload["unverified_observations"] else None
    return {"overall_assessment": "Review complete.", "sections": sections, "open_observations_note": note}


DEFAULT_RESPONSES = {
    "record_dispatch_plan": {
        "run_mandate": True, "run_kya": True, "run_log": True, "run_drift": True,
        "reasoning": "run everything",
    },
    "record_observations": {"observations": []},
    "write_narration": {"narration": "Nothing to report."},
    "record_log_analysis": {
        "structuring": _CLEAN, "concentration": _CLEAN, "velocity": _CLEAN, "other_observations": [],
    },
    "record_drift_analysis": {"drift": _CLEAN, "other_observations": []},
    "record_semantic_check": {"consistent": True, "quoted_evidence": "", "explanation": "matches intent"},
    "draft_case_report": _grounded_draft,
}


def _make_fake(overrides: dict | None = None) -> FakeChatModel:
    return FakeChatModel({**DEFAULT_RESPONSES, **(overrides or {})})


def test_graph_builds() -> None:
    assert build_graph(model=_make_fake()) is not None


async def test_clean_case_produces_no_findings_and_no_escalation() -> None:
    fake = _make_fake()
    result = await run_case(str(CASES_DIR / "case-001-compliant.json"), model=fake)

    assert result["findings"] == []
    assert result["observations"] == []
    # dispatch + mandate + kya(reasoning+narration) + log + drift = 6 calls, no escalation round
    assert fake.call_log.count("record_dispatch_plan") == 1
    assert fake.call_log.count("record_observations") == 1  # kya only called once — no escalation


async def test_dispatch_plan_actually_gates_which_specialists_run() -> None:
    fake = _make_fake(overrides={
        "record_dispatch_plan": {
            "run_mandate": True, "run_kya": True, "run_log": False, "run_drift": False,
            "reasoning": "minimal history",
        },
    })
    # case-007 has 7 tx: floor forces Log (non-empty) but not Drift (<30)
    await run_case(str(CASES_DIR / "case-007-prompt-injection.json"), model=fake)

    assert fake.call_log.count("record_log_analysis") == 1  # floor forced it despite LLM saying no
    assert fake.call_log.count("record_drift_analysis") == 0  # floor didn't force it, LLM said no


async def test_escalation_round_re_dispatches_only_the_targeted_agent() -> None:
    fake = _make_fake(overrides={
        "record_observations": {
            "observations": [{"note": "Issuer name looks slightly unusual.", "cited_field": "issuer_name"}],
        },
    })
    # case-006 has 49 tx — comfortably over Drift's own insufficient_baseline
    # gate, so all four specialists genuinely reach their LLM call in round 0.
    result = await run_case(str(CASES_DIR / "case-006-drift.json"), model=fake)

    # kya's reasoning tool called twice: round 0 (raises the observation)
    # and round 1 (escalation, resolving it) — capped there.
    assert fake.call_log.count("record_observations") == 2
    # mandate/log/drift were never escalation targets — only ever called once each
    assert fake.call_log.count("record_semantic_check") == 1
    assert fake.call_log.count("record_log_analysis") == 1
    assert fake.call_log.count("record_drift_analysis") == 1
    # escalation-round findings are never re-added — kya contributes no
    # findings at all here (its floor was clean), so nothing to duplicate
    assert result["findings"] == []


async def test_cross_agent_observation_escalates_to_the_named_agent_not_the_originator() -> None:
    fake = _make_fake(overrides={
        "record_drift_analysis": {
            "drift": _CLEAN,
            "other_observations": [
                {"note": "This new counterparty warrants a specific KYA verification check.", "cited_evidence": "x"},
            ],
        },
    })
    await run_case(str(CASES_DIR / "case-006-drift.json"), model=fake)

    # drift raised the observation but it names KYA — escalation round
    # should re-invoke KYA's reasoning, not drift's analysis, a second time
    assert fake.call_log.count("record_drift_analysis") == 1
    assert fake.call_log.count("record_observations") == 2  # kya: round 0 + escalation round


async def test_escalation_is_capped_at_one_extra_round_even_with_persistent_observations() -> None:
    fake = _make_fake(overrides={
        "record_observations": {
            "observations": [{"note": "Still unresolved even after a second look.", "cited_field": "x"}],
        },
    })
    # kya keeps producing an observation every single call — must not loop forever
    await run_case(str(CASES_DIR / "case-001-compliant.json"), model=fake)

    assert fake.call_log.count("record_observations") == 2  # round 0 + exactly 1 escalation round, then stops


async def test_ingestion_findings_are_a_subset_of_agent_findings() -> None:
    for name in ["case-003-broken-chain.json", "case-004-synthetic-identity.json"]:
        fake = _make_fake()
        result = await run_case(str(CASES_DIR / name), model=fake)
        ingestion_types = {f.type for f in result["ingestion_findings"]}
        agent_types = {f.type for f in result["findings"]}
        assert ingestion_types <= agent_types, name


def test_all_graph_nodes_present() -> None:
    graph = build_graph(model=_make_fake())
    node_names = set(graph.get_graph().nodes) - {"__start__", "__end__"}
    assert node_names == {
        "ingest", "dispatch", "mandate", "kya", "log", "drift",
        "escalate_check", "bump_round", "risk_score", "draft_report", "grounding_check", "human_gate",
    }


async def test_every_run_ends_with_a_grounded_report() -> None:
    fake = _make_fake()
    result = await run_case(str(CASES_DIR / "case-002-mandate-breaching.json"), model=fake)

    assert fake.call_log.count("draft_case_report") == 1  # grounded first try, no retries
    report = result["draft_report"]
    assert report.case_id == "CASE-2026-002"
    cited = {fid for s in report.sections for fid in s.cited_finding_ids}
    assert cited == {f.finding_id for f in result["findings"]}  # full coverage
    assert result["grounding_problems"] == []
    assert result["report_blocked"] is False
    # PLAN item 11: the score is pure arithmetic over the findings' weights
    score = result["risk_score"]
    assert score.total == round(sum(f.severity_weight or 0.0 for f in result["findings"]), 4)
    assert score.total > 0
    assert {f.agent for f in score.factors} == {"mandate", "kya", "log", "drift"}


async def test_ungroundable_draft_retries_twice_then_blocks() -> None:
    # A draftsman that always cites a finding that doesn't exist — grounding
    # must fail every attempt: 1 initial + exactly 2 retries, then block
    # (never ship the prose), per CLAUDE.md's grounding-retry cap.
    fake = _make_fake(overrides={
        "draft_case_report": {
            "overall_assessment": "Invented.",
            "sections": [{"title": "Ghost", "body": "b", "cited_finding_ids": ["F-INVENTED"]}],
            "open_observations_note": None,
        },
    })
    result = await run_case(str(CASES_DIR / "case-001-compliant.json"), model=fake)

    assert fake.call_log.count("draft_case_report") == 3
    assert result["report_blocked"] is True
    assert result["grounding_problems"]  # the validator's complaints survive for the UI
    # the retry prompt carried the validator's feedback into the model
    assert "FAILED grounding validation" in fake.last_messages[0].content
    # a blocked report never reaches the human gate — nothing approvable
    assert "__interrupt__" not in result


def _gate_graph(fake: FakeChatModel):
    graph = build_graph(model=fake, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "gate-test"}}
    return graph, config


async def _run_to_gate(fake: FakeChatModel, case_name: str):
    graph, config = _gate_graph(fake)
    state = await graph.ainvoke(
        {"case_path": str(CASES_DIR / case_name), "findings": [], "observations": [], "messages": []},
        config,
    )
    return graph, config, state


async def test_grounded_run_pauses_at_the_human_gate() -> None:
    _, _, state = await _run_to_gate(_make_fake(), "case-001-compliant.json")

    (intr,) = state["__interrupt__"]
    assert intr.value["reason"] == "report_approval"
    assert intr.value["rerun_allowed"] is True
    assert state["draft_report"] is not None  # the officer decides on a grounded draft
    assert "report_status" not in state or state.get("report_status") == "draft"


async def test_approve_resolves_the_gate_and_issues_the_report() -> None:
    graph, config, _ = await _run_to_gate(_make_fake(), "case-001-compliant.json")

    end = await graph.ainvoke(
        Command(resume={"action": "approve", "reviewer": "N. Officer", "comment": "Clean.", "directive": None}),
        config,
    )
    assert end["report_status"] == "issued"
    (decision,) = end["reviewer_decisions"]
    assert decision.reviewer == "N. Officer"
    assert decision.decided_at  # stamped server-side
    assert "__interrupt__" not in end


async def test_reject_resolves_the_gate_without_issuing() -> None:
    graph, config, _ = await _run_to_gate(_make_fake(), "case-001-compliant.json")

    end = await graph.ainvoke(
        Command(resume={"action": "reject", "reviewer": "N. Officer", "comment": "Not convincing.", "directive": None}),
        config,
    )
    assert end["report_status"] == "rejected"


async def test_rerun_directive_reinvokes_only_the_targeted_agent_then_gates_again() -> None:
    fake = _make_fake()
    graph, config, _ = await _run_to_gate(fake, "case-001-compliant.json")
    assert fake.call_log.count("record_log_analysis") == 1

    paused = await graph.ainvoke(
        Command(resume={
            "action": "rerun", "reviewer": "N. Officer", "comment": None,
            "directive": {"instructions": "Re-check the same-day payments for a shared beneficiary.", "target_agents": ["log"]},
        }),
        config,
    )
    # only Log re-ran; the directive reached its prompt; the tail re-ran too
    assert fake.call_log.count("record_log_analysis") == 2
    assert fake.call_log.count("record_observations") == 1  # kya untouched
    assert fake.call_log.count("draft_case_report") == 2  # report redrafted after the pass
    assert "Re-check the same-day payments" in fake.last_messages_for("record_log_analysis")[0].content
    # back at the gate, round counted, directive consumed
    (intr,) = paused["__interrupt__"]
    assert intr.value["reviewer_rounds"] == 1
    assert paused["reviewer_directive"] is None

    end = await graph.ainvoke(
        Command(resume={"action": "approve", "reviewer": "N. Officer", "comment": None, "directive": None}),
        config,
    )
    assert end["report_status"] == "issued"
    assert len(end["reviewer_decisions"]) == 2  # the rerun call is on the record too


async def test_invalid_decision_reinterrupts_with_an_error_instead_of_crashing() -> None:
    graph, config, _ = await _run_to_gate(_make_fake(), "case-001-compliant.json")

    paused = await graph.ainvoke(Command(resume={"action": "approve"}), config)  # no reviewer name
    (intr,) = paused["__interrupt__"]
    assert "reviewer" in intr.value["error"]

    end = await graph.ainvoke(
        Command(resume={"action": "approve", "reviewer": "N. Officer", "comment": None, "directive": None}),
        config,
    )
    assert end["report_status"] == "issued"


async def test_rerun_cap_forces_a_final_decision() -> None:
    fake = _make_fake()
    graph, config, _ = await _run_to_gate(fake, "case-001-compliant.json")

    rerun = {
        "action": "rerun", "reviewer": "N. Officer", "comment": None,
        "directive": {"instructions": "Look again.", "target_agents": ["log"]},
    }
    for expected_round in (1, 2, 3):
        paused = await graph.ainvoke(Command(resume=rerun), config)
        (intr,) = paused["__interrupt__"]
        assert intr.value["reviewer_rounds"] == expected_round

    # 4th rerun refused: the gate re-interrupts with the cap error
    paused = await graph.ainvoke(Command(resume=rerun), config)
    (intr,) = paused["__interrupt__"]
    assert "cap" in intr.value["error"].lower()
    assert intr.value["rerun_allowed"] is False

    end = await graph.ainvoke(
        Command(resume={"action": "reject", "reviewer": "N. Officer", "comment": None, "directive": None}),
        config,
    )
    assert end["report_status"] == "rejected"
    assert end["reviewer_rounds"] == 3
