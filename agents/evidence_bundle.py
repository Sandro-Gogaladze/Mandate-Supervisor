"""Attach the same auditable rule/fact envelope to every specialist view."""
from __future__ import annotations

from schemas import Fact, RuleResultIndex, Ruleset, SpecialistEvidenceContract
from schemas.dossier import LoadedDossier

_UNTRUSTED_VALUE_KEYS = frozenset({
    "natural_language_intent", "description", "agent_reasoning",
    "shopper_request", "query", "text", "result_excerpt",
})


def _delimit_untrusted_values(value, key: str | None = None):
    if isinstance(value, dict):
        return {k: _delimit_untrusted_values(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_delimit_untrusted_values(v, key) for v in value]
    if isinstance(value, str) and key in _UNTRUSTED_VALUE_KEYS:
        if value.startswith("<<<UNTRUSTED_"):
            return value
        return f"<<<UNTRUSTED_EVIDENCE_TEXT>>>{value}<<<END_UNTRUSTED_EVIDENCE_TEXT>>>"
    return value


def _fact_for_prompt(fact: Fact) -> dict:
    item = fact.model_dump(mode="json")
    # Statements are deterministic prose but may quote submitted text.
    item["statement"] = (
        f"<<<UNTRUSTED_FACT_STATEMENT>>>{item['statement']}"
        "<<<END_UNTRUSTED_FACT_STATEMENT>>>"
    )
    item["values"] = _delimit_untrusted_values(item["values"])
    for ref in item["refs"]:
        if any(token in ref["ref"] for token in (
            "natural_language_intent", "description", "user_prompt", "result_excerpt"
        )) and isinstance(ref.get("value"), str):
            ref["value"] = _delimit_untrusted_values(ref["value"], "text")
    return item


def with_evidence_contract(
    domain_evidence: dict,
    *,
    specialist: str,
    skill_id: str,
    dossier: LoadedDossier,
    facts: list[Fact],
    ruleset: Ruleset | None,
) -> dict:
    """Return the existing domain view plus a deterministic common contract.

    Domain fields stay at the root so existing prompts keep their semantics.
    The common envelope is nested once under ``evidence_contract``; this
    avoids duplicating large statistics or run projections in the prompt.
    """
    from registry.loader import load_failure_catalogue

    grouped: dict[str, list[Fact]] = {}
    for fact in facts:
        if fact.rule_id:
            grouped.setdefault(fact.rule_id, []).append(fact)
    results = []
    for rule_id, rule_facts in sorted(grouped.items()):
        counts: dict[str, int] = {}
        for fact in rule_facts:
            counts[fact.kind] = counts.get(fact.kind, 0) + 1
        results.append(RuleResultIndex(
            rule_id=rule_id,
            counts=counts,
            # Clean outcomes are represented by count + run refs. Their
            # deterministic ids add no information and can dominate prompt
            # size on large dossiers. Attention facts retain every id in full.
            fact_ids=[f.fact_id for f in rule_facts if f.kind != "satisfied"],
            run_refs=sorted({f.run_ref for f in rule_facts if f.run_ref}),
        ))
    contract = SpecialistEvidenceContract(
        case_id=dossier.dossier.dossier_id,
        specialist=specialist,
        skill_id=skill_id,
        review_scope={
            "kind": "whole_dossier" if len(dossier.runs) == len(dossier.dossier.run_index)
                    else "selected_runs",
            "run_refs": [r.run_id for r in dossier.runs],
        },
        ruleset=({"ruleset_id": ruleset.ruleset_id, "version": ruleset.version,
                  "as_of": ruleset.as_of} if ruleset else None),
        failure_catalogue_version=load_failure_catalogue().version,
        rule_inventory=[{
            "rule_id": r.rule_id,
            "description": r.description,
            "status": r.status,
            "evaluation": r.evaluation,
            "severity_weight": r.severity_weight,
            "failure_ids": list(r.failures),
        } for r in (ruleset.rules if ruleset else [])],
        rule_results=results,
        attention_facts=[_fact_for_prompt(f) for f in facts if f.kind != "satisfied"],
    )
    if "evidence_contract" in domain_evidence:
        raise ValueError("domain evidence cannot replace the mandatory evidence_contract")
    return {**domain_evidence, "evidence_contract": contract.model_dump(mode="json")}
