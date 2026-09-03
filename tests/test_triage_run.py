import pytest

# PARKED — migration-plan.md Phase 2/3.
#
# These cover the triage graph, which is real and still wanted. They are parked because
# their FIXTURE is gone: every one built its case from data/cases/*.json, and
# the corpus is now two dossiers with a different shape.
#
# Parked rather than deleted, and loudly rather than quietly: the logic under
# test did not stop mattering, and a silently shrinking suite is how a
# migration loses coverage nobody notices. Each comes back when the pipeline
# consumes a Dossier and a dossier fixture exists to replace the case one.
pytestmark = pytest.mark.skip(reason="fixture removed with the case corpus — migration Phase 2/3")

"""Stage 5–6 — the triage run, wired to the ledger (architecture-v2 §14.1).

Everything here runs against a tmp-path ledger and the comprehensive fake
model — zero live calls. The old test_pipeline.py graph-shape and
escalation tests continue here in their new home; the gate tests moved to
tests/test_drafting_run.py.
"""
from __future__ import annotations

import json

import pytest

from agents.context import canonical_context, compose_context, context_digest
from data.loader import CASES_DIR, load_raw_case_json
from ledger import LedgerStore
from ledger.seed import submit_case
from pipeline.graph import build_triage_graph, run_triage
from registry.loader import load_log_ruleset
from schemas import ReviewerDirective
from tests.fakes import CLEAN_VERDICT, make_graph_fake


@pytest.fixture
def store(tmp_path) -> LedgerStore:
    return LedgerStore(tmp_path / "ledger.db")


def _seed(store: LedgerStore, name: str) -> str:
    return submit_case(store, load_raw_case_json(CASES_DIR / name))


def test_triage_graph_nodes() -> None:
    graph = build_triage_graph(model=make_graph_fake(), store=LedgerStore.__new__(LedgerStore))
    node_names = set(graph.get_graph().nodes) - {"__start__", "__end__"}
    assert node_names == {
        "ingest", "dispatch", "mandate", "kya", "log", "drift",
        "escalate_check", "bump_round", "critic", "synthesizer", "risk_score",
    }


async def test_clean_case_triage_ends_at_the_score_with_the_expected_ledger_trail(store) -> None:
    case_id = _seed(store, "case-001-compliant.json")
    fake = make_graph_fake()
    record = await run_triage(case_id, model=fake, store=store)

    assert record.status == "triaged"
    assert record.findings == []
    assert record.observations == []
    assert record.risk_score is not None and record.risk_score.total == 0.0
    assert record.draft_report is None  # triage NEVER drafts — report is on demand

    events = [e.event_type for e in store.events_for(case_id)]
    # The fake orchestrator proposes all four and the floor is ADD-only, so
    # drift is dispatched too — and declines on insufficient baseline (24 tx
    # < 30), recorded as such. Specialist dispatch order is fan-out order,
    # not asserted.
    assert events[:3] == ["case_submitted", "run_started", "dispatch_planned"]
    assert events[-2:] == ["score_computed", "run_completed"]
    assert events[3:-2].count("dispatch_recorded") == 4
    drift_dispatch = next(e.payload for e in store.events_for(case_id)
                          if e.event_type == "dispatch_recorded" and e.payload["target"] == "drift")
    assert drift_dispatch["context_blocks"] == {"insufficient_baseline_gate": True, "transaction_count": 24}
    # clean case: <2 findings, synthesizer never called
    assert fake.call_log.count("record_correlations") == 0
    assert store.verify() == []


async def test_findings_are_recorded_one_event_each_with_agent_actor(store) -> None:
    case_id = _seed(store, "case-002-mandate-breaching.json")
    record = await run_triage(case_id, model=make_graph_fake(), store=store)

    finding_events = [e for e in store.events_for(case_id) if e.event_type == "finding_recorded"]
    assert len(finding_events) == 3
    assert {e.actor for e in finding_events} == {"agent:mandate"}
    assert {e.payload["type"] for e in finding_events} == {
        "category_out_of_scope", "counterparty_not_approved", "per_transaction_cap_exceeded",
    }
    # the projected record carries them, deduped, scored
    assert len(record.findings) == 3
    assert record.risk_score.total == round(sum(f.severity_weight for f in record.findings), 4)


