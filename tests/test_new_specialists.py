"""The six specialists Phase 4 added, as agents: each reviews with one
contained call (or none), validates what the model names against what it
was shown, and yields assessments whose ids never collide with a peer's.
Control Assurance is fed by the peers' facts; Systemic looks across the
portfolio.
"""
from __future__ import annotations

import pytest

from agents.consent import ConsentAgent
from agents.control_assurance import ControlAssuranceAgent, classify_postures, peers_from_evidence, peers_from_facts
from agents.counterparty import CounterpartyAgent
from agents.drift import DriftAgent
from agents.injection import InjectionAgent
from agents.kya import KYAAgent
from agents.log import LogAgent
from agents.mandate import MandateAgent
from agents.prompts import PROMPTS_BY_RUN_KIND, assemble
from agents.provenance import ProvenanceAgent
from agents.systemic import SystemicAgent
from agents.tools import AGENT_TOOLS
from registry.loader import load_all_rulesets
from tests.fakes import DEFAULT_GRAPH_RESPONSES, FakeChatModel

TEN = ("mandate", "kya", "provenance", "injection", "counterparty", "consent", "log", "drift",
       "control_assurance", "systemic")


@pytest.fixture(scope="module")
def books():
    return load_all_rulesets()


def fake(**overrides):
    return FakeChatModel({**DEFAULT_GRAPH_RESPONSES, **overrides})


async def _peer_facts(d, books, model):
    facts = []
    for agent, book in ((MandateAgent(), "mandate"), (KYAAgent(), "kya"), (LogAgent(), "log"), (DriftAgent(), "drift")):
        facts += agent.run(d, books[book])
    for agent, book in ((ProvenanceAgent(), "provenance"), (InjectionAgent(), "injection"),
                        (CounterpartyAgent(), "counterparty"), (ConsentAgent(), "consent")):
        facts += (await agent.review(d, books[book], model=model)).facts
    return facts


# --- the roster --------------------------------------------------------------------

def test_all_ten_have_tool_permissions_and_the_specialists_have_prompts():
    assert set(TEN) <= set(AGENT_TOOLS)
    for pid in ("SPECIALIST-CONSENT", "SPECIALIST-INJECTION", "SPECIALIST-COUNTERPARTY", "SPECIALIST-PROVENANCE"):
        assert assemble(pid).effective
        assert pid in PROMPTS_BY_RUN_KIND["triage"] and pid in PROMPTS_BY_RUN_KIND["investigation"]


async def test_assessment_ids_never_collide_across_the_ten(kst, hal, books):
    model = fake()
    for d in (kst, hal):
        seen = set()
        peer_facts = await _peer_facts(d, books, model)
        reviews = [await a.review(d, books[b], model=model) for a, b in (
            (ProvenanceAgent(), "provenance"), (InjectionAgent(), "injection"),
            (CounterpartyAgent(), "counterparty"), (ConsentAgent(), "consent"))]
        reviews.append(await ControlAssuranceAgent().review(d, books["controls"], peer_facts=peer_facts, rulebooks=books))
        reviews.append(await SystemicAgent().review(d, portfolio=[kst, hal]))
        for rv in reviews:
            for a in rv.assessments:
                assert a.assessment_id not in seen, a.assessment_id
                seen.add(a.assessment_id)
                assert a.fact_ids or a.verdict in ("clear", "inconclusive"), a.assessment_id


# --- the four with a contained call ---------------------------------------------------

async def test_provenance_floor_then_reconciliation(kst, books):
    rv = await ProvenanceAgent().review(kst, books["provenance"], model=fake())
    verdicts = {(a.rule_id, a.verdict) for a in rv.assessments}
    assert verdicts == {("KYA-TEC-02", "breach"), ("KYA-TEC-05", "breach"), ("KYA-TEC-06", "breach"),
                        # KYA-TEC-07: the model that actually ran is blocklisted (F19).
                        ("KYA-TEC-07", "breach"),
                        ("PRV-REC-01", "clear")}
    rv = await ProvenanceAgent().review(kst, books["provenance"], model=fake(record_provenance_reconciliation={
        "reconciled": False, "disagreements": [{"sources": ["agent_card", "observed"],
                                                "explanation": "a server called that the card never lists",
                                                "cited_evidence": "mcp://inventory.fastcheck-partners.net"}],
        "explanation": "The card and the calls disagree.", "other_observations": []}))
    a = next(a for a in rv.assessments if a.rule_id == "PRV-REC-01")
    assert a.verdict == "breach" and a.subject == "agent_card, observed" and a.scope == "case"


