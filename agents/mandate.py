"""Mandate agent (A1) — within what the human signed?

- `run()` — the full deterministic floor: the two chain-link rules
  (ingestion/verify.py, against the raw submission) plus the scope/cap/
  consistency rules (agents/mandate_checks.py), one fact per rule per run.
  No model, no key.
- `review()` — the floor as assessments, plus the one contained model
  call: per-line-item intent fidelity against the shopper's own sentence,
  one call over every run that reached a cart, a verdict per run, plus the
  open channel (agents/mandate_reasoning.py) — one tool call carries both.
  Only runs when `MND-SEM-01` is active in the ruleset it is handed — a
  draft rule never fires, model or not.
"""
from __future__ import annotations

from ingestion.verify import RawSubmissionMissing, chain_facts_with_ruleset
from schemas import Assessment, EvidencePack, Fact, Ruleset
from schemas.dossier import LoadedDossier

from .base import SpecialistReview, floor, narrated
from .mandate_checks import run_policy_checks
from .mandate_reasoning import check_intent_fidelity
from .prompts import effective_text


class MandateAgent:
    name = "mandate"

    def run(self, dossier: LoadedDossier, ruleset: Ruleset | None, *,
            evidence: EvidencePack | None = None) -> list[Fact]:
        if ruleset is None:
            return []
        try:
            chain = chain_facts_with_ruleset(dossier, ruleset)
        except RawSubmissionMissing:
            chain = [f for f in (evidence.ingestion_facts if evidence else []) if f.domain == "mandate"]
        return chain + run_policy_checks(dossier, ruleset)

    def assess(self, facts: list[Fact], ruleset: Ruleset | None,
               dossier: LoadedDossier, *, round: int = 1) -> list[Assessment]:
        return floor(facts, ruleset, dossier, agent=self.name, round=round) if ruleset else []

    async def review(
        self,
        dossier: LoadedDossier,
        ruleset: Ruleset | None,
        *,
        evidence: EvidencePack | None = None,
        model=None,
        semantic_check: bool = True,
        reviewer_directive: str | None = None,
        prompts: dict[str, dict] | None = None,
        context: dict | None = None,
        round: int = 1,
        narrate: bool = True,
    ) -> SpecialistReview:
        facts = self.run(dossier, ruleset, evidence=evidence)
        assessments = self.assess(facts, ruleset, dossier, round=round)
        rule = next((r for r in (ruleset.rules if ruleset else [])
                     if r.type == "cart_reasoning_matches_intent" and r.status == "active"), None)
        observations = []
        if semantic_check and rule is not None:
            judged, observations = await check_intent_fidelity(
                dossier, facts, rule, model=model, reviewer_directive=reviewer_directive,
                system_prompt=effective_text(prompts, "SPECIALIST-MANDATE") if prompts else None,
                context=context, round=round,
            )
            assessments = assessments + judged
        return await narrated(SpecialistReview(facts=facts, assessments=assessments, observations=observations), self.name, dossier,
                              model=model, prompts=prompts, narrate=narrate)
