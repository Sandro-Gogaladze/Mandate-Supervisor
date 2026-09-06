"""The triage run, wired to the ledger, on the dossier.

Everything here runs against a tmp-path ledger and the comprehensive fake
model — zero live calls.
"""
from __future__ import annotations

import json

import pytest

from agents.context import canonical_context, compose_context, context_digest
from ingestion.normalize import normalize_dossier
from ledger import LedgerStore
from pipeline.graph import build_triage_graph, run_triage
from registry.loader import load_log_ruleset
from schemas import ReviewerDirective
from tests.corpus import HAL, hal as load_hal, seed, thin
from tests.fakes import CLEAN_VERDICT, make_graph_fake
from agents.llm import message_text


def test_triage_graph_nodes() -> None:
    graph = build_triage_graph(model=make_graph_fake(), store=LedgerStore.__new__(LedgerStore))
    node_names = set(graph.get_graph().nodes) - {"__start__", "__end__"}
    assert node_names == {
        "ingest", "orchestrate", "mandate", "kya", "log", "drift",
        "specialists_done", "critic", "synthesizer", "record", "investigator",
        "provenance", "injection", "consent", "counterparty", "control_assurance", "systemic",
    }


async def test_kestrel_triage_produces_the_floor_the_scripts_do(store) -> None:
    case_id = seed(store)
    fake = make_graph_fake()
    record = await run_triage(case_id, model=fake, store=store)

    assert record.status == "triaged"
    # 2658 = 2603 + 50 + 5. KYA-TEC-07 is run-level, so it adds one fact per
    # run on this fifty-run dossier. The five singles: PRV-CPT-01 and
    # LOG-HRS-01 each record an absent/rule_draft, which is how F34 and F63
    # stay visibly named-but-undetectable rather than uncovered and silent;
    # DRIFT-BAS-01 checks the baseline can carry a drift question at all; and
    # LOG-RND-01 and LOG-LIM-01 each carry the measurement their verdict rests
    # on — the roundness profile and the cap-utilisation distribution.
    # +1 systemic: with one case on the ledger it records "there is no
    # portfolio to look from" rather than staying silent, which would read as
    # nothing found.
    assert len(record.facts) == 2659
    verdicts = sorted((a.agent, a.rule_id, a.verdict) for a in record.assessments if a.agent in ("mandate", "kya", "log", "drift"))
    assert verdicts == sorted([
        ("kya", "KYA-LIF-04", "breach"),
        ("kya", "KYA-REG-03", "clear"),   # judged and in force: activity fits the registered class
        ("mandate", "MND-CAP-01", "breach"), ("mandate", "MND-CAP-01", "explained"),
        ("mandate", "MND-CAP-02", "breach"), ("mandate", "MND-CAP-05", "breach"),
        ("mandate", "MND-USE-01", "breach"),
        ("mandate", "MND-SEM-01", "clear"),   # the whole-dossier fidelity call, fake-consistent
        ("log", "LOG-STR-01", "clear"), ("log", "LOG-CON-01", "clear"), ("log", "LOG-VEL-01", "clear"),
        ("log", "LOG-RND-01", "clear"),   # 3 of 102 multiples of 100 — retail, not a pattern
        ("log", "LOG-LIM-01", "clear"),   # median draw 0.92 of the cap — a budget being used
        ("drift", "DRIFT-BHV-01", "clear"),
    ])
    fidelity = next(a for a in record.assessments if a.rule_id == "MND-SEM-01")
    assert len(fidelity.run_refs) == 49 and len(fidelity.fact_ids) == 49
    # findings are the projection, under the same ids
    assert {f.finding_id for f in record.findings} == {a.assessment_id for a in record.assessments}
    # 14.1 = 13.1 + 1.00: KYA-TEC-07 breaches once (severity 1.0, certain).
    assert record.risk_score.total == 14.1
    assert record.draft_report is None  # triage NEVER drafts — report is on demand

    events = [e.event_type for e in store.events_for(case_id)]
    assert events[:3] == ["dossier_submitted", "run_started", "dispatch_planned"]
    # The orchestrator's closing brief is the last thing written before the
    # run closes, and it is written over a recommendation already on the record.
    assert "authorisation_computed" in events
    assert events[-3:] == ["run_evaluated", "orchestrator_summarised", "run_completed"]
    assert events.count("dispatch_recorded") == 10  # eight peers + systemic + control assurance
    # +50 KYA-TEC-07 (one per run), +5 singles (see the fact count above)
    assert events.count("fact_recorded") == 2659
    # 86 = 83 + three judged verdicts added since: KYA-REG-03 (activity fits
    # the registered class), LOG-RND-01 and LOG-LIM-01.
    assert events.count("assessment_recorded") == events.count("finding_recorded") == 86
    assert fake.call_log.count("record_intent_fidelity") == 1
    assert fake.call_log.count("record_correlations") == 1  # ≥2 findings → synthesizer ran
    assert store.verify() == []


