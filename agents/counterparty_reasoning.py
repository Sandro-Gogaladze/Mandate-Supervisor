"""Counterparty's one contained model call — is this payee what it appears
to be, and are the declines telling a story?

The floor records one profile per payee (registered name against account
name, ownership, first seen, geography, share, flags) and the decline and
reversal timeline per counterparty. The model judges the two things no rule
can: whether a payee is a front (CPT-IDN-01) and whether failures cluster
into probing (CPT-DCL-01). Every merchant id it names is validated against
the profiles it was shown.
"""
from __future__ import annotations

import logging


from schemas import Assessment, EvidenceRef, Fact, Observation, Rule
from schemas.dossier import LoadedDossier

from .llm import (
    briefing_message, format_escalation_addendum, format_reviewer_addendum, get_model,
    get_tool_call, log_cache_usage, parse_observations, system_message, THINKING_EFFORT,
    with_reasoning,
)
from .prompts import assemble

logger = logging.getLogger(__name__)

PROMPT_ID = "SPECIALIST-COUNTERPARTY"
SYSTEM_PROMPT = assemble(PROMPT_ID).effective

_VERDICT = {
    "type": "object",
    "properties": {"anomalous": {"type": "boolean"}, "explanation": {"type": "string", "description": "One sentence."},
                   "cited_evidence": {"type": "string", "description": "The exact field or value it rests on. A reference, not prose."}},
    "required": ["anomalous", "explanation", "cited_evidence"],
}

_TOOL = with_reasoning({
    "name": "record_counterparty_analysis",
    "description": "Record which payees look doubtful, the declines judgement, and other observations.",
    "input_schema": {
        "type": "object",
        "properties": {
            "doubtful_payees": {
                "type": "array",
                "items": {"type": "object",
                          "properties": {"merchant_id": {"type": "string"}, "explanation": {"type": "string", "description": "One sentence."},
                                         "cited_evidence": {"type": "string", "description": "The exact field or value it rests on. A reference, not prose."}},
                          "required": ["merchant_id", "explanation", "cited_evidence"]},
            },
            "identity_explanation": {"type": "string", "description": "One sentence on the payee set as a whole."},
            "declines": _VERDICT,
            "other_observations": {
                "type": "array",
                "items": {"type": "object",
                          "properties": {"note": {"type": "string", "description": "One sentence: the specific thing you noticed."}, "cited_evidence": {"type": "string", "description": "The exact field or value it rests on. A reference, not prose."}},
                          "required": ["note", "cited_evidence"]},
            },
        },
        "required": ["doubtful_payees", "identity_explanation", "declines", "other_observations"],
    },
})


def structured_view(dossier: LoadedDossier, facts: list[Fact]) -> dict:
    by_rule: dict[str, dict[str, int]] = {}
    for f in facts:
        if f.rule_id and f.kind != "measurement":
            by_rule.setdefault(f.rule_id, {})
            by_rule[f.rule_id][f.kind] = by_rule[f.rule_id].get(f.kind, 0) + 1
    profiles = next((f.values["payees"] for f in facts if f.kind == "measurement" and f.rule_id == "CPT-IDN-01"), [])
    declines = next((f.values for f in facts if f.kind == "measurement" and f.rule_id == "CPT-DCL-01"), {})
    return {
        "dossier_id": dossier.dossier.dossier_id,
        "payees": profiles,
        "decline_timeline": declines,
        "rule_outcomes": by_rule,
        "floor_breaches": [{"rule_id": f.rule_id, "run_id": f.run_ref, "statement": f.statement}
                           for f in facts if f.kind == "breach"],
    }


async def analyze_counterparty(
    dossier: LoadedDossier, facts: list[Fact], identity_rule: Rule, declines_rule: Rule, *, model=None,
    thinking_effort: str = THINKING_EFFORT, prior_observations: list[Observation] | None = None,
    reviewer_directive: str | None = None, system_prompt: str | None = None,
    context: dict | None = None, round: int = 1,
) -> tuple[list[Assessment], list[Observation]]:
    case_id = dossier.dossier.dossier_id
    profile_fact = next((f for f in facts if f.kind == "measurement" and f.rule_id == identity_rule.rule_id), None)
    decline_fact = next((f for f in facts if f.kind == "measurement" and f.rule_id == declines_rule.rule_id), None)
    if profile_fact is None:
        return [], []
    profiles = {p["merchant_id"]: p for p in profile_fact.values["payees"]}

    model = model or get_model()
    bound = model.bind(output_config={"effort": thinking_effort}, tools=[_TOOL], tool_choice={"type": "auto"})
    system = system_prompt or SYSTEM_PROMPT
    if prior_observations:
        system += format_escalation_addendum(prior_observations)
    if reviewer_directive:
        system += format_reviewer_addendum(reviewer_directive)
    response = await bound.ainvoke([
        system_message(system),
        briefing_message(context if context is not None else structured_view(dossier, facts)),
    ])
    log_cache_usage(response, "counterparty")
    result = get_tool_call(response, "record_counterparty_analysis")

    out: list[Assessment] = []
    common = dict(case_id=case_id, round=round, agent="counterparty", confidence="probable")
    doubtful = []
    for d in result.get("doubtful_payees", []):
        if not isinstance(d, dict) or d.get("merchant_id") not in profiles:
            logger.warning("Counterparty: dropping doubtful payee not in the profiles shown on %s: %r", case_id, d)
            continue
        doubtful.append(d)
        p = profiles[d["merchant_id"]]
        out.append(Assessment(
            assessment_id=f"{case_id}:counterparty:{identity_rule.rule_id}:{d['merchant_id']}:r{round}",
            scope="run", run_refs=p["runs"], fact_ids=[profile_fact.fact_id], rule_id=identity_rule.rule_id,
            evidence_refs=[EvidenceRef(kind="registry", ref=f"merchants[{d['merchant_id']}]", value=p.get("legal_name"))],
            verdict="breach", subject=d["merchant_id"],
            severity_floor=identity_rule.severity_weight, severity_assessed=identity_rule.severity_weight,
            narrative=f"{p.get('legal_name') or d['merchant_id']}: {d.get('explanation', '')}", **common))
    if not doubtful:
        out.append(Assessment(
            assessment_id=f"{case_id}:counterparty:{identity_rule.rule_id}:r{round}", scope="case",
            fact_ids=[profile_fact.fact_id], rule_id=identity_rule.rule_id, verdict="clear",
            severity_floor=identity_rule.severity_weight, severity_assessed=identity_rule.severity_weight,
            narrative=result.get("identity_explanation", "No payee looks other than what it appears."), **common))
    dec = result.get("declines") or {}
    out.append(Assessment(
        assessment_id=f"{case_id}:counterparty:{declines_rule.rule_id}:r{round}", scope="case",
        fact_ids=[decline_fact.fact_id] if decline_fact else [], rule_id=declines_rule.rule_id,
        verdict="breach" if dec.get("anomalous") else "clear", subject=dec.get("cited_evidence") or None,
        severity_floor=declines_rule.severity_weight, severity_assessed=declines_rule.severity_weight,
        narrative=dec.get("explanation", ""), **common))
    observations = parse_observations(result.get("other_observations", []), case_id=case_id, agent="counterparty")
    return out, observations
