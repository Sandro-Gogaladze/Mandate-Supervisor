"""KYA agent (PLAN item 5).

Two layers, kept structurally separate on purpose:

- `run()` — the deterministic floor. All 18 active KYA rules, unconditionally.
  This is the Protocol-conformant method (agents/base.py) the orchestrator
  (pipeline/graph.py) calls; no LLM involved, fully reproducible, testable
  without any API key. 6 rule types via ingestion/verify.py (credential
  signature/hash/alg, delegation-entry signatures, issuer trust/revocation
  — Phase 3), 12 via agents/kya_checks.py (issuer trust-level/staleness,
  credential lifecycle, delegation-chain shape, capabilities, consent).
- `review()` — floor + the agentic ceiling (free-text reasoning over
  anything the fixed rules can't catch) + grounded narration. Needs a live
  ANTHROPIC_API_KEY unless reasoning/narration are disabled or a fake
  client is injected. Returns a `KYAReview`, not a bare `list[Finding]` —
  `findings` and `observations` are never merged, see agents/kya_reasoning.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ingestion.normalize import IngestedCase
from ingestion.verify import verify_credential_with_ruleset
from schemas import Finding, Ruleset

from .kya_checks import run_policy_checks
from .prompts import effective_text
from .kya_reasoning import Observation, narrate_findings, reason_about_case


@dataclass
class KYAReview:
    findings: list[Finding]
    observations: list[Observation] = field(default_factory=list)
    narration: str | None = None


class KYAAgent:
    name = "kya"

    def run(self, case: IngestedCase, ruleset: Ruleset | None) -> list[Finding]:
        if ruleset is None:
            return []
        crypto_findings = verify_credential_with_ruleset(case.raw, ruleset)
        policy_findings = run_policy_checks(case.case, ruleset)
        return crypto_findings + policy_findings

    async def review(
        self,
        case: IngestedCase,
        ruleset: Ruleset | None,
        *,
        model=None,
        reason: bool = True,
        narrate: bool = True,
        prior_observations: list[Observation] | None = None,
        reviewer_directive: str | None = None,
        prompts: dict[str, dict] | None = None,
        context: dict | None = None,
    ) -> KYAReview:
        findings = self.run(case, ruleset)
        # `prompts` is the run's assembled prompt set (agents/prompts.py) —
        # the same text recorded on run_started; `context` is the composed
        # evidence recorded on dispatch_recorded (agents/context.py).
        reasoning_prompt = effective_text(prompts, "SPECIALIST-KYA") if prompts else None
        narration_prompt = effective_text(prompts, "KYA-NARRATION") if prompts else None
        observations = (
            await reason_about_case(
                case, findings, model=model, prior_observations=prior_observations,
                reviewer_directive=reviewer_directive, system_prompt=reasoning_prompt,
                context=context,
            )
            if reason else []
        )
        narration = (
            await narrate_findings(case.case.case_id, findings, model=model, system_prompt=narration_prompt)
            if narrate else None
        )
        return KYAReview(findings=findings, observations=observations, narration=narration)