async def test_dispatch_recorded_context_is_the_exact_canonical_composition(store) -> None:
    """§9.4 — what the ledger says the agent saw IS what compose_context
    builds, digest and all."""
    case_id = _seed(store, "case-005-structuring.json")
    await run_triage(case_id, model=make_graph_fake(), store=store)

    dispatches = {e.payload["target"]: e.payload for e in store.events_for(case_id)
                  if e.event_type == "dispatch_recorded"}
    # drift was proposed by the fake orchestrator (add-only floor keeps it)
    # but declined on data availability — 16 tx < 30
    assert set(dispatches) == {"mandate", "kya", "log", "drift"}
    assert dispatches["drift"]["context_blocks"]["insufficient_baseline_gate"] is True

    from ingestion.normalize import normalize_case_payload
    case = normalize_case_payload(load_raw_case_json(CASES_DIR / "case-005-structuring.json"))
    expected = compose_context(canonical_context("log.analyze", case, ruleset=load_log_ruleset()))
    assert dispatches["log"]["context_blocks"] == json.loads(json.dumps(expected))
    assert dispatches["log"]["context_digest"] == context_digest(expected)
    assert dispatches["log"]["skill"] == "log.analyze"
    assert dispatches["log"]["instruction"] == ""


async def test_floor_gates_specialists_despite_the_llm_proposal(store) -> None:
    case_id = _seed(store, "case-007-prompt-injection.json")
    fake = make_graph_fake(overrides={
        "record_dispatch_plan": {
            "run_mandate": False, "run_kya": False, "run_log": False, "run_drift": False,
            "reasoning": "skip everything",  # hostile/lazy proposal
        },
    })
    await run_triage(case_id, model=fake, store=store)

    # floor forced mandate+kya+log (7 tx), not drift
    assert fake.call_log.count("record_semantic_check") == 1
    assert fake.call_log.count("record_observations") == 1
    assert fake.call_log.count("record_log_analysis") == 1
    assert fake.call_log.count("record_drift_analysis") == 0


async def test_escalation_re_dispatches_only_the_targeted_agent_and_is_capped(store) -> None:
    case_id = _seed(store, "case-006-drift.json")
    fake = make_graph_fake(overrides={
        "record_observations": {
            "observations": [{"note": "Issuer name looks slightly unusual.", "cited_field": "issuer_name"}],
        },
    })
    record = await run_triage(case_id, model=fake, store=store)

    # kya reasons twice (round 0 + the one escalation round), others once
    assert fake.call_log.count("record_observations") == 2
    assert fake.call_log.count("record_semantic_check") == 1
    assert fake.call_log.count("record_log_analysis") == 1
    assert fake.call_log.count("record_drift_analysis") == 1
    assert record.escalation_rounds == 1
    escalations = [e for e in store.events_for(case_id) if e.event_type == "escalation_round_started"]
    assert len(escalations) == 1
    assert escalations[0].payload == {"round": 1, "targets": ["kya"]}


async def test_cross_agent_observation_escalates_to_the_named_agent(store) -> None:
    case_id = _seed(store, "case-006-drift.json")
    fake = make_graph_fake(overrides={
        "record_drift_analysis": {
            "drift": CLEAN_VERDICT,
            "other_observations": [
                {"note": "This new counterparty warrants a specific KYA verification check.", "cited_evidence": "x"},
            ],
        },
    })
    await run_triage(case_id, model=fake, store=store)
    assert fake.call_log.count("record_drift_analysis") == 1
    assert fake.call_log.count("record_observations") == 2  # kya: round 0 + escalation


async def test_directed_pass_runs_exactly_the_named_agents_with_no_floor(store) -> None:
    case_id = _seed(store, "case-001-compliant.json")
    fake = make_graph_fake()
    await run_triage(case_id, model=fake, store=store)  # pass 1, full floor
    calls_after_first = list(fake.call_log)

    directive = ReviewerDirective(
        instructions="Re-check the same-day payments for a shared beneficiary.",
        target_agents=["log"],
    )
    record = await run_triage(case_id, model=fake, store=store, directive=directive)

    new_calls = fake.call_log[len(calls_after_first):]
    assert new_calls.count("record_log_analysis") == 1
    assert new_calls.count("record_observations") == 0  # kya NOT re-run — no floor on pass 2
    assert new_calls.count("record_semantic_check") == 0
    assert new_calls.count("record_dispatch_plan") == 0  # no LLM proposal on a directed pass
    # the officer's instruction reached the specialist's prompt
    assert "shared beneficiary" in fake.last_messages_for("record_log_analysis")[0].content
    # and the dispatch record carries it
    directed_run = record.runs[-1]
    assert [d.target for d in directed_run.dispatches] == ["log"]
    assert directed_run.dispatches[0].instruction == directive.instructions
    assert directed_run.plan.reasoning.startswith("Directed re-analysis")


