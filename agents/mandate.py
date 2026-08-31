"""Mandate agent (PLAN item 6).

- `run()` — the full deterministic floor. 2 rule types via ingestion/verify.py
  (chain-link hash integrity — Phase 3), 10 via agents/mandate_checks.py
  (scope/cap/counterparty/currency/validity-window/cumulative-monthly-cap,
  plus the deterministic injection heuristic). No LLM, no API key needed —
  this is what the orchestrator (pipeline/graph.py) calls.
- `review()` — run() plus the one contained LLM call CLAUDE.md specifies
  (agents/mandate_reasoning.py's prompt-playback semantic subcheck).
  Unlike agents/kya.py's review(), the LLM result here is merged straight
  into the same findings list, not kept as a separate unverified type —
  see agents/mandate_reasoning.py's module docstring for why that's the
  right call here and not a KYA-vs-Mandate inconsistency. Only runs the
  semantic subcheck if its rule (MND-SEM-01) is actually active in the
  ruleset passed in — draft rules never fire, LLM or not.
"""
from __future__ import annotations

from ingestion.normalize import IngestedCase
from ingestion.verify import verify_chain_links_with_ruleset
from schemas import Finding, Ruleset

from .mandate_checks import run_policy_checks
from .mandate_reasoning import check_cart_reasoning_matches_intent


class MandateAgent:
    name = "mandate"

    def run(self, case: IngestedCase, ruleset: Ruleset | None) -> list[Finding]:
        if ruleset is None:
            return []
        chain_findings = verify_chain_links_with_ruleset(case.raw, ruleset)
        policy_findings = run_policy_checks(case.case, ruleset)
        return chain_findings + policy_findings

    async def review(
        self,
        case: IngestedCase,
        ruleset: Ruleset | None,
        *,
        model=None,
        semantic_check: bool = True,
        reviewer_directive: str | None = None,
    ) -> list[Finding]:
        findings = self.run(case, ruleset)
        if not semantic_check or ruleset is None:
            return findings

        rule = next(
            (r for r in ruleset.rules if r.type == "cart_reasoning_matches_intent" and r.status == "active"),
            None,
        )
        if rule is None:
            return findings

        semantic_finding = await check_cart_reasoning_matches_intent(case, rule, model=model, reviewer_directive=reviewer_directive)
        if semantic_finding is not None:
            findings = findings + [semantic_finding]
        return findings