async def test_every_assessment_cites_facts_on_the_record(store) -> None:
    case_id = seed(store)
    record = await run_triage(case_id, model=make_graph_fake(), store=store)
    fact_ids = {f.fact_id for f in record.facts}
    for a in record.assessments:
        assert a.fact_ids and set(a.fact_ids) <= fact_ids, a.assessment_id
        if a.scope == "run":
            assert a.run_refs


async def test_halcyon_triage_is_nearly_clean(store) -> None:
    case_id = seed(store, HAL)
    record = await run_triage(case_id, model=make_graph_fake(), store=store)
    assert [(a.rule_id, a.run_refs) for a in record.assessments if a.verdict == "breach" and a.agent == "mandate"] == [
        ("MND-CAP-02", ["RUN-2026-0813-0015"])]
    assert record.risk_score.total == 3.2
    assert {e.actor for e in store.events_for(case_id) if e.event_type == "finding_recorded"} <= {
        "agent:mandate", "agent:kya", "agent:log", "agent:drift", "agent:consent", "agent:injection", "agent:provenance", "agent:counterparty", "agent:control_assurance"}


async def test_dispatch_recorded_context_is_the_exact_canonical_composition(store) -> None:
    case_id = seed(store)
    await run_triage(case_id, model=make_graph_fake(), store=store)
    dispatches = {e.payload["target"]: e.payload for e in store.events_for(case_id)
                  if e.event_type == "dispatch_recorded"}
    assert set(dispatches) == {"mandate", "kya", "log", "drift", "provenance", "injection",
                               "consent", "counterparty", "systemic", "control_assurance"}

    from ingestion.normalize import dossier_from_submission
    from ledger.seed import latest_submission
    dossier = dossier_from_submission(latest_submission(store, case_id))
    from ledger.projection import project_case
    record = project_case(store.events_for(case_id))
    expected = compose_context(canonical_context(
        "log.analyze", dossier, ruleset=load_log_ruleset(),
        floor_facts=[f for f in record.facts if f.domain == "log"],
    ))
    assert dispatches["log"]["context_blocks"] == json.loads(json.dumps(expected))
    assert dispatches["log"]["context_digest"] == context_digest(expected)
    assert dispatches["log"]["skill"] == "log.analyze" and dispatches["log"]["instruction"] == ""


async def test_drift_declines_on_a_thin_history_and_says_so(store) -> None:
    case_id = seed(store, dossier=thin(load_hal(), 12))
    fake = make_graph_fake()
    record = await run_triage(case_id, model=fake, store=store)
    assert fake.call_log.count("record_drift_analysis") == 0
    assert fake.call_log.count("record_log_analysis") == 1
    drift_dispatch = next(e.payload for e in store.events_for(case_id)
                          if e.event_type == "dispatch_recorded" and e.payload["target"] == "drift")
    assert drift_dispatch["context_blocks"] == {"insufficient_baseline_gate": True, "transaction_count": 12}
    f, = [f for f in record.facts if f.domain == "drift"]
    assert (f.kind, f.absent_reason) == ("absent", "insufficient_history")


