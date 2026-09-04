"""Provenance's one contained model call — do the four sources reconcile?

The agent card (the operator's own description), the credential (the
issuer's), the register (the regulator's) and the observed tool calls (what
actually happened) should describe one agent. The computable rules catch
each pairwise disagreement they were written for; the model reads the four
side by side and says whether the whole picture holds together, and which
source is the odd one out when it does not.
"""
from __future__ import annotations



from schemas import Assessment, Fact, Observation, Rule
from schemas.dossier import LoadedDossier

from .llm import (
    briefing_message, format_escalation_addendum, format_reviewer_addendum, get_model,
    get_tool_call, log_cache_usage, parse_observations, system_message, THINKING_EFFORT,
    with_reasoning,
)
from .prompts import assemble

PROMPT_ID = "SPECIALIST-PROVENANCE"
SYSTEM_PROMPT = assemble(PROMPT_ID).effective

_TOOL = with_reasoning({
    "name": "record_provenance_reconciliation",
    "description": "Record whether the agent card, credential, register and observed calls describe one agent.",
    "input_schema": {
        "type": "object",
        "properties": {
            "reconciled": {"type": "boolean"},
            "disagreements": {
                "type": "array",
                "items": {"type": "object",
                          "properties": {"sources": {"type": "array", "items": {"type": "string"}},
                                         "explanation": {"type": "string", "description": "One sentence."}, "cited_evidence": {"type": "string", "description": "The exact field or value it rests on. A reference, not prose."}},
                          "required": ["sources", "explanation", "cited_evidence"]},
            },
            "explanation": {"type": "string", "description": "One sentence."},
            "other_observations": {
                "type": "array",
                "items": {"type": "object",
                          "properties": {"note": {"type": "string", "description": "One sentence: the specific thing you noticed."}, "cited_evidence": {"type": "string", "description": "The exact field or value it rests on. A reference, not prose."}},
                          "required": ["note", "cited_evidence"]},
            },
        },
        "required": ["reconciled", "disagreements", "explanation", "other_observations"],
    },
})


def structured_view(dossier: LoadedDossier, facts: list[Fact]) -> dict:
    by_rule: dict[str, dict[str, int]] = {}
    for f in facts:
        if f.rule_id and f.kind != "measurement":
            by_rule.setdefault(f.rule_id, {})
            by_rule[f.rule_id][f.kind] = by_rule[f.rule_id].get(f.kind, 0) + 1
    sources = next((f.values for f in facts if f.kind == "measurement" and f.rule_id == "PRV-REC-01"), {})
    return {
        "dossier_id": dossier.dossier.dossier_id,
        "sources": sources,
        "provenance_evidence_by_run": [{
            "run_id": run.run_id,
            "model": run.construction_context.model.model_dump(mode="json"),
            "policy_version": run.construction_context.policy_version.model_dump(mode="json"),
            "tool_calls": [{
                "sequence": call.sequence, "tool_name": call.tool_name,
                "server_id": call.server_id, "tool_schema_hash": call.tool_schema_hash,
                "result_digest": call.result_digest,
            } for call in run.construction_context.tool_calls],
        } for run in dossier.runs],
        "rule_outcomes": by_rule,
        "floor_breaches": [{"rule_id": f.rule_id, "run_id": f.run_ref, "statement": f.statement}
                           for f in facts if f.kind == "breach"],
    }


async def analyze_provenance(
    dossier: LoadedDossier, facts: list[Fact], rule: Rule, *, model=None,
    thinking_effort: str = THINKING_EFFORT, prior_observations: list[Observation] | None = None,
    reviewer_directive: str | None = None, system_prompt: str | None = None,
    context: dict | None = None, round: int = 1,
) -> tuple[list[Assessment], list[Observation]]:
    case_id = dossier.dossier.dossier_id
    measurement = next((f for f in facts if f.kind == "measurement" and f.rule_id == rule.rule_id), None)
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
    log_cache_usage(response, "provenance")
    result = get_tool_call(response, "record_provenance_reconciliation")
    disagreements = [d for d in result.get("disagreements", []) if isinstance(d, dict)]
    assessment = Assessment(
        assessment_id=f"{case_id}:provenance:{rule.rule_id}:r{round}", case_id=case_id, round=round,
        scope="case", agent="provenance", rule_id=rule.rule_id,
        fact_ids=[measurement.fact_id] if measurement else [],
        verdict="clear" if result.get("reconciled") and not disagreements else "breach", confidence="probable",
        severity_floor=rule.severity_weight, severity_assessed=rule.severity_weight,
        subject=", ".join(sorted({s for d in disagreements for s in d.get("sources", [])})) or None,
        narrative=result.get("explanation", "") + ("".join(f" [{'/'.join(d.get('sources', []))}: {d.get('explanation', '')}]"
                                                          for d in disagreements)),
    )
    observations = parse_observations(result.get("other_observations", []), case_id=case_id, agent="provenance")
    return [assessment], observations