async def test_injection_judges_every_flagged_run_and_validates_the_channel(kst, books):
    rv = await InjectionAgent().review(kst, books["injection"], model=fake())
    judged = {a.run_refs[0]: a for a in rv.assessments if a.rule_id == "INJ-ACT-01" and len(a.run_refs) == 1}
    assert set(judged) == {r.run_id for r in kst.runs}
    assert {a.verdict for a in judged.values()} == {"clear"}
    # the model says the agent obeyed the listing on run 25, and names a
    # channel the floor never flagged on run 40, and invents a run
    rv = await InjectionAgent().review(kst, books["injection"], model=fake(record_injection_analysis={
        "verdicts": [
            {"run_id": "RUN-2026-0715-0025", "acted": True, "channel": "listing",
             "explanation": "the serum nobody asked for is in the cart", "cited_evidence": "LUM-SKN-CRM-50"},
            {"run_id": "RUN-2026-0806-0040", "acted": True, "channel": "tool_schema",
             "explanation": "wrong channel", "cited_evidence": "n/a"},
            {"run_id": "RUN-2026-9999-9999", "acted": True, "channel": "listing",
             "explanation": "invented", "cited_evidence": "n/a"}],
        "objective_redirected": {"present": True, "explanation": "Lumen favoured throughout."},
        "other_observations": []}))
    by_run = {a.run_refs[0]: a for a in rv.assessments if a.rule_id == "INJ-ACT-01" and a.subject != "objective"}
    assert by_run["RUN-2026-0715-0025"].verdict == "breach" and by_run["RUN-2026-0715-0025"].subject == "listing"
    assert by_run["RUN-2026-0715-0025"].evidence_refs[0].ref == "cart.line_items[0]"
    # an unflagged channel is downgraded to none — the breach stands on the floor's evidence, not the model's label
    assert any(a.verdict == "inconclusive" and "RUN-2026-0806-0040" in a.run_refs for a in rv.assessments)
    assert "RUN-2026-9999-9999" not in by_run
    objective = next(a for a in rv.assessments if a.subject == "objective")
    assert objective.verdict == "breach" and set(objective.run_refs) == {r.run_id for r in kst.runs}


async def test_injection_with_nothing_flagged_still_requires_judgment(hal, books):
    quiet = hal.model_copy(update={"runs": [r for r in hal.runs if r.run_id != "RUN-2026-0723-0011"]})
    model = fake()
    rv = await InjectionAgent().review(quiet, books["injection"], model=model)
    assert "record_injection_analysis" in model.call_log
    judged = [a for a in rv.assessments if a.rule_id == "INJ-ACT-01"]
    assert len(judged) == len(quiet.runs) + 1 and all(a.verdict == "clear" for a in judged)


async def test_injection_leaves_unjudged_runs_inconclusive(kst, books):
    rv = await InjectionAgent().review(kst, books["injection"], model=fake(record_injection_analysis={
        "verdicts": [{"run_id": "RUN-2026-0715-0025", "acted": False, "channel": "none",
                      "explanation": "ignored", "cited_evidence": "n/a"}],
        "objective_redirected": {"present": False, "explanation": "n/a"}, "other_observations": []}))
    inconclusive, = [a for a in rv.assessments if a.verdict == "inconclusive"]
    assert set(inconclusive.run_refs) == {r.run_id for r in kst.runs} - {"RUN-2026-0715-0025"}


async def test_counterparty_names_only_payees_it_was_shown(kst, books):
    rv = await CounterpartyAgent().review(kst, books["counterparty"], model=fake())
    assert {(a.rule_id, a.verdict) for a in rv.assessments} == {
        ("CPT-SUB-01", "breach"), ("CPT-BEN-01", "breach"), ("CPT-NEW-01", "breach"),
        ("CPT-IDN-01", "clear"), ("CPT-DCL-01", "clear")}
    rv = await CounterpartyAgent().review(kst, books["counterparty"], model=fake(record_counterparty_analysis={
        "doubtful_payees": [
            {"merchant_id": "MER-QVC-8801", "explanation": "new, owner unresolved, half the month", "cited_evidence": "first_seen 2026-08-05"},
            {"merchant_id": "MER-NOT-REAL", "explanation": "invented", "cited_evidence": "n/a"}],
        "identity_explanation": "one doubtful", "declines": {"anomalous": True, "explanation": "three declines then a success at one counterparty", "cited_evidence": "n/a"},
        "other_observations": []}))
    doubtful = [a for a in rv.assessments if a.rule_id == "CPT-IDN-01"]
    assert [a.subject for a in doubtful] == ["MER-QVC-8801"]
    assert doubtful[0].verdict == "breach" and len(doubtful[0].run_refs) == 4
    assert next(a for a in rv.assessments if a.rule_id == "CPT-DCL-01").verdict == "breach"