async def test_the_first_pass_dispatches_every_review_skill_without_routing_call(store) -> None:
    """The fixed first-pass policy fans out; Control Assurance follows by topology."""
    case_id = seed(store, dossier=thin(load_hal(), 12))
    fake = make_graph_fake()
    record = await run_triage(case_id, model=fake, store=store)
    assert fake.call_log.count("route_supervisor_request") == 0
    dispatched = [e.payload["target"] for e in store.events_for(case_id) if e.event_type == "dispatch_recorded"]
    assert set(dispatched) == {"mandate", "kya", "provenance", "injection", "counterparty",
                               "consent", "log", "drift", "systemic", "control_assurance"}
    plan = record.runs[-1].plan
    # 9: the eight peers plus systemic. Control Assurance is not in the plan —
    # the graph runs it after the fan-out, because its rules need their facts.
    assert plan.first_pass and plan.not_dispatched == [] and len(plan.skills) == 9
    assert plan.message_to_officer




async def test_directed_pass_runs_exactly_the_named_agents_as_a_new_round(store) -> None:
    case_id = seed(store)
    fake = make_graph_fake()
    first = await run_triage(case_id, model=fake, store=store)
    calls_after_first = list(fake.call_log)
    fact_events_after_first = sum(1 for e in store.events_for(case_id) if e.event_type == "fact_recorded")

    directive = ReviewerDirective(instructions="Re-check the override on 11 August for a shared beneficiary.",
                                  target_agents=["log"])
    record = await run_triage(case_id, model=fake, store=store, directive=directive)

    new_calls = fake.call_log[len(calls_after_first):]
    assert new_calls.count("record_log_analysis") == 1
    assert new_calls.count("record_observations") == 0  # kya NOT re-run — no floor on pass 2
    assert new_calls.count("route_supervisor_request") == 0  # a directive needs no model routing
    assert "shared beneficiary" in message_text(fake.last_messages_for("record_log_analysis")[0])
    directed_run = record.runs[-1]
    assert [d.target for d in directed_run.dispatches] == ["log", "control_assurance"]
    assert directed_run.dispatches[0].instruction == directive.instructions
    assert directed_run.plan.reasoning.startswith("Directed re-analysis")
    # round 2 supersedes round 1's Log verdicts; nothing else changed; the
    # floor's facts were not re-recorded
    r2 = [a for a in record.assessments if a.round == 2 and a.agent == "log"]
    assert {a.rule_id for a in r2} == {"LOG-STR-01", "LOG-CON-01", "LOG-VEL-01",
                                       "LOG-RND-01", "LOG-LIM-01"}
    assert all(a.supersedes and a.supersedes.endswith(":r1") for a in r2)
    assert len(record.findings) == len(first.findings)
    assert sum(1 for e in store.events_for(case_id) if e.event_type == "fact_recorded") == fact_events_after_first
    assert record.risk_score.total == first.risk_score.total


async def test_a_changed_judgement_in_a_later_round_moves_the_score(store) -> None:
    case_id = seed(store)
    await run_triage(case_id, model=make_graph_fake(), store=store)
    anomalous = {"anomalous": True, "explanation": "The largest counterparty holds 2735.0 of 20113.5.",
                 "cited_evidence": "total 2735.0", "transaction_ids": ["TXN-KST-0001"]}
    fake = make_graph_fake({"record_log_analysis": {
        "structuring": CLEAN_VERDICT, "concentration": anomalous, "velocity": CLEAN_VERDICT,
        "other_observations": []}})
    record = await run_triage(case_id, model=fake, store=store,
                              directive=ReviewerDirective(instructions="Judge concentration.", target_agents=["log"]))
    current = [f for f in record.findings if f.rule_id == "LOG-CON-01"]
    assert len(current) == 1 and current[0].severity_weight == pytest.approx(0.35)  # 0.5 × probable
    # 14.45 = 13.45 + 1.00: KYA-TEC-07 breaches once (severity 1.0, certain).
    assert record.risk_score.total == pytest.approx(14.45)


