"""Facts → Assessments → Findings (agents/assess.py)."""
from __future__ import annotations

import pytest

from agents.assess import (
    contained_runs,
    data_gap_assessments,
    floor_assessments,
    project_finding,
    project_findings,
    rules_by_id,
)
from agents.facts import FactBuilder
from schemas import Rule, Ruleset


def _ruleset(*rules: tuple[str, float]) -> Ruleset:
    return Ruleset(
        ruleset_id="T", domain="test", version="9.9", as_of="2026-09-03", description="t",
        rules=[Rule(rule_id=rid, type=f"type_{i}", version=1, status="active",
                    effective_from="2026-01-01", severity_weight=w,
                    finding_type=f"ft_{rid.lower()}", description="d")
               for i, (rid, w) in enumerate(rules)])


@pytest.fixture
def rs():
    return _ruleset(("R-1", 0.8), ("R-2", 0.4))


@pytest.fixture
def fb():
    return FactBuilder("CASE-1", "test")


def _rule(rs, rid):
    return next(r for r in rs.rules if r.rule_id == rid)


# --- floor assessments -----------------------------------------------------

def test_one_assessment_per_breached_rule_citing_every_run(rs, fb):
    r1, r2 = _rule(rs, "R-1"), _rule(rs, "R-2")
    facts = [fb.breach(r1, "a", run_ref="RUN-B"), fb.breach(r1, "b", run_ref="RUN-A"),
             fb.satisfied(r1, "c", run_ref="RUN-C"), fb.breach(r2, "d")]
    out = floor_assessments(facts, rs, agent="t")
    assert [a.assessment_id for a in out] == ["CASE-1:t:R-1:r1", "CASE-1:t:R-2:r1"]
    a1, a2 = out
    assert (a1.verdict, a1.scope, a1.run_refs) == ("breach", "run", ["RUN-A", "RUN-B"])
    assert a1.fact_ids == ["CASE-1:R-1:RUN-B", "CASE-1:R-1:RUN-A"]
    assert a1.severity_floor == a1.severity_assessed == 0.8
    assert a1.ruleset_version == "9.9"
    assert (a2.scope, a2.run_refs, a2.fact_ids) == ("case", [], ["CASE-1:R-2"])


def test_no_breach_no_assessment(rs, fb):
    facts = [fb.satisfied(_rule(rs, "R-1"), "fine", run_ref="RUN-A"),
             fb.absent(_rule(rs, "R-2"), "out_of_scope", "n/a")]
    assert floor_assessments(facts, rs, agent="t") == []


def test_a_breach_the_firm_contained_is_explained_not_priced(rs, fb):
    r1 = _rule(rs, "R-1")
    facts = [fb.breach(r1, "over cap", run_ref="RUN-BLOCKED"),
             fb.breach(r1, "over cap", run_ref="RUN-SETTLED")]
    out = floor_assessments(facts, rs, agent="t", contained={"RUN-BLOCKED": ["CTL-9"]})
    by_id = {a.assessment_id: a for a in out}
    open_ = by_id["CASE-1:t:R-1:r1"]
    held = by_id["CASE-1:t:R-1:explained:r1"]
    assert (open_.verdict, open_.run_refs) == ("breach", ["RUN-SETTLED"])
    assert (held.verdict, held.run_refs) == ("explained", ["RUN-BLOCKED"])
    assert "CTL-9" in held.narrative and "held" in held.narrative
    assert held.weighted() == 0.0 and open_.weighted() == 0.8
    # the explained assessment still cites its fact — the deviation is on record
    assert held.fact_ids == ["CASE-1:R-1:RUN-BLOCKED"]


def test_a_breach_citing_an_unknown_rule_cannot_be_priced(rs, fb):
    stranger = _ruleset(("R-9", 0.5))
    facts = [fb.breach(_rule(stranger, "R-9"), "x", run_ref="RUN-A")]
    with pytest.raises(ValueError, match="R-9"):
        floor_assessments(facts, rs, agent="t")


# --- data gaps -------------------------------------------------------------

