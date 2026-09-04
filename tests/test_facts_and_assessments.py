"""architecture-v3 Stage 1 — the guarantees that live in the type system.

Every test here corresponds to a row in the guarantees table. If one of
these can be made to pass by a prompt instead, the guarantee isn't real.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas import Assessment, ControlPosture, EvidenceRef, Fact


def _fact(**over) -> Fact:
    return Fact(**{
        "fact_id": "F-1", "case_id": "CASE-1", "domain": "mandate",
        "rule_id": "MND-CAP-01", "kind": "breach",
        "statement": "Cart total 1289.0 exceeds cap 350.0 by 939.0",
        "values": {"cart_total": 1289.0, "cap": 350.0, "excess": 939.0},
        **over,
    })


def _assessment(**over) -> Assessment:
    return Assessment(**{
        "assessment_id": "A-1", "case_id": "CASE-1", "agent": "mandate",
        "rule_id": "MND-CAP-01", "fact_ids": ["F-1"], "verdict": "breach",
        "severity_floor": 0.85, "severity_assessed": 0.85,
        "narrative": "The cart exceeds the cap the human set.",
        **over,
    })


# --- Fact -----------------------------------------------------------------

def test_satisfied_facts_are_recordable():
    """A clean case has to be provably clean rather than merely silent — and
    the eval harness needs true negatives to compute a false-positive rate
    at all."""
    fact = _fact(fact_id="F-2", kind="satisfied", statement="Chain hash recomputes.")
    assert fact.kind == "satisfied"


def test_absent_fact_must_say_why():
    """An unexplained gap is indistinguishable from not having looked."""
    with pytest.raises(ValidationError, match="requires absent_reason"):
        _fact(kind="absent")


def test_absent_reason_is_rejected_on_a_non_absent_fact():
    with pytest.raises(ValidationError, match="only valid when kind='absent'"):
        _fact(kind="breach", absent_reason="missing_block")


def test_rule_outcomes_must_name_their_rule():
    """breach/satisfied/absent are rule outcomes; a measurement need not be."""
    with pytest.raises(ValidationError, match="must name its rule_id"):
        _fact(rule_id=None)


def test_a_gap_must_name_what_is_missing():
    """'Could not evaluate' without saying why is not a supervisory fact."""
    with pytest.raises(ValidationError, match="must name what is missing"):
        _fact(kind="absent", absent_reason="missing_block")
    fact = _fact(kind="absent", absent_reason="missing_block",
                 missing="consent_ceremony.rendered_values")
    assert fact.missing == "consent_ceremony.rendered_values"


def test_rules_that_do_not_apply_name_nothing():
    """`out_of_scope` and `rule_draft` are about the rule, not a gap."""
    assert _fact(kind="absent", absent_reason="out_of_scope").missing is None
    assert _fact(kind="absent", absent_reason="rule_draft").missing is None


def test_missing_is_only_valid_on_an_absent_fact():
    with pytest.raises(ValidationError, match="only valid when kind='absent'"):
        _fact(kind="breach", missing="something")


def test_a_fact_may_cite_its_run():
    fact = _fact(run_ref="RUN-2026-0811-0043")
    assert fact.run_ref == "RUN-2026-0811-0043"


def test_measurements_need_no_rule():
    """Log's rules are all judged, so its check() emits measurements — which
    is what stops its model reasoning over raw rows."""
    fact = _fact(
        fact_id="F-M1", domain="log", rule_id=None, kind="measurement",
        statement="Cluster: 3 payments within 6h totalling 8700.0 against a 3000.0 threshold",
        values={"cluster_sum": 8700.0, "threshold": 3000.0, "window_hours": 6},
    )
    assert fact.rule_id is None


# --- Assessment: the severity guarantee -----------------------------------

def test_agent_cannot_lower_severity_below_the_ruleset_floor():
    """THE guarantee of the severity design. An agent may argue a finding up,
    never down — enforced by a validator, not requested in a prompt."""
    with pytest.raises(ValidationError, match="below the ruleset floor"):
        _assessment(severity_floor=0.85, severity_assessed=0.40)


def test_agent_may_escalate_with_a_reason():
    a = _assessment(
        severity_floor=0.60, severity_assessed=0.90,
        severity_rationale="Four detectors converged on one injected line item.",
    )
    assert a.severity_assessed > a.severity_floor


def test_escalation_without_a_rationale_is_rejected():
    """An unexplained escalation is not reviewable."""
    with pytest.raises(ValidationError, match="without a rationale"):
        _assessment(severity_floor=0.60, severity_assessed=0.90)


# --- Assessment: grounding ------------------------------------------------

def test_a_scoring_verdict_must_cite_a_fact():
    """An assertion with no fact behind it cannot be checked by the critic
    and cannot be defended to a firm."""
    with pytest.raises(ValidationError, match="must cite at least one fact_id"):
        _assessment(fact_ids=[])


def test_non_scoring_verdicts_may_stand_alone():
    """`inconclusive` is the agent saying it evaluated and cannot decide —
    which in v2 had to lie in one direction."""
    a = _assessment(verdict="inconclusive", fact_ids=[], severity_floor=0.0, severity_assessed=0.0)
    assert not a.scores


# --- Assessment: scoring --------------------------------------------------

def test_only_breach_scores():
    """`explained` records 'we looked and it's fine' as distinct from 'we
    didn't look' — and prices it at nothing."""
    explained = _assessment(verdict="explained", narrative="Disclosed subsidiary of the approved supplier.")
    assert explained.weighted() == 0.0
    assert _assessment().weighted() == 0.85


def test_confidence_discounts_the_weight():
    probable = _assessment(confidence="probable")
    possible = _assessment(confidence="possible")
    assert probable.weighted() == pytest.approx(0.85 * 0.7)
    assert possible.weighted() == pytest.approx(0.85 * 0.4)


def test_floor_and_assessed_totals_diverge_only_upward():
    """Both are shown, so a firm can see the derivation from rules alone and
    the supervisory judgment on top of it."""
    a = _assessment(
        severity_floor=0.60, severity_assessed=0.90,
        severity_rationale="Coordinated manipulation, not three coincidences.",
    )
    assert a.weighted(use_assessed=False) == 0.60
    assert a.weighted(use_assessed=True) == 0.90


# --- Assessment: scope and supersession -----------------------------------

def test_run_scope_must_name_its_runs():
    """A whole-dossier call is only viable if every claim can be checked
    against a specific run."""
    with pytest.raises(ValidationError, match="must name the runs"):
        _assessment(scope="run")
    a = _assessment(scope="run", run_refs=["RUN-2026-0811-0043"])
    assert a.run_refs == ["RUN-2026-0811-0043"]


def test_portfolio_scope_must_name_its_cases():
    with pytest.raises(ValidationError, match="must list the case ids"):
        _assessment(scope="portfolio", agent="systemic")


def test_supersession_is_recorded_not_edited():
    """Round 3 overruling round 1 leaves both on the ledger; the audit trail
    shows the case changing its mind and why."""
    later = _assessment(
        assessment_id="A-9", round=3, verdict="explained", supersedes="A-1",
        narrative="Disclosed subsidiary — established from the officer's context.",
    )
    assert later.supersedes == "A-1"
    assert later.round == 3


# --- ControlPosture -------------------------------------------------------

def test_absent_posture_needs_no_finding():
    """A firm that declared no control for a risk its own mandate creates has
    a governance failure whether or not anything went wrong."""
    p = ControlPosture(
        case_id="CASE-1", posture="absent",
        narrative="No control declared for cumulative spend against a GEL 50,000 ceiling.",
    )
    assert p.assessment_id is None


def test_bypassed_must_name_who_overrode_it():
    """An anonymous override is not a supervisable fact — the conduct
    question is who, on what authority, how often."""
    with pytest.raises(ValidationError, match="must name who overrode"):
        ControlPosture(case_id="CASE-1", posture="bypassed", narrative="Overridden.")


def test_evidence_refs_are_structured_not_prose():
    """Prose evidence can't be resolved by the critic, linked by the UI, or
    cited by a report."""
    ref = EvidenceRef(kind="transaction", ref="TXN-2026-0142", value=2900.0)
    a = _assessment(evidence_refs=[ref])
    assert a.evidence_refs[0].ref == "TXN-2026-0142"
