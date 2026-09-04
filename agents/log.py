"""Log agent (D1) — what does this history reveal?

All three of Log's rules are judged: agents/log_stats.py computes the real
statistics (sums, per-counterparty totals, candidate same-counterparty
clusters, gap distributions) and nothing in this codebase pre-decides
whether a candidate cluster or a concentration share actually *counts* as
reportable — every verdict is the model's, over the numbers.

Under the fact contract that split is literal:

- `run()` — the floor emits **measurements**: one per judged rule carrying
  the evidence that rule's judgement rests on, plus the shared statistics.
  With no transaction history it emits `absent/insufficient_history` for
  each rule — visibly, rather than staying silent.
- `review()` — the model's verdicts become assessments (`breach` or
  `clear`) citing those measurement facts, so the critic can check every
  quoted number against what the model was actually shown.
"""
from __future__ import annotations

from schemas import Assessment, EvidencePack, Fact, FactBuilder, Observation, Ruleset
from schemas.dossier import LoadedDossier

from .base import SpecialistReview
from .log_reasoning import analyze_log, structured_view
from .prompts import effective_text

LogReview = SpecialistReview

_RULE_TYPES = ("transaction_structuring_detected", "counterparty_concentration_anomaly",
               "transaction_velocity_anomaly")


def _rules(ruleset: Ruleset | None) -> dict:
    if ruleset is None:
        return {}
    return {r.type: r for r in ruleset.rules if r.status == "active" and r.type in _RULE_TYPES}


class LogAgent:
    name = "log"

    def run(self, dossier: LoadedDossier, ruleset: Ruleset | None, *,
            evidence: EvidencePack | None = None) -> list[Fact]:
        rules = _rules(ruleset)
        if len(rules) < 3:
            return []
        fb = FactBuilder(dossier.dossier.dossier_id, self.name)
        n = len(dossier.transaction_history)
        if n == 0:
            return [fb.absent(r, "insufficient_history",
                              f"{r.rule_id} judges the transaction pattern; no transaction history "
                              f"was submitted.", missing="transaction_history",
                              values={"transactions": 0})
                    for r in rules.values()]
        view = structured_view(dossier, rules["transaction_structuring_detected"],
                               rules["counterparty_concentration_anomaly"])
        npc = view["latest_month_concentration"]
        top = npc["counterparties"][0] if npc["counterparties"] else None
        return [
            fb.measurement("candidate_clusters",
                           f"{len(view['candidate_structuring_clusters'])} candidate "
                           f"same-counterparty cluster(s) within {view['window_hours']}h against a "
                           f"reporting-flag threshold of {view['reporting_flag_threshold']}.",
                           rule=rules["transaction_structuring_detected"],
                           values={"clusters": view["candidate_structuring_clusters"],
                                   "reporting_flag_threshold": view["reporting_flag_threshold"],
                                   "window_hours": view["window_hours"],
                                   "min_cluster_size": view["min_cluster_size"]}),
            fb.measurement("counterparty_breakdown",
                           f"Spend across {len(view['counterparty_breakdown'])} counterparties; "
                           f"the largest holds {view['counterparty_breakdown'][0]['share']:.0%}.",
                           rule=rules["counterparty_concentration_anomaly"],
                           values={"breakdown": view["counterparty_breakdown"],
                                   "approved_counterparty_count": view["approved_counterparty_count"]}),
            fb.measurement("new_payee_share",
                           (f"In {npc['latest_month']}, {top['counterparty_name']} took "
                            f"{top['share_pct']}% of in-window spend"
                            + (f"; the register first saw it {top['registry_first_seen']}, inside the "
                               f"review window." if top["new_in_window"] else ".")) if top
                           else "No in-window transactions to profile by month.",
                           rule=rules["counterparty_concentration_anomaly"],
                           values={**npc, "new_payee_min_share_pct": view["new_payee_min_share_pct"]}),
            fb.measurement("velocity",
                           f"Inter-transaction gaps: min {view['velocity_stats']['min_gap_hours']}h, "
                           f"median {view['velocity_stats']['median_gap_hours']}h, "
                           f"{view['velocity_stats']['gaps_under_1_hour']} under an hour.",
                           rule=rules["transaction_velocity_anomaly"],
                           values=view["velocity_stats"]),
            fb.measurement("amount_stats", f"{n} transactions totalling {view['amount_stats']['total']}.",
                           values=view["amount_stats"]),
            fb.measurement("hourly_distribution", "Transactions by hour of day.",
                           values=view["hourly_distribution"]),
        ]

    def assess(self, facts: list[Fact], ruleset: Ruleset | None,
               dossier: LoadedDossier, *, round: int = 1) -> list[Assessment]:
        # Every Log rule is judged; the floor has no verdicts to price. Data
        # gaps are the one mechanical assessment.
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
        rules = _rules(ruleset)
        if len(rules) < 3:
            return SpecialistReview(facts=[], assessments=[])
        facts = self.run(dossier, ruleset, evidence=evidence)
        assessments = self.assess(facts, ruleset, dossier, round=round)
        if not dossier.transaction_history:
            return SpecialistReview(facts=facts, assessments=assessments)

        judged, observations = await analyze_log(
            dossier, facts,
            rules["transaction_structuring_detected"],
            rules["counterparty_concentration_anomaly"],
            rules["transaction_velocity_anomaly"],
            model=model,
            prior_observations=prior_observations,
            reviewer_directive=reviewer_directive,
            system_prompt=effective_text(prompts, "SPECIALIST-LOG") if prompts else None,
            context=context, round=round,
        )
        return SpecialistReview(facts=facts, assessments=assessments + judged,
                                observations=observations)
