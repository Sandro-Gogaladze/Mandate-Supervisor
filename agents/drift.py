"""Drift agent (PLAN item 8) — entirely LLM-judged, same design as the
revised Log agent (agents/log.py): agents/drift_stats.py computes real
statistics (PSI, z-score, frequency shift), but nothing pre-decides
whether a shift counts as drift. That verdict is the model's, in
agents/drift_reasoning.py.

`run()` — Protocol-conformant (agents/base.py), always returns `[]`; all
real analysis is in `review()`, same as Log.

`insufficient_baseline` is the one prerequisite check kept outside the
model: whether there's enough history to attempt a baseline/comparison
split at all is a data-availability fact (a row count), not a judgment
about behavior, same reasoning as Log's empty-history short-circuit.
Below `min_total_transactions` (ruleset param, default 30 — PLAN item 8's
own "insufficient_baseline under 30 tx"), review() reports that directly
without calling the model.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ingestion.normalize import IngestedCase
from schemas import Finding, Observation, Ruleset, typed_params

from .drift_reasoning import analyze_drift


@dataclass
class DriftReview:
    findings: list[Finding]
    observations: list[Observation] = field(default_factory=list)
    insufficient_baseline: bool = False


class DriftAgent:
    name = "drift"

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
    ) -> DriftReview:
        if ruleset is None:
            return DriftReview(findings=[])

        rule = next(
            (r for r in ruleset.rules if r.type == "behavioral_drift_detected" and r.status == "active"),
            None,
        )
        if rule is None:
            return DriftReview(findings=[])

        params = typed_params(rule)
        if len(case.case.transaction_history) < params.min_total_transactions:
            return DriftReview(findings=[], insufficient_baseline=True)

        findings, observations = await analyze_drift(case, rule, model=model, prior_observations=prior_observations, reviewer_directive=reviewer_directive)
        return DriftReview(findings=findings, observations=observations)
