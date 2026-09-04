"""Provenance (B1) — was this mandate built from inputs anyone should trust?

Floor: `agents/provenance_checks.py` over `provenance.json`. Review: floor
assessments, then the four-source reconciliation (agents/provenance_reasoning.py).
"""
from __future__ import annotations

from schemas import Assessment, EvidencePack, Fact, Observation, Ruleset
from schemas.dossier import LoadedDossier

from .base import SpecialistReview, floor
from .prompts import effective_text
from .provenance_checks import run_provenance_checks
from .provenance_reasoning import analyze_provenance


class ProvenanceAgent:
    name = "provenance"

    def run(self, dossier: LoadedDossier, ruleset: Ruleset | None, *,
            evidence: EvidencePack | None = None) -> list[Fact]:
        return run_provenance_checks(dossier, ruleset) if ruleset else []

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
        rule = next((r for r in ruleset.rules if r.type == "four_sources_reconcile" and r.status == "active"), None)
        observations: list[Observation] = []
        if rule is not None:
            judged, observations = await analyze_provenance(
                dossier, facts, rule, model=model, prior_observations=prior_observations,
                reviewer_directive=reviewer_directive,
                system_prompt=effective_text(prompts, "SPECIALIST-PROVENANCE") if prompts else None,
                context=context, round=round)
            assessments = assessments + judged
        return SpecialistReview(facts=facts, assessments=assessments, observations=observations)