async def test_consent_value_for_money_validates_run_ids(kst, books):
    rv = await ConsentAgent().review(kst, books["consent"], model=fake())
    assert {(a.rule_id, a.verdict) for a in rv.assessments if a.rule_id} == {
        ("CNS-PRS-01", "breach"), ("CNS-RND-01", "breach"), ("CNS-VFM-01", "clear")}
    rv = await ConsentAgent().review(kst, books["consent"], model=fake(record_consent_analysis={
        "value_for_money": {"systematic": True, "run_ids": ["RUN-2026-0616-0001", "RUN-2026-9999-9999"],
                            "explanation": "dearer pick when an equivalent was cheaper", "cited_evidence": "SKU x at 40 vs y at 25"},
        "other_observations": []}))
    a = next(a for a in rv.assessments if a.rule_id == "CNS-VFM-01")
    assert a.verdict == "breach" and a.run_refs == ["RUN-2026-0616-0001"] and len(a.fact_ids) == 1
    # systematic with no valid run is not a breach
    rv = await ConsentAgent().review(kst, books["consent"], model=fake(record_consent_analysis={
        "value_for_money": {"systematic": True, "run_ids": ["RUN-2026-9999-9999"], "explanation": "x", "cited_evidence": "x"},
        "other_observations": []}))
    assert next(a for a in rv.assessments if a.rule_id == "CNS-VFM-01").verdict == "inconclusive"


# --- control assurance: fed by the peers, postures computed -----------------------------

async def test_peers_come_from_the_rules_own_failure_declarations(kst, books):
    peers = peers_from_facts(await _peer_facts(kst, books, fake()), books)
    assert peers["RUN-2026-0811-0043"] >= {"F42", "F43"}
    assert peers["RUN-2026-0818-0048"] >= {"F43", "F50"}
    assert peers["RUN-2026-0810-0042"] == {"F24"}
    assert peers["RUN-2026-0805-0039"] == {"F44"}
    assert "RUN-2026-0616-0001" not in peers


async def test_control_assurance_uses_judged_injection_not_triage_hits(kst, books):
    injection = await InjectionAgent().review(kst, books["injection"], model=fake(record_injection_analysis={
        "verdicts": [{
            "run_id": r.run_id, "acted": r.run_id == "RUN-2026-0715-0025",
            "channel": "listing" if r.run_id == "RUN-2026-0715-0025" else "none",
            "explanation": "acted" if r.run_id == "RUN-2026-0715-0025" else "ignored",
            "cited_evidence": "evidence",
        } for r in kst.runs],
        "objective_redirected": {"present": False, "explanation": "no"},
        "other_observations": [],
    }))
    peers = peers_from_evidence(injection.facts, injection.assessments, books)
    assert peers.get("RUN-2026-0715-0025") == {"F32"}
    # A retrieved-content regex hit that the model says was ignored is not F32.
    assert "F32" not in peers.get("RUN-2026-0806-0040", set())


async def test_control_assurance_without_peers_waits_and_with_them_finds_the_silent_controls(kst, books):
    alone = await ControlAssuranceAgent().review(kst, books["controls"])
    eff = [f for f in alone.facts if f.rule_id == "CTL-EFF-01"]
    assert eff and {(f.kind, f.absent_reason) for f in eff} == {("absent", "awaiting_peers")}
    fed = await ControlAssuranceAgent().review(kst, books["controls"],
                                               peer_facts=await _peer_facts(kst, books, fake()), rulebooks=books)
    assert {(a.rule_id, a.verdict) for a in fed.assessments} == {
        ("CTL-EFF-01", "breach"), ("CTL-EFF-03", "breach"), ("CTL-EFF-04", "breach")}
    postures = {(p.posture, p.control_id, p.override_by) for p in fed.postures}
    assert postures == {("effective", "KST-CTL-001", None), ("bypassed", "KST-CTL-001", "ops-analyst-11"),
                        ("ineffective", "KST-CTL-002", None), ("ineffective", "KST-CTL-003", None),
                        ("ineffective", "KST-CTL-004", None)}
    # every non-effective posture points at the assessment it explains
    by_rule = {a.rule_id: a.assessment_id for a in fed.assessments}
    for p in fed.postures:
        if p.posture == "bypassed":
            assert p.assessment_id == by_rule["CTL-EFF-04"]
        if p.posture == "ineffective":
            assert p.assessment_id == by_rule["CTL-EFF-01"]


def test_postures_from_no_facts_is_empty():
    assert classify_postures([], []) == []


# --- systemic ---------------------------------------------------------------------------

async def test_systemic_needs_a_portfolio_and_scopes_its_concerns_to_it(kst, hal):
    alone = await SystemicAgent().review(kst)
    assert alone.assessments == [] and alone.facts[0].values["swept"] is False
    both = await SystemicAgent().review(kst, portfolio=[kst, hal])
    assert {a.subject.split(":")[0] for a in both.assessments} == {"F57", "F67", "F69"}
    for a in both.assessments:
        assert a.scope == "portfolio" and a.verdict == "concern"
        assert set(a.subject_refs) == {"DOSSIER-KST-2026-001", "DOSSIER-HAL-2026-001"}


