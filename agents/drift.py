"""Drift agent (D2) — what changed, and when did it start?

Entirely judged, same design as Log: agents/drift_stats.py computes real
statistics (PSI, z-score, frequency shift) between a baseline window and
everything after it, and nothing pre-decides whether a shift counts as
drift. That verdict is the model's, in agents/drift_reasoning.py.

- `run()` — below the rule's `min_total_transactions` the one fact is
  `absent/insufficient_history`: whether there is enough history to split
  at all is a row count, not a judgement, and saying so is different from
  saying nothing. Above it, the split is a measurement.
- `review()` — the model's verdict becomes a `breach` or `clear`
  assessment citing that measurement.

The `change_log` is what the onset lands on: the same statistics are
evaluated before and after each dated event the operator logged, and the
model names the event (validated in code) rather than a date.
"""
from __future__ import annotations

from schemas import Assessment, EvidencePack, Fact, FactBuilder, Observation, Ruleset, typed_params
from schemas.dossier import LoadedDossier

from .base import SpecialistReview
from .drift_reasoning import analyze_drift, structured_view
from .prompts import effective_text

DriftReview = SpecialistReview


def _rule(ruleset: Ruleset | None):
    if ruleset is None:
        return None
    return next((r for r in ruleset.rules
                 if r.type == "behavioral_drift_detected" and r.status == "active"), None)


class DriftAgent:
    name = "drift"

    def run(self, dossier: LoadedDossier, ruleset: Ruleset | None, *,
            evidence: EvidencePack | None = None) -> list[Fact]:
        rule = _rule(ruleset)
        if rule is None:
            return []
        fb = FactBuilder(dossier.dossier.dossier_id, self.name)
        params = typed_params(rule)
        n = len(dossier.transaction_history)
        if n < params.min_total_transactions:
            return [fb.absent(
                rule, "insufficient_history",
                f"{n} transaction(s) are below the {params.min_total_transactions} needed for a "
                f"baseline/comparison split; no drift estimate is possible.",
                missing="transaction_history",
                values={"transactions": n, "min_total_transactions": params.min_total_transactions})]
        view = structured_view(dossier, rule)
        strongest = max((c for c in view["change_points"] if c.get("evaluable")),
                        key=lambda c: c["counterparty_mix_psi"] + c["mcc_mix_psi"], default=None)
        return [fb.measurement(
            "baseline_split",
            f"Baseline of {view['baseline_transaction_count']} vs comparison of "
            f"{view['comparison_transaction_count']} transactions: amount z-score "
            f"{view['amount_shift'].get('z_score')}, counterparty-mix PSI "
            f"{view['counterparty_mix_psi']}, MCC-mix PSI {view['mcc_mix_psi']}."
            + (f" Largest before/after shift at change_log {strongest['ref']} ({strongest['at'][:10]}): "
               f"counterparty-mix PSI {strongest['counterparty_mix_psi']}." if strongest else ""),
            rule=rule, values=view)]

    def assess(self, facts: list[Fact], ruleset: Ruleset | None,
               dossier: LoadedDossier, *, round: int = 1) -> list[Assessment]:
        from .assess import data_gap_assessments

        return data_gap_assessments(facts, agent=self.name, round=round)

    async def review(
        self,
        dossier: LoadedDossier,
        ruleset: Ruleset | None,
        *,
        evidence: EvidencePack | None = None,
        model=None,
        prior_observations: list[Observation] | None = None,
        reviewer_directive: str | None = None,
        prompts: dict[str, dict] | None = None,
        context: dict | None = None,
        round: int = 1,
    ) -> SpecialistReview:
        rule = _rule(ruleset)
        if rule is None:
            return SpecialistReview(facts=[], assessments=[])
        facts = self.run(dossier, ruleset, evidence=evidence)
        assessments = self.assess(facts, ruleset, dossier, round=round)
        if any(f.kind == "absent" for f in facts):
            return SpecialistReview(facts=facts, assessments=assessments, insufficient_baseline=True)

        judged, observations = await analyze_drift(
            dossier, facts, rule, model=model, prior_observations=prior_observations,
            reviewer_directive=reviewer_directive,
            system_prompt=effective_text(prompts, "SPECIALIST-DRIFT") if prompts else None,
            context=context, round=round,
        )
        return SpecialistReview(facts=facts, assessments=assessments + judged,
                                observations=observations)
