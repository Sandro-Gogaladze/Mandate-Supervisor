"""agents/grounding.py — the deterministic validator behind the
drafting agent's regenerate-then-block loop (PLAN item 12)."""
from __future__ import annotations

from agents.grounding import check_grounding
from schemas import DraftReport, Finding, Observation, ReportSection, RiskScore


def _finding(fid: str, severity: float | None = 0.5) -> Finding:
    """A breach by default. `severity=None` is a rule that was SATISFIED —
    the majority of what a real pass records."""
    return Finding(finding_id=fid, case_id="CASE-T", agent="mandate", type="cap_exceeded",
                   summary="s", severity_weight=severity)


def _section(title: str, ids: list[str], character: str | None = "adverse", body: str = "b") -> ReportSection:
    return ReportSection(title=title, body=body, cited_finding_ids=ids, character=character)


def _score(total: float = 4.25, tier: str = "escalate", label: str = "Escalate") -> RiskScore:
    return RiskScore(case_id="CASE-T", total=total, tier=tier, tier_label=label,
                     tier_guidance="g", factors=[], config_version="test")


def _obs() -> Observation:
    return Observation(case_id="CASE-T", agent="log", note="hunch", cited_evidence="e")


def _report(sections: list[ReportSection], note: str | None = None) -> DraftReport:
    return DraftReport(case_id="CASE-T", overall_assessment="ok", sections=sections, open_observations_note=note)


def test_grounded_report_passes():
    findings = [_finding("F-1"), _finding("F-2")]
    report = _report([_section("Breach", ["F-1", "F-2"])])
    assert check_grounding(report, findings, []) == []


def test_invented_citation_flagged():
    report = _report([_section("Breach", ["F-1", "F-99"])])
    problems = check_grounding(report, [_finding("F-1")], [])
    assert any("'F-99'" in p and "does not exist" in p for p in problems)


def test_omitted_finding_flagged():
    findings = [_finding("F-1"), _finding("F-2")]
    report = _report([_section("Partial", ["F-1"])])
    problems = check_grounding(report, findings, [])
    assert any("'F-2'" in p and "not cited" in p for p in problems)


def test_uncited_section_flagged_when_findings_exist():
    report = _report([
        _section("Breach", ["F-1"]),
        _section("Editorial", [], body="free-floating prose"),
    ])
    problems = check_grounding(report, [_finding("F-1")], [])
    assert any("cites no findings" in p for p in problems)


def test_clean_case_with_no_sections_passes():
    assert check_grounding(_report([]), [], []) == []


def test_sections_on_a_clean_case_flagged():
    report = _report([_section("Invented", [])])
    problems = check_grounding(report, [], [])
    assert any("zero findings" in p for p in problems)


def test_observations_require_the_labeled_note():
    problems = check_grounding(_report([]), [], [_obs()])
    assert any("open_observations_note" in p for p in problems)


def test_note_without_observations_flagged():
    problems = check_grounding(_report([], note="phantom open items"), [], [])
    assert any("no observations" in p for p in problems)


def test_note_present_with_observations_passes():
    assert check_grounding(_report([], note="one unverified hunch"), [], [_obs()]) == []


# --- characterisation: does the section describe what it cites? -------------

def test_satisfied_checks_written_up_as_adverse_flagged():
    """The hole this rule closes: citations real, coverage complete, and the
    section still calls forty clean checks a failure."""
    findings = [_finding("F-1", None), _finding("F-2", None)]
    report = _report([_section("Mandate breaches", ["F-1", "F-2"], "adverse")])
    problems = check_grounding(report, findings, [])
    assert any("declared 'adverse'" in p and "is 'clear'" in p for p in problems)


def test_breaches_written_up_as_clear_flagged():
    report = _report([_section("Other areas reviewed — clear", ["F-1"], "clear")])
    problems = check_grounding(report, [_finding("F-1")], [])
    assert any("is 'adverse'" in p for p in problems)


def test_clear_section_over_satisfied_checks_passes():
    findings = [_finding("F-1", None), _finding("F-2", None)]
    report = _report([_section("Other areas reviewed — clear", ["F-1", "F-2"], "clear")])
    assert check_grounding(report, findings, []) == []


def test_mixed_section_must_be_declared_mixed():
    findings = [_finding("F-1"), _finding("F-2", None)]
    assert check_grounding(_report([_section("Both", ["F-1", "F-2"], "mixed")]), findings, []) == []
    problems = check_grounding(_report([_section("Both", ["F-1", "F-2"], "adverse")]), findings, [])
    assert any("is 'mixed'" in p for p in problems)


def test_undeclared_character_flagged():
    report = _report([_section("Breach", ["F-1"], None)])
    problems = check_grounding(report, [_finding("F-1")], [])
    assert any("declares no character" in p for p in problems)


# --- the risk score, the one claim that rests on no finding ----------------

def _scored(assessment: str) -> DraftReport:
    return DraftReport(case_id="CASE-T", overall_assessment=assessment, sections=[])


def test_stated_score_and_tier_pass():
    assert check_grounding(_scored("Risk score 4.25 — tier Escalate."), [], [], risk_score=_score()) == []


def test_missing_score_flagged():
    problems = check_grounding(_scored("Serious breaches, tier Escalate."), [], [], risk_score=_score())
    assert any("does not state the risk score total" in p for p in problems)


def test_rounded_score_flagged():
    """'state it exactly as given' — 18.88 for 18.875 is the model doing its
    own arithmetic on a number computed deterministically."""
    problems = check_grounding(_scored("Risk score 18.88 — tier Escalate."), [], [],
                               risk_score=_score(total=18.875))
    assert any("does not state the risk score total" in p for p in problems)


def test_missing_tier_flagged():
    problems = check_grounding(_scored("Risk score 4.25."), [], [], risk_score=_score())
    assert any("does not state the risk tier" in p for p in problems)


def test_tier_id_accepted_in_place_of_label():
    assert check_grounding(_scored("Risk score 4.25, escalate."), [], [], risk_score=_score()) == []


def test_no_score_supplied_is_not_checked():
    assert check_grounding(_scored("no numbers here"), [], []) == []