async def test_prompt_override_reaches_the_specialist_and_the_record(store) -> None:
    case_id = seed(store)
    fake = make_graph_fake()
    override = "This run: weight threshold-proximity heavily; treat repeat purchases as benign."
    record = await run_triage(case_id, model=fake, store=store, prompt_overrides={"SPECIALIST-LOG": override})
    sent = message_text(fake.last_messages_for("record_log_analysis")[0])
    assert override in sent
    recorded = record.runs[-1].prompts["SPECIALIST-LOG"]
    assert recorded["override"] == override and recorded["effective"] == sent
    assert record.runs[-1].prompts["SPECIALIST-KYA"]["override"] is None


async def test_synthesizer_correlations_validated_and_recorded(store) -> None:
    case_id = seed(store)

    def correlate(messages):
        payload = json.loads(message_text(messages[-1]))
        ids = [f["finding_id"] for f in payload["findings"]]
        return {"correlations": [
            {"finding_ids": ids[:2], "relationship": "same_event", "explanation": "One over-cap cart seen by two rules."},
            {"finding_ids": ["F-INVENTED", ids[0]], "relationship": "causal", "explanation": "x"},
        ]}

    record = await run_triage(case_id, model=make_graph_fake({"record_correlations": correlate}), store=store)
    assert len(record.correlations) == 1 and record.correlations[0].relationship == "same_event"


async def test_synthesizer_accepts_a_json_encoded_correlations_array(store) -> None:
    """Some live model replies encode the array one level too deep as text;
    normalize that boundary instead of iterating thousands of characters."""
    case_id = seed(store)

    def correlate(messages):
        payload = json.loads(message_text(messages[-1]))
        ids = [f["finding_id"] for f in payload["findings"]]
        return {"correlations": json.dumps([
            {"finding_ids": ids[:2], "relationship": "corroborating", "explanation": "Two checks agree."}
        ])}

    record = await run_triage(case_id, model=make_graph_fake({"record_correlations": correlate}), store=store)
    assert len(record.correlations) == 1 and record.correlations[0].relationship == "corroborating"


async def test_critic_flags_a_number_absent_from_the_dispatched_evidence(store) -> None:
    case_id = seed(store)
    fake = make_graph_fake(overrides={"record_log_analysis": {
        "structuring": {"anomalous": True, "explanation": "Three payments of 9999999.99 each split a settlement.",
                        "cited_evidence": "cluster sums to 9999999.99", "transaction_ids": ["TXN-KST-0001"]},
        "concentration": CLEAN_VERDICT, "velocity": CLEAN_VERDICT, "other_observations": []}})
    await run_triage(case_id, model=fake, store=store)
    log_check = next(e.payload for e in store.events_for(case_id)
                     if e.event_type == "critic_checked" and e.payload["target"] == "log")
    assert log_check["passed"] is False and "9999999.99" in log_check["unquoted_values"]


async def test_critic_passes_when_the_model_quotes_real_numbers(store) -> None:
    case_id = seed(store)
    fake = make_graph_fake(overrides={"record_log_analysis": {
        "structuring": {"anomalous": True,
                        "explanation": "Spend totals 20113.5 across 102 transactions against a 1000.0 threshold.",
                        "cited_evidence": "total 20113.5, threshold 1000.0", "transaction_ids": ["TXN-KST-0001"]},
        "concentration": CLEAN_VERDICT, "velocity": CLEAN_VERDICT, "other_observations": []}})
    await run_triage(case_id, model=fake, store=store)
    log_check = next(e.payload for e in store.events_for(case_id)
                     if e.event_type == "critic_checked" and e.payload["target"] == "log")
    assert log_check["passed"] is True, log_check


async def test_intake_facts_are_a_subset_of_the_agents_facts(store) -> None:
    case_id = seed(store)
    record = await run_triage(case_id, model=make_graph_fake(), store=store)
    from ingestion.normalize import dossier_from_submission
    from ledger.seed import latest_submission
    pack = normalize_dossier(dossier_from_submission(latest_submission(store, case_id)))
    assert {(f.fact_id, f.kind) for f in pack.ingestion_facts} <= {(f.fact_id, f.kind) for f in record.facts}


async def test_unknown_case_id_raises_clearly(store) -> None:
    with pytest.raises(ValueError, match="no case_submitted event"):
        await run_triage("DOSSIER-DOES-NOT-EXIST", model=make_graph_fake(), store=store)
