"""The case risk score (PLAN item 11) — a pure function, no LLM anywhere.

CLAUDE.md's exact framing: this is "the only honest version of
'explainable, factor-level scoring'". Same findings in, same score out,
every time; when a firm challenges the number, the answer is a printable
derivation — these findings × these ruleset severity_weights, tiered by
this config version. An LLM-assigned score would be an opinion wearing a
number.

Only `Finding`s score. `Observation`s (unverified model hunches) are not
an input to this function *by signature*, not just by convention — the
strongest way to keep "never scored" true forever.

A finding with `severity_weight=None` contributes 0.0 but still counts in
its factor's `finding_count` — visible in the breakdown, priced at
nothing, rather than silently invisible.
"""
from __future__ import annotations

from schemas import Finding, RiskFactor, RiskScore, ScoringConfig

_AGENTS = ("mandate", "kya", "log", "drift")

__all__ = ["score_findings"]


def score_findings(case_id: str, findings: list[Finding], config: ScoringConfig) -> RiskScore:
    factors = []
    for agent in _AGENTS:
        agent_findings = [f for f in findings if f.agent == agent]
        factors.append(RiskFactor(
            agent=agent,
            score=round(sum(f.severity_weight or 0.0 for f in agent_findings), 4),
            finding_count=len(agent_findings),
        ))

    total = round(sum(f.score for f in factors), 4)

    # Highest tier whose floor the score reaches. The config is data, so
    # don't trust its ordering; and if a (mis)configured tier set leaves the
    # score below every floor, fall back to the lowest-floor tier rather
    # than crash a live review over a config edit.
    reached = [t for t in config.tiers if total >= t.min_score]
    tier = (
        max(reached, key=lambda t: t.min_score)
        if reached
        else min(config.tiers, key=lambda t: t.min_score)
    )

    return RiskScore(
        case_id=case_id,
        total=total,
        tier=tier.tier,
        tier_label=tier.label,
        tier_guidance=tier.guidance,
        factors=factors,
        config_version=config.version,
    )