async def test_prompt_override_reaches_the_specialist_and_the_record(store) -> None:
    case_id = _seed(store, "case-001-compliant.json")
    fake = make_graph_fake()
    override = "This run: weight threshold-proximity heavily; treat repeat purchases as benign."
    record = await run_triage(
        case_id, model=fake, store=store,
        prompt_overrides={"SPECIALIST-LOG": override},
    )

    sent = fake.last_messages_for("record_log_analysis")[0].content
    assert override in sent
    recorded = record.runs[-1].prompts["SPECIALIST-LOG"]
    assert recorded["override"] == override
    assert recorded["effective"] == sent  # ledger text == wire text
    # the other prompts stayed default
    assert record.runs[-1].prompts["SPECIALIST-KYA"]["override"] is None


async def test_synthesizer_correlations_validated_and_recorded(store) -> None:
    case_id = _seed(store, "case-002-mandate-breaching.json")

    def correlate(messages):
        payload = json.loads(messages[-1].content)
        ids = [f["finding_id"] for f in payload["findings"]]
        return {"correlations": [
            {"finding_ids": ids[:2], "relationship": "same_event",
             "explanation": "One out-of-scope purchase seen by two rules."},
            # invented id — must be dropped by the resolver, not recorded
            {"finding_ids": ["F-INVENTED", ids[0]], "relationship": "causal", "explanation": "x"},
        ]}

    record = await run_triage(
        case_id, model=make_graph_fake({"record_correlations": correlate}), store=store,
    )
    assert len(record.correlations) == 1
    assert record.correlations[0].relationship == "same_event"
    events = [e for e in store.events_for(case_id) if e.event_type == "correlation_recorded"]
    assert len(events) == 1


async def test_critic_flags_a_number_absent_from_the_dispatched_evidence(store) -> None:
    case_id = _seed(store, "case-005-structuring.json")
    fake = make_graph_fake(overrides={
        "record_log_analysis": {
            "structuring": {
                "anomalous": True,
                "explanation": "Three payments of 9999999.99 each split a settlement.",
                "cited_evidence": "cluster sums to 9999999.99",
            },
            "concentration": CLEAN_VERDICT, "velocity": CLEAN_VERDICT, "other_observations": [],
        },
    })
    await run_triage(case_id, model=fake, store=store)

    critic_events = [e for e in store.events_for(case_id) if e.event_type == "critic_checked"]
    log_check = next(e.payload for e in critic_events if e.payload["target"] == "log")
    assert log_check["passed"] is False
    assert "9999999.99" in log_check["unquoted_values"]


async def test_critic_passes_when_the_model_quotes_real_numbers(store) -> None:
    case_id = _seed(store, "case-005-structuring.json")
    fake = make_graph_fake(overrides={
        "record_log_analysis": {
            "structuring": {
                "anomalous": True,
                # 2900/2850/2950 are case-005's real cluster amounts — present
                # in the dispatched evidence
                "explanation": "Payments of 2900.0, 2850.0 and 2950.0 sit just under the threshold.",
                "cited_evidence": "cluster sum 8700.0 vs threshold 3000.0",
            },
            "concentration": CLEAN_VERDICT, "velocity": CLEAN_VERDICT, "other_observations": [],
        },
    })
    await run_triage(case_id, model=fake, store=store)
    critic_events = [e for e in store.events_for(case_id) if e.event_type == "critic_checked"]
    log_check = next(e.payload for e in critic_events if e.payload["target"] == "log")
    assert log_check["passed"] is True, log_check


async def test_ingestion_findings_are_a_subset_of_agent_findings(store) -> None:
    for name in ["case-003-broken-chain.json", "case-004-synthetic-identity.json"]:
        case_id = _seed(store, name)
        record = await run_triage(case_id, model=make_graph_fake(), store=store)
        finding_types = {f.type for f in record.findings}
        raw = load_raw_case_json(CASES_DIR / name)
        from ingestion.normalize import normalize_case_payload
        ingestion_types = {f.type for f in normalize_case_payload(raw).findings}
        assert ingestion_types <= finding_types, name


async def test_unknown_case_id_raises_clearly(store) -> None:
    with pytest.raises(ValueError, match="no case_submitted event"):
        await run_triage("CASE-DOES-NOT-EXIST", model=make_graph_fake(), store=store)
