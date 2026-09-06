"""KYA agent (A2) — authority traceable to a human?

Two layers, kept structurally separate on purpose:

- `run()` — the deterministic floor: the six cryptographic rules
  (ingestion/verify.py, against the raw submission) plus the rest of the
  active KYA book (agents/kya_checks.py), as facts over the whole dossier.
  No model, no key, reproducible.
- `review()` — floor + the agentic ceiling (free-text reasoning over
  anything the fixed rules can't catch — a near-name issuer, a structural
  oddity) + grounded narration. Returns a `SpecialistReview`; observations
  and assessments are never merged.

Provenance owns three of the book's rules (TEC-02/05/06) and evaluates them
from `construction_context`; this agent skips them deliberately.
"""
from __future__ import annotations

from ingestion.verify import RawSubmissionMissing, credential_facts_with_ruleset
from schemas import Assessment, EvidencePack, Fact, FactBuilder, Ruleset
from schemas.dossier import LoadedDossier

from .base import SpecialistReview, floor, narrated
from .kya_checks import run_policy_checks
from .kya_reasoning import (
    Observation, activity_summary, capability_profile, reason_about_case,
)
from .prompts import effective_text

KYAReview = SpecialistReview


def _activity_measurement(fb: FactBuilder, rule, dossier: LoadedDossier) -> Fact:
    """KYA-REG-03's evidence: does observed activity fit the registered class?"""
    s = activity_summary(dossier)
    return fb.measurement(
        "activity_summary",
        f"{s['transactions']} transactions ({s['in_window']} in window) totalling "
        f"{s['settled_total']}, largest {s['largest_single']}, "
        f"{s['distinct_counterparties']} counterparties.",
        rule=rule, values=s)


def _capability_measurement(fb: FactBuilder, rule, dossier: LoadedDossier) -> Fact:
    """KYA-CAP-04's evidence: the grant against what the purpose needs."""
    p = capability_profile(dossier)
    unused = p["granted_but_not_on_card"]
    return fb.measurement(
        "capability_profile",
        f"The credential grants {p['granted_count']} capability(ies) to a "
        f"{p['registered_classification'] or 'unregistered'} agent"
        + (f"; {len(unused)} appear on no agent card: {', '.join(unused)}." if unused else "."),
        rule=rule, values=p)


class KYAAgent:
    name = "kya"

    def run(self, dossier: LoadedDossier, ruleset: Ruleset | None, *,
            evidence: EvidencePack | None = None) -> list[Fact]:
        if ruleset is None:
            return []
        try:
            crypto = credential_facts_with_ruleset(dossier, ruleset)
        except RawSubmissionMissing:
            # A dossier constructed without its raw submission cannot be
            # verified; intake's record is the next best thing.
            crypto = [f for f in (evidence.ingestion_facts if evidence else []) if f.domain == "kya"]
        facts = crypto + run_policy_checks(dossier, ruleset)
        # KYA's judged rules: the floor records what each judgement rests on,
        # ACTIVE OR DRAFT, so the evidence is on the record either way and a
        # rule promoted in the sandbox has its measurement waiting for it.
        fb = FactBuilder(dossier.dossier.dossier_id, self.name)
        for rule_type, build in (("agent_activity_matches_classification", _activity_measurement),
                                 ("capabilities_least_privilege", _capability_measurement)):
            rule = next((r for r in ruleset.rules if r.type == rule_type), None)
            if rule is not None:
                facts.append(build(fb, rule, dossier))
        return facts

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
        reason: bool = True,
        narrate: bool = True,
        prior_observations: list[Observation] | None = None,
        reviewer_directive: str | None = None,
        prompts: dict[str, dict] | None = None,
        context: dict | None = None,
        round: int = 1,
    ) -> SpecialistReview:
        facts = self.run(dossier, ruleset, evidence=evidence)
        assessments = self.assess(facts, ruleset, dossier, round=round)
        # `prompts` is the run's assembled prompt set (agents/prompts.py) —
        # the same text recorded on run_started; `context` is the composed
        # evidence recorded on dispatch_recorded (agents/context.py).
        reasoning_prompt = effective_text(prompts, "SPECIALIST-KYA") if prompts else None
        observations: list[Observation] = []
        if reason:
            observations, judged = await reason_about_case(
                dossier, facts, model=model, prior_observations=prior_observations,
                reviewer_directive=reviewer_directive, system_prompt=reasoning_prompt,
                context=context, ruleset=ruleset, round=round,
            )
            assessments = assessments + judged
        return await narrated(
            SpecialistReview(facts=facts, assessments=assessments, observations=observations),
            self.name, dossier, model=model, prompts=prompts, narrate=narrate)
