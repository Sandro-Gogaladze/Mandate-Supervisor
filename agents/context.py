"""Context composition — how a specialist's evidence is assembled, and the
code that makes three invariants mechanical:

- the evidence floor: the canonical base is always fully present —
  compose_context() starts from it and can only add;
- no summarization: extra blocks are inserted whole, exactly as the
  resolver fetched them — the orchestrator *names* blocks, it never authors
  their content;
- every dispatch records exactly what was sent: the composed dict is what
  gets recorded (dispatch_recorded.context_blocks) AND what the reasoning
  function serializes into its human message, byte for byte.

The canonical base for each skill is the dossier-level view its reasoning
module would build for itself: KYA's credential and what the floor found,
Mandate's per-rule outcomes across the runs, Log's and Drift's statistics
over the whole transaction history. Fifty runs' worth of facts, not fifty
JSON files (HANDOFF §5.1).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from data.canonical import payload_hash
from schemas import EvidencePack, Fact, Ruleset
from schemas.dossier import LoadedDossier

from . import drift_reasoning, kya_reasoning, log_reasoning, mandate_reasoning
from .evidence_bundle import with_evidence_contract


class ContextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_id: str
    content: Any


class ContextCompositionError(ValueError):
    pass


def canonical_context(
    skill_id: str,
    dossier: LoadedDossier,
    *,
    evidence: EvidencePack | None = None,
    ruleset: Ruleset | None = None,
    floor_facts: list[Fact] | None = None,
    peer_facts: list[Fact] | None = None,
    peer_assessments: list | None = None,
    portfolio: list[LoadedDossier] | None = None,
) -> dict:
    """The evidence floor for one skill — the same structured view the
    reasoning module would build for itself, produced here so the dispatcher
    can compose, record, and hand over one identical object."""
    if skill_id == "mandate.review":
        return with_evidence_contract(
            mandate_reasoning.structured_view(dossier, floor_facts or []),
            specialist="mandate", skill_id=skill_id, dossier=dossier,
            facts=floor_facts or [], ruleset=ruleset,
        )
    if skill_id == "kya.review":
        return kya_reasoning.structured_view(dossier, floor_facts or [], ruleset)
    from . import consent_reasoning, counterparty_reasoning, injection_reasoning, provenance_reasoning
    builders = {"consent.review": consent_reasoning, "counterparty.review": counterparty_reasoning,
                "injection.review": injection_reasoning, "provenance.review": provenance_reasoning}
    if skill_id in builders:
        specialist = skill_id.split(".", 1)[0]
        return with_evidence_contract(
            builders[skill_id].structured_view(dossier, floor_facts or []),
            specialist=specialist, skill_id=skill_id, dossier=dossier,
            facts=floor_facts or [], ruleset=ruleset,
        )
    if skill_id in ("control_assurance.review", "systemic.review"):
        # No model reads this briefing; it is recorded for the audit trail.
        # A summary by rule and kind, plus the breaches in full, says what
        # the pass established without copying hundreds of facts into the
        # dispatch event (Control Assurance's was 200 kB per dispatch).
        by_rule: dict[str, dict[str, int]] = {}
        for f in floor_facts or []:
            key = f.rule_id or f.fact_id.split("#")[-1].split("@")[0]
            by_rule.setdefault(key, {})
            by_rule[key][f.kind] = by_rule[key].get(f.kind, 0) + 1
        domain_evidence: dict[str, Any] = {
            "dossier_id": dossier.dossier.dossier_id,
            "facts": len(floor_facts or []),
            "rule_outcomes": by_rule,
            "breaches": [{"fact_id": f.fact_id, "rule_id": f.rule_id, "run_ref": f.run_ref,
                          "statement": f.statement} for f in floor_facts or [] if f.kind == "breach"],
            "absent": [{"fact_id": f.fact_id, "rule_id": f.rule_id, "run_ref": f.run_ref,
                        "reason": f.absent_reason, "missing": f.missing}
                       for f in floor_facts or [] if f.kind == "absent"],
        }
        if skill_id == "control_assurance.review":
            domain_evidence.update({
                "declared_controls": dossier.dossier.controls.model_dump(mode="json"),
                "control_executions": [{
                    "run_ref": run.run_id,
                    "outcome": run.outcome,
                    "controls_evaluated": [c.model_dump(mode="json") for c in run.controls_evaluated],
                } for run in dossier.runs],
                "peer_breach_facts": [f.model_dump(mode="json") for f in (peer_facts or [])
                                      if f.kind == "breach"],
                "peer_breach_assessments": [a.model_dump(mode="json") for a in (peer_assessments or [])
                                             if a.verdict == "breach"],
            })
        elif skill_id == "systemic.review":
            domain_evidence["portfolio"] = [{
                "case_id": item.dossier.dossier_id,
                "agent_id": item.dossier.agent_id,
                "operator_id": item.dossier.operator_id,
                "declared_models": sorted({r.intent_mandate.agent.model_version for r in item.runs}),
                "counterparties": sorted({t.counterparty_id for t in item.transaction_history}),
                "transactions": len(item.transaction_history),
            } for item in (portfolio or [dossier])]
        specialist = skill_id.split(".", 1)[0]
        return with_evidence_contract(
            domain_evidence, specialist=specialist, skill_id=skill_id,
            dossier=dossier, facts=floor_facts or [], ruleset=ruleset,
        )
    if skill_id == "log.analyze":
        rule = _active_rule(ruleset, "transaction_structuring_detected", skill_id)
        concentration = next((r for r in ruleset.rules
                              if r.type == "counterparty_concentration_anomaly" and r.status == "active"), None)
        return with_evidence_contract(
            log_reasoning.structured_view(dossier, rule, concentration),
            specialist="log", skill_id=skill_id, dossier=dossier,
            facts=floor_facts or [], ruleset=ruleset,
        )
    if skill_id == "drift.analyze":
        rule = _active_rule(ruleset, "behavioral_drift_detected", skill_id)
        return with_evidence_contract(
            drift_reasoning.structured_view(dossier, rule),
            specialist="drift", skill_id=skill_id, dossier=dossier,
            facts=floor_facts or [], ruleset=ruleset,
        )
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


def resolve_blocks(record, block_ids: list[str]) -> list[ContextBlock]:
    """Orchestrator-named record items → verbatim blocks. The orchestrator
    NAMES blocks; this resolver fetches their content untouched — the model
    never authors or summarizes what goes into a briefing. An id that
    doesn't resolve is logged and skipped, not improvised."""
    import logging

    logger = logging.getLogger(__name__)
    blocks: list[ContextBlock] = []
    for block_id in block_ids:
        content = None
        if block_id == "score" and record.risk_score is not None:
            content = record.risk_score.model_dump()
        elif block_id == "correlations" and record.correlations:
            content = [c.model_dump() for c in record.correlations]
        elif block_id.startswith("finding:"):
            fid = block_id.split(":", 1)[1]
            match = next((f for f in record.findings if f.finding_id == fid), None)
            content = match.model_dump() if match else None
        elif block_id.startswith("assessment:"):
            aid = block_id.split(":", 1)[1]
            match = next((a for a in record.assessments if a.assessment_id == aid), None)
            content = match.model_dump() if match else None
        elif block_id.startswith("answer:"):
            qid = block_id.split(":", 1)[1]
            match = next((a for a in record.answers if a.question_id == qid), None)
            if match is not None:
                content = {"question": match.question, "answer": match.answer,
                           "cited_evidence": match.cited_evidence}
        elif block_id.startswith("observation:"):
            try:
                idx = int(block_id.split(":", 1)[1])
                content = record.observations[idx].model_dump()
            except (ValueError, IndexError):
                content = None
        if content is None:
            logger.warning("Context block %r did not resolve on case %s — skipped", block_id, record.case_id)
            continue
        blocks.append(ContextBlock(block_id=block_id, content=content))
    return blocks


def context_digest(context: dict) -> str:
    """sha256 over the canonical bytes — same serialization that signs the
    corpus and chains the ledger, so two runs' contexts compare as equal
    exactly when their bytes are."""
    return payload_hash(context, exclude_keys=())
