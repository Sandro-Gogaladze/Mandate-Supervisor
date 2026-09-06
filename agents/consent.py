"""Consent & Harm (C2) — was the human there; is the consumer worse off?

Floor: `agents/consent_checks.py`, nine computable rules over the consent
ceremony against the signed chain, plus the selection measurement behind the
one judged rule. Review: floor assessments, then the value-for-money
judgement (agents/consent_reasoning.py) when `CNS-VFM-01` is active and any
run recorded a selection.
"""
from __future__ import annotations

from schemas import Assessment, EvidencePack, Fact, Observation, Ruleset
from schemas.dossier import LoadedDossier

from .base import SpecialistReview, floor, narrated
from .consent_checks import run_consent_checks
from .consent_reasoning import analyze_consent
from .prompts import effective_text


class ConsentAgent:
    name = "consent"

    def run(self, dossier: LoadedDossier, ruleset: Ruleset | None, *,
            evidence: EvidencePack | None = None) -> list[Fact]:
        return run_consent_checks(dossier, ruleset) if ruleset else []

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
        rule = next((r for r in ruleset.rules
                     if r.type == "value_for_money_against_alternatives" and r.status == "active"), None)
        observations: list[Observation] = []
        if rule is not None and any(f.kind == "measurement" and f.rule_id == rule.rule_id for f in facts):
            judged, observations = await analyze_consent(
                dossier, facts, rule, model=model, prior_observations=prior_observations,
                reviewer_directive=reviewer_directive,
                system_prompt=effective_text(prompts, "SPECIALIST-CONSENT") if prompts else None,
                context=context, round=round)
            assessments = assessments + judged
        return await narrated(SpecialistReview(facts=facts, assessments=assessments, observations=observations), self.name, dossier,
                              model=model, prompts=prompts, narrate=narrate)
