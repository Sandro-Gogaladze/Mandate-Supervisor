"""Context composition (architecture-v2 §13.3) — how a subagent's evidence
is assembled, and the code that makes three invariants mechanical:

- §9.2 the evidence floor: the canonical base is always fully present —
  compose_context() starts from it and can only add;
- §9.3 no summarization: extra blocks are inserted whole, exactly as the
  resolver fetched them — the orchestrator *names* blocks, it never authors
  their content;
- §9.4 every dispatch records exactly what was sent: the composed dict is
  what gets recorded (dispatch_recorded.context_blocks) AND what the
  reasoning function serializes into its human message, byte for byte.

Why the floor matters even though verdicts are already non-deterministic:
case-005's structuring pattern is only visible across all 16 transactions
relative to the account's own spread. A subagent handed three rows still
answers — worse, with nothing downstream knowing why. Verdict variance is
inherent; evidence integrity is a different thing, and it is also what makes
run-vs-run comparison meaningful (same evidence, different judgment — not
two different questions).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from data.canonical import payload_hash
from ingestion.normalize import IngestedCase
from schemas import Finding, Ruleset

from . import drift_reasoning, kya_reasoning, log_reasoning, mandate_reasoning


class ContextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_id: str
    content: Any


class ContextCompositionError(ValueError):
    pass


def canonical_context(
    skill_id: str,
    case: IngestedCase,
    *,
    ruleset: Ruleset | None = None,
    floor_findings: list[Finding] | None = None,
) -> dict:
    """The evidence floor for one skill — the same structured view the
    reasoning module would build for itself, produced here so the dispatcher
    can compose, record, and hand over one identical object."""
    if skill_id == "mandate.review":
        return mandate_reasoning.structured_view(case)
    if skill_id == "kya.review":
        return kya_reasoning.structured_view(case, floor_findings or [])
    if skill_id == "log.analyze":
        rule = _active_rule(ruleset, "transaction_structuring_detected", skill_id)
        return log_reasoning.structured_view(case, rule)
    if skill_id == "drift.analyze":
        rule = _active_rule(ruleset, "behavioral_drift_detected", skill_id)
        return drift_reasoning.structured_view(case, rule)
    raise ContextCompositionError(f"no canonical context builder for skill {skill_id!r}")


def _active_rule(ruleset: Ruleset | None, rule_type: str, skill_id: str):
    if ruleset is None:
        raise ContextCompositionError(f"{skill_id} needs its ruleset to build canonical context")
    rule = next((r for r in ruleset.rules if r.type == rule_type and r.status == "active"), None)
    if rule is None:
        raise ContextCompositionError(f"{skill_id}: no active {rule_type!r} rule in {ruleset.ruleset_id}")
    return rule


def compose_context(base: dict, extra_blocks: list[ContextBlock] | None = None) -> dict:
    """base + verbatim extras. Never removes, never rewrites: the composed
    dict is a strict superset of the base, with orchestrator-named blocks
    under one clearly labeled key."""
    if "supplementary_context" in base:
        raise ContextCompositionError(
            "base context already carries supplementary_context — compose once, at dispatch"
        )
    composed = dict(base)
    if extra_blocks:
        composed["supplementary_context"] = [block.model_dump() for block in extra_blocks]
    return composed


def context_digest(context: dict) -> str:
    """sha256 over the canonical bytes — same serialization that signs the
    mandate corpus and chains the ledger, so two runs' contexts compare as
    equal exactly when their bytes are."""
    return payload_hash(context, exclude_keys=())
