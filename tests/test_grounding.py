"""agents/grounding.py — the deterministic validator behind the
drafting agent's regenerate-then-block loop (PLAN item 12)."""
from __future__ import annotations

from agents.grounding import check_grounding
from schemas import DraftReport, Finding, Observation, ReportSection


def _finding(fid: str) -> Finding:
    return Finding(finding_id=fid, case_id="CASE-T", agent="mandate", type="cap_exceeded", summary="s")


def _obs() -> Observation:
    return Observation(case_id="CASE-T", agent="log", note="hunch", cited_evidence="e")


def _report(sections: list[ReportSection], note: str | None = None) -> DraftReport:
    return DraftReport(case_id="CASE-T", overall_assessment="ok", sections=sections, open_observations_note=note)


def test_grounded_report_passes():
    findings = [_finding("F-1"), _finding("F-2")]
    report = _report([ReportSection(title="Breach", body="b", cited_finding_ids=["F-1", "F-2"])])
    assert check_grounding(report, findings, []) == []


def test_invented_citation_flagged():
    report = _report([ReportSection(title="Breach", body="b", cited_finding_ids=["F-1", "F-99"])])
    problems = check_grounding(report, [_finding("F-1")], [])
    assert any("'F-99'" in p and "does not exist" in p for p in problems)


def test_omitted_finding_flagged():
    findings = [_finding("F-1"), _finding("F-2")]
    report = _report([ReportSection(title="Partial", body="b", cited_finding_ids=["F-1"])])
    problems = check_grounding(report, findings, [])
    assert any("'F-2'" in p and "not cited" in p for p in problems)


def test_uncited_section_flagged_when_findings_exist():
    report = _report([
        ReportSection(title="Breach", body="b", cited_finding_ids=["F-1"]),
        ReportSection(title="Editorial", body="free-floating prose", cited_finding_ids=[]),
    ])
    problems = check_grounding(report, [_finding("F-1")], [])
    assert any("cites no findings" in p for p in problems)


def test_clean_case_with_no_sections_passes():
    assert check_grounding(_report([]), [], []) == []


def test_sections_on_a_clean_case_flagged():
    report = _report([ReportSection(title="Invented", body="b", cited_finding_ids=[])])
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
