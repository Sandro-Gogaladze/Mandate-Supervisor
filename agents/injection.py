"""Injection (B2) — manipulated by what it read, and through which channel?

Floor: `agents/injection_checks.py`, regex triage over the four channels plus
the tool-schema hash, and a measurement per flagged run. Review: floor
assessments, then the judgement of whether the agent acted
(agents/injection_reasoning.py) — skipped, with a `clear` on record, when no
channel was flagged anywhere.
"""
from __future__ import annotations

from schemas import Assessment, EvidencePack, Fact, Observation, Ruleset
from schemas.dossier import LoadedDossier

from .base import SpecialistReview, floor
from .injection_checks import run_injection_checks
from .injection_reasoning import analyze_injection
from .prompts import effective_text


class InjectionAgent:
    name = "injection"

    def run(self, dossier: LoadedDossier, ruleset: Ruleset | None, *,
            evidence: EvidencePack | None = None) -> list[Fact]:
        return run_injection_checks(dossier, ruleset) if ruleset else []

    def assess(self, facts: list[Fact], ruleset: Ruleset | None, dossier: LoadedDossier, *,
               round: int = 1) -> list[Assessment]:
        return floor(facts, ruleset, dossier, agent=self.name, round=round) if ruleset else []

    async def review(self, dossier: LoadedDossier, ruleset: Ruleset | None, *,
                     evidence: EvidencePack | None = None, model=None,
                     prior_observations: list[Observation] | None = None,
                     reviewer_directive: str | None = None, prompts: dict | None = None,
                     context: dict | None = None, round: int = 1) -> SpecialistReview:
        if ruleset is None:
            return SpecialistReview(facts=[], assessments=[])
        facts = self.run(dossier, ruleset, evidence=evidence)
        assessments = self.assess(facts, ruleset, dossier, round=round)
        rule = next((r for r in ruleset.rules
                     if r.type == "agent_acted_on_injected_content" and r.status == "active"), None)
        observations: list[Observation] = []
        if rule is not None:
            judged, observations = await analyze_injection(
                dossier, facts, rule, model=model, prior_observations=prior_observations,
                reviewer_directive=reviewer_directive,
                system_prompt=effective_text(prompts, "SPECIALIST-INJECTION") if prompts else None,
                context=context, round=round)
            assessments = assessments + judged
        return SpecialistReview(facts=facts, assessments=assessments, observations=observations)
