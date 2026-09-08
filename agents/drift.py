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

from .base import SpecialistReview, narrated
from .drift_reasoning import analyze_drift, structured_view
from .prompts import effective_text

DriftReview = SpecialistReview


def _rule(ruleset: Ruleset | None, rule_type: str = "behavioral_drift_detected"):
    if ruleset is None:
        return None
    return next((r for r in ruleset.rules
                 if r.type == rule_type and r.status == "active"), None)


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
        stability = self._stability_fact(fb, ruleset, dossier, view)
        return stability + [fb.measurement(
            "baseline_split",
            f"Baseline of {view['baseline_transaction_count']} vs comparison of "
            f"{view['comparison_transaction_count']} transactions: amount z-score "
            f"{view['amount_shift'].get('z_score')}, counterparty-mix PSI "
            f"{view['counterparty_mix_psi']}, MCC-mix PSI {view['mcc_mix_psi']}."
            + (f" Largest before/after shift at change_log {strongest['ref']} ({strongest['at'][:10]}): "
               f"counterparty-mix PSI {strongest['counterparty_mix_psi']}." if strongest else ""),
            rule=rule, values=view)]

    def _stability_fact(self, fb, ruleset, dossier, view) -> list[Fact]:
        """DRIFT-BAS-01 — can the baseline carry the question at all?"""
        rule = _rule(ruleset, "baseline_window_is_stable")
        if rule is None:
            return []
        from .drift_stats import baseline_stability, split_baseline, to_dataframe

        params = typed_params(_rule(ruleset))
        baseline, _ = split_baseline(to_dataframe(dossier.transaction_history),
                                     baseline_window_days=params.baseline_window_days)
        stats = baseline_stability(baseline)
        if not stats["evaluable"]:
            return [fb.absent(rule, "insufficient_history",
                              f"The baseline holds {stats['baseline_transactions']} transaction(s) — "
                              f"too few to split and check against itself.",
                              missing="transaction_history", values=stats)]
        limit = typed_params(rule).max_baseline_z
        z = stats["amount_z_score"]
        unstable = z is not None and abs(z) > limit
        return [fb.verdict(
            rule, unstable,
            f"The baseline is already moving: its two halves differ by {z} standard deviations in "
            f"average transaction size, past the {limit} a baseline may carry. A comparison against "
            f"it measures nothing.",
            f"The baseline holds steady across its own two halves (amount z-score {z}, limit "
            f"{limit}), so it can carry a comparison.",
            values={**stats, "max_baseline_z": limit})]

    def assess(self, facts: list[Fact], ruleset: Ruleset | None,
               dossier: LoadedDossier, *, round: int = 1) -> list[Assessment]:
        from .assess import data_gap_assessments

        out = data_gap_assessments(facts, agent=self.name, round=round)
        # An unstable baseline is an evidence problem, not misconduct: the
        # agent did nothing wrong, we simply cannot ask the question of it. So
        # it is a `concern` — surfaced to the officer, never scored — rather
        # than the `breach` the generic floor would mint.
        for f in facts:
            if f.rule_id and f.kind == "breach" and f.rule_id.endswith("BAS-01"):
                rule = _rule(ruleset, "baseline_window_is_stable")
                out.append(Assessment(
                    assessment_id=f"{f.case_id}:drift:{f.rule_id}:r{round}", case_id=f.case_id,
                    round=round, scope="case", agent=self.name, rule_id=f.rule_id,
                    fact_ids=[f.fact_id], verdict="concern", confidence="certain",
                    severity_floor=rule.severity_weight if rule else 0.4,
                    severity_assessed=rule.severity_weight if rule else 0.4,
                    narrative=f.statement))
        return out

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
        narrate: bool = True,
    ) -> SpecialistReview:
        rule = _rule(ruleset)
        if rule is None:
            return SpecialistReview(facts=[], assessments=[])
        facts = self.run(dossier, ruleset, evidence=evidence)
        assessments = self.assess(facts, ruleset, dossier, round=round)
        if any(f.kind == "absent" for f in facts):
            # There is no drift judgement to narrate when the baseline is too
            # small. Returning the deterministic data-gap assessment keeps
            # this path offline as promised.
            return SpecialistReview(facts=facts, assessments=assessments, insufficient_baseline=True)

        judged, observations = await analyze_drift(
            dossier, facts, rule, model=model, prior_observations=prior_observations,
            reviewer_directive=reviewer_directive,
            system_prompt=effective_text(prompts, "SPECIALIST-DRIFT") if prompts else None,
            context=context, ruleset=ruleset, round=round,
        )
        return await narrated(SpecialistReview(facts=facts, assessments=assessments + judged,
                                observations=observations), self.name, dossier,
                              model=model, prompts=prompts, narrate=narrate)
