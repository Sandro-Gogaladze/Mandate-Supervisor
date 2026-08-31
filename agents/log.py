"""Log agent (PLAN item 7) — entirely LLM-judged, no deterministic
detection rule at all. Revised from the original build, which had a
hardcoded Python threshold check for structuring; that's gone, per
explicit direction: every verdict (structuring, concentration, velocity)
is the model's judgment over real pre-computed evidence
(agents/log_stats.py), not a Python comparison. See
agents/log_reasoning.py's module docstring for the reasoning.

`run()` — Protocol-conformant (agents/base.py), always returns `[]`. There
is nothing left to compute without an LLM call, same shape as Drift's
current stub — this is what the orchestrator (pipeline/graph.py) calls by
default, so the deterministic pipeline path still never needs a key.
`review()` is the only place any of this agent's real analysis happens.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ingestion.normalize import IngestedCase
from schemas import Finding, Observation, Ruleset

from .log_reasoning import analyze_log
from .prompts import effective_text


@dataclass
class LogReview:
    findings: list[Finding]
    observations: list[Observation] = field(default_factory=list)


class LogAgent:
    name = "log"

    def run(self, case: IngestedCase, ruleset: Ruleset | None) -> list[Finding]:
        return []

    async def review(
        self,
        case: IngestedCase,
        ruleset: Ruleset | None,
        *,
        model=None,
        prior_observations: list[Observation] | None = None,
        reviewer_directive: str | None = None,
        prompts: dict[str, dict] | None = None,
        context: dict | None = None,
    ) -> LogReview:
        if ruleset is None:
            return LogReview(findings=[])

        rules = {
            r.type: r for r in ruleset.rules
            if r.status == "active"
            and r.type in ("transaction_structuring_detected", "counterparty_concentration_anomaly", "transaction_velocity_anomaly")
        }
        if len(rules) < 3:
            return LogReview(findings=[])

        findings, observations = await analyze_log(
            case,
            rules["transaction_structuring_detected"],
            rules["counterparty_concentration_anomaly"],
            rules["transaction_velocity_anomaly"],
            model=model,
            prior_observations=prior_observations,
            reviewer_directive=reviewer_directive,
            system_prompt=effective_text(prompts, "SPECIALIST-LOG") if prompts else None,
            context=context,
        )
        return LogReview(findings=findings, observations=observations)
