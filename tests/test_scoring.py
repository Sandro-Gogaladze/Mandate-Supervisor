"""pipeline/scoring.py — the pure risk-score function (PLAN item 11) and
its tier config. No LLM anywhere in this path, by design."""
from __future__ import annotations

from pipeline.scoring import score_findings
from registry.loader import load_scoring_config
from schemas import Finding, ScoringConfig, ScoringTier


def _finding(agent: str, weight: float | None, n: int = 1) -> Finding:
    return Finding(
        finding_id=f"F-{agent}-{n}", case_id="CASE-T", agent=agent, type="t",
        severity_weight=weight, summary="s",
    )


def _config() -> ScoringConfig:
    return ScoringConfig(
        version="test.1",
        tiers=[
            ScoringTier(tier="escalate", min_score=2.0, label="Escalate", guidance="act"),
            ScoringTier(tier="review", min_score=0.75, label="Review", guidance="look"),
            ScoringTier(tier="clear", min_score=0.0, label="Clear", guidance="ok"),
        ],
    )


def test_no_findings_scores_zero_and_clear():
    score = score_findings("CASE-T", [], _config())
    assert score.total == 0.0
    assert score.tier == "clear"
    assert [f.score for f in score.factors] == [0.0, 0.0, 0.0, 0.0]


def test_weights_sum_per_agent_and_in_total():
    findings = [
        _finding("mandate", 0.8, 1), _finding("mandate", 0.6, 2),
        _finding("log", 0.7, 1),
    ]
    score = score_findings("CASE-T", findings, _config())
    by_agent = {f.agent: f for f in score.factors}
    assert by_agent["mandate"].score == 1.4
    assert by_agent["mandate"].finding_count == 2
    assert by_agent["log"].score == 0.7
    assert by_agent["kya"].score == 0.0
    assert score.total == 2.1
    assert score.tier == "escalate"


def test_tier_floors_are_inclusive():
    assert score_findings("CASE-T", [_finding("kya", 0.75)], _config()).tier == "review"
    assert score_findings("CASE-T", [_finding("kya", 2.0)], _config()).tier == "escalate"
    assert score_findings("CASE-T", [_finding("kya", 0.74)], _config()).tier == "clear"


def test_none_weight_counts_but_scores_nothing():
    score = score_findings("CASE-T", [_finding("drift", None)], _config())
    by_agent = {f.agent: f for f in score.factors}
    assert by_agent["drift"].score == 0.0
    assert by_agent["drift"].finding_count == 1  # visible, priced at nothing
    assert score.tier == "clear"


def test_misconfigured_tiers_fall_back_to_lowest_floor_instead_of_crashing():
    config = ScoringConfig(
        version="test.bad",
        tiers=[ScoringTier(tier="review", min_score=5.0, label="Review", guidance="g")],
    )
    score = score_findings("CASE-T", [], config)
    assert score.tier == "review"  # lowest (only) floor, not a crash mid-review


def test_deterministic_same_inputs_same_score():
    findings = [_finding("mandate", 0.8), _finding("log", 0.3)]
    a = score_findings("CASE-T", findings, _config())
    b = score_findings("CASE-T", findings, _config())
    assert a == b


def test_real_config_loads_and_covers_zero():
    config = load_scoring_config()
    assert config.version
    assert min(t.min_score for t in config.tiers) == 0.0  # every score lands somewhere
    score = score_findings("CASE-T", [], config)
    assert score.config_version == config.version