def test_missing_blocks_roll_up_into_one_concern_per_block(rs, fb):
    r1, r2 = _rule(rs, "R-1"), _rule(rs, "R-2")
    facts = [
        fb.absent(r1, "missing_block", "no consent", missing="consent_ceremony", run_ref="RUN-A"),
        fb.absent(r1, "missing_block", "no consent", missing="consent_ceremony", run_ref="RUN-B"),
        fb.absent(r2, "missing_block", "no consent", missing="consent_ceremony"),
        fb.absent(r2, "out_of_scope", "n/a"),
    ]
    a, = data_gap_assessments(facts, agent="t")
    assert a.assessment_id == "CASE-1:t:gap:consent_ceremony:r1"
    assert (a.verdict, a.rule_id, a.scope, a.run_refs) == ("concern", None, "run", ["RUN-A", "RUN-B"])
    assert a.subject == "data_gap:consent_ceremony"
    assert "R-1 (2 runs)" in a.narrative and "R-2" in a.narrative
    assert len(a.fact_ids) == 3
    assert not a.scores


def test_only_the_submissions_gaps_become_findings(rs, fb):
    """A draft rule, a rule that does not apply, a register the regulator has
    not filled, a peer that has not run — none is the firm's gap."""
    r = _rule(rs, "R-1")
    facts = [fb.absent(r, "rule_draft", "draft"),
             fb.absent(r, "out_of_scope", "n/a", run_ref="RUN-A"),
             fb.absent(r, "no_registry_record", "no agent", missing="registry:agents[X]"),
             fb.absent(r, "awaiting_peers", "later", missing="peer findings", run_ref="RUN-B")]
    assert data_gap_assessments(facts, agent="t") == []
    thin = fb.absent(r, "insufficient_history", "too few", missing="transaction_history")
    a, = data_gap_assessments([thin], agent="t")
    assert "too thin" in a.narrative


# --- projection ------------------------------------------------------------

def test_a_finding_is_the_assessment_under_its_own_id(rs, fb):
    r1 = _rule(rs, "R-1")
    a, = floor_assessments([fb.breach(r1, "x", run_ref="RUN-A")], rs, agent="t")
    f = project_finding(a, rules_by_id(rs))
    assert f.finding_id == a.assessment_id
    assert (f.agent, f.type, f.rule_id, f.severity_weight) == ("t", "ft_r-1", "R-1", 0.8)
    assert f.summary == a.narrative
    assert f.details["fact_ids"] == a.fact_ids and f.details["run_refs"] == ["RUN-A"]


def test_non_scoring_verdicts_project_with_no_weight(rs, fb):
    r1 = _rule(rs, "R-1")
    held, = floor_assessments([fb.breach(r1, "x", run_ref="RUN-A")], rs, agent="t",
                              contained={"RUN-A": ["C"]})
    gap, = data_gap_assessments([fb.absent(r1, "missing_block", "m", missing="block.x")],
                                agent="t")
    fs = project_findings([held, gap], [rs])
    assert [f.severity_weight for f in fs] == [None, None]
    assert [f.type for f in fs] == ["ft_r-1", "data_gap"]


def test_confidence_discounts_the_projected_weight(rs, fb):
    a, = floor_assessments([fb.breach(_rule(rs, "R-1"), "x", run_ref="RUN-A")], rs, agent="t")
    probable = a.model_copy(update={"confidence": "probable"})
    assert project_finding(probable, rules_by_id(rs)).severity_weight == pytest.approx(0.56)


def test_projecting_an_assessment_whose_rule_is_unknown_raises(rs, fb):
    a, = floor_assessments([fb.breach(_rule(rs, "R-1"), "x")], rs, agent="t")
    with pytest.raises(ValueError, match="R-1"):
        project_finding(a, {})


# --- against the corpus ----------------------------------------------------

def test_contained_runs_is_the_blocked_run_and_its_control():
    from data.dossier_loader import load

    d = load("data/dossiers/DOSSIER-KST-2026-001")
    assert contained_runs(d) == {"RUN-2026-0722-0030": ["KST-CTL-001"]}
