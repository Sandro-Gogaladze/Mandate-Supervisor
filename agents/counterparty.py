"""Counterparty (C1) — who received this money?

Floor: `agents/counterparty_checks.py`, eight computable rules over the
payee, the merchant and the register, plus the profile and decline-timeline
measurements behind the two judged rules. Review: floor assessments, then
the payee-identity and declines judgements (agents/counterparty_reasoning.py).
"""
from __future__ import annotations

from schemas import Assessment, EvidencePack, Fact, Observation, Ruleset
from schemas.dossier import LoadedDossier

from .base import SpecialistReview, floor, narrated
from .counterparty_checks import run_counterparty_checks
from .counterparty_reasoning import analyze_counterparty
from .prompts import effective_text


class CounterpartyAgent:
    name = "counterparty"

    def run(self, dossier: LoadedDossier, ruleset: Ruleset | None, *,
            evidence: EvidencePack | None = None) -> list[Fact]:
        return run_counterparty_checks(dossier, ruleset) if ruleset else []

    def assess(self, facts: list[Fact], ruleset: Ruleset | None, dossier: LoadedDossier, *,
               round: int = 1) -> list[Assessment]:
        return floor(facts, ruleset, dossier, agent=self.name, round=round) if ruleset else []

    async def review(self, dossier: LoadedDossier, ruleset: Ruleset | None, *,
                     evidence: EvidencePack | None = None, model=None,
                     prior_observations: list[Observation] | None = None,
                     reviewer_directive: str | None = None, prompts: dict | None = None,
                     context: dict | None = None, round: int = 1,
                     narrate: bool = True) -> SpecialistReview:
        if ruleset is None:
            return SpecialistReview(facts=[], assessments=[])
        facts = self.run(dossier, ruleset, evidence=evidence)
        assessments = self.assess(facts, ruleset, dossier, round=round)
        by_type = {r.type: r for r in ruleset.rules if r.status == "active"}
        identity, declines = by_type.get("payee_is_what_it_appears"), by_type.get("declines_not_clustered")
        observations: list[Observation] = []
        if identity is not None and declines is not None:
            judged, observations = await analyze_counterparty(
                dossier, facts, identity, declines, model=model, prior_observations=prior_observations,
                reviewer_directive=reviewer_directive,
                system_prompt=effective_text(prompts, "SPECIALIST-COUNTERPARTY") if prompts else None,
                context=context, round=round)
            assessments = assessments + judged
        return await narrated(SpecialistReview(facts=facts, assessments=assessments, observations=observations), self.name, dossier,
                              model=model, prompts=prompts, narrate=narrate)
