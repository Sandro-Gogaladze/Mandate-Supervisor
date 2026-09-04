"""The agentic ceiling: free-text reasoning over anything the fixed KYA
rules can't catch, plus narration of the assessments that did fire.

Both run with adaptive thinking at high effort and are still
schema-constrained via a tool — output is always structured, never
free-form prose to parse with regex. `tool_choice` stays `{"type": "auto"}`
rather than forced — Anthropic's thinking modes require it — so the system
prompts compensate by instructing the model explicitly, and
agents/llm.py::get_tool_call() raises a clear error rather than crashing
opaquely if the model doesn't comply.

`model` is always a parameter, never constructed internally, so tests can
substitute a duck-typed fake and exercise everything except the actual
network call. Observation (schemas/observation.py) is a separate type from
Assessment: nothing here traces to a rule, and nothing here scores.
"""
from __future__ import annotations



from schemas import Assessment, Fact, KYAEvidenceBundle, KYAResultSummary, Observation, Ruleset
from schemas.dossier import LoadedDossier

from .llm import (
    briefing_message, format_escalation_addendum, format_reviewer_addendum, get_model,
    get_tool_call, log_cache_usage, ModelDidNotCallTool, parse_observations, system_message,
    THINKING_EFFORT, with_reasoning,
)
from .prompts import assemble

__all__ = [
    "Observation",
    "ModelDidNotCallTool",
    "reason_about_case",
    "narrate_findings",
    "structured_view",
    "activity_summary",
]


REASONING_PROMPT_ID = "SPECIALIST-KYA"
REASONING_SYSTEM_PROMPT = assemble(REASONING_PROMPT_ID).effective


_OBSERVATION_TOOL = with_reasoning({
    "name": "record_observations",
    "description": "Record zero or more observations about this agent's credential that the fixed rule checks would not catch.",
    "input_schema": {
        "type": "object",
        "properties": {
            "observations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "note": {"type": "string", "description": "Short, specific description of the observation."},
                        "cited_field": {"type": "string", "description": "The exact field/value in the data this concerns, e.g. kya_credential.issuer.issuer_name."},
                    },
                    "required": ["note", "cited_field"],
                },
            },
        },
        "required": ["observations"],
    },
})


def activity_summary(dossier: LoadedDossier) -> dict:
    """What `REG-03` compares against the registered classification: a
    transaction summary computed from the history the submission already
    carries — no new firm data, an evidence-floor widening (kya-ruleset.md
    Part 3.5)."""
    txns = dossier.transaction_history
    settled = [t for t in txns if t.status == "settled"]
    return {
        "transactions": len(txns),
        "in_window": sum(1 for t in txns if t.run_ref),
        "settled_total": round(sum(t.amount for t in settled), 2),
        "largest_single": max((t.amount for t in settled), default=0.0),
        "mean_amount": round(sum(t.amount for t in settled) / len(settled), 2) if settled else 0.0,
        "distinct_counterparties": len({t.counterparty_id for t in txns}),
        "mccs": sorted({t.mcc for t in txns}),
        "currencies": sorted({t.currency for t in txns}),
        "channels": sorted({t.channel for t in txns}),
        "first": min((t.timestamp for t in txns), default=None),
        "last": max((t.timestamp for t in txns), default=None),
        "runs": len(dossier.runs),
        "purpose_categories": sorted({r.intent_mandate.authorization_scope.purpose_category
                                      for r in dossier.runs}),
    }


def structured_view(
    dossier: LoadedDossier, floor_facts: list[Fact], ruleset: Ruleset | None = None
) -> dict:
    """Build the complete, bounded KYA evidence bundle.

    Every active/draft KYA rule and every rule result is represented. Clean
    per-run outcomes are compressed to ids/counts/run refs; breaches,
    absences and measurements are included in full. The reasoning model can
    therefore cite exact facts and runs while still seeing enough typed
    dossier/registry evidence to hunt for in-domain issues no rule covers.
    """
    from data.issuers import load_issuer_registry
    from data.registries import load_agents, load_model_blocklist, load_operators
    from registry.loader import load_failure_catalogue

    credential = dossier.dossier.kya_credential
    by_rule: dict[str, dict[str, int]] = {}
    for f in floor_facts:
        if f.rule_id and f.kind != "measurement":
            by_rule.setdefault(f.rule_id, {})
            by_rule[f.rule_id][f.kind] = by_rule[f.rule_id].get(f.kind, 0) + 1
    agent_record = load_agents().get(dossier.dossier.agent_id)
    operator_record = load_operators().get(dossier.dossier.operator_id)
    issuer_record = load_issuer_registry().get(credential.issuer.issuer_id)
    declared_models = sorted({r.intent_mandate.agent.model_version for r in dossier.runs})
    blocklist = load_model_blocklist()
    purpose_categories = sorted({r.intent_mandate.authorization_scope.purpose_category
                                 for r in dossier.runs})
    summaries = [KYAResultSummary(
        rule_id=rule_id,
        counts=kinds,
        fact_ids=[f.fact_id for f in floor_facts
                  if f.rule_id == rule_id and f.kind != "satisfied"],
        run_refs=sorted({f.run_ref for f in floor_facts
                         if f.rule_id == rule_id and f.run_ref}),
    ) for rule_id, kinds in sorted(by_rule.items())]
    bundle = KYAEvidenceBundle(
        case_id=dossier.dossier.dossier_id,
        review_scope={"kind": "whole_dossier", "run_refs": [r.run_id for r in dossier.runs]},
        agent_id=dossier.dossier.agent_id,
        operator_id=dossier.dossier.operator_id,
        ruleset={"ruleset_id": ruleset.ruleset_id if ruleset else None,
                 "version": ruleset.version if ruleset else None},
        failure_catalogue_version=load_failure_catalogue().version,
        rule_inventory=[{
            "rule_id": r.rule_id, "description": r.description, "status": r.status,
            "evaluation": r.evaluation, "severity_weight": r.severity_weight,
            "failure_ids": list(r.failures),
        } for r in (ruleset.rules if ruleset else [])],
        rule_results=summaries,
        attention_facts=[f for f in floor_facts if f.kind != "satisfied"],
        agent_registry_record=agent_record,
        operator_registry_record=operator_record,
        issuer_registry_record=issuer_record,
        blocked_model_records=[blocklist[m] for m in declared_models if m in blocklist],
        registered_classification=(agent_record or {}).get("classification"),
        registered_risk_class=(agent_record or {}).get("risk_class"),
        declared_purpose=(agent_record or {}).get("declared_purpose"),
        activity_summary=activity_summary(dossier),
        credential={
            "credential_id": credential.credential_id,
            "agent_id": credential.agent_id,
            "agent_name": credential.agent_name,
            "operator_firm": credential.operator_firm,
            "issuer_name": credential.issuer.issuer_name,
            "issuer_id": credential.issuer.issuer_id,
            "revocation_checked_at": credential.revocation_checked_at,
            "revocation_source": credential.revocation_source,
            "issued_at": credential.issued_at,
            "expires_at": credential.expires_at,
            "capabilities": credential.capabilities,
            "delegation_chain": [
                {"level": e.level, "holder_type": e.holder_type, "holder_id": e.holder_id,
                 "name": e.name, "granted_capabilities": e.granted_capabilities}
                for e in credential.delegation_chain
            ],
        },
        credential_history=[
            {"credential_id": c.credential_id, "issued_at": c.issued_at, "expires_at": c.expires_at,
             "agent_id": c.agent_id, "issuer_id": c.issuer.issuer_id,
             "capabilities": c.capabilities,
             "delegation_terminus": (c.delegation_chain[-1].holder_id
                                      if c.delegation_chain else None)}
            for c in dossier.dossier.credential_history
        ],
        run_identity_evidence=[{
            "run_ref": r.run_id,
            "outcome": r.outcome,
            "environment": r.environment,
            "trigger": r.trigger,
            "principal": r.intent_mandate.principal.model_dump(),
            "agent": r.intent_mandate.agent.model_dump(),
            "purpose_category": r.intent_mandate.authorization_scope.purpose_category,
            "human_presence_required": r.intent_mandate.authorization_scope.human_presence_required,
        } for r in dossier.runs],
        purpose_categories=purpose_categories,
        runs=len(dossier.runs),
        already_flagged_by_fixed_rules=sorted(
            rid for rid, kinds in by_rule.items() if kinds.get("breach")),
        rule_outcomes=by_rule,
    )
    return bundle.model_dump(mode="json")


_CLASSIFICATION_FIT = {
    "type": "object",
    "description": "KYA-REG-03: does the observed activity (activity_summary) fit the registered classification and declared purpose?",
    "properties": {
        "consistent": {"type": "boolean"},
        "explanation": {"type": "string", "description": "One sentence."},
        "cited_evidence": {"type": "string", "description": "Quote the activity_summary numbers this rests on."},
    },
    "required": ["consistent", "explanation", "cited_evidence"],
}


def _judged_rule(ruleset, rule_type: str):
    if ruleset is None:
        return None
    return next((r for r in ruleset.rules if r.type == rule_type and r.status == "active"), None)


async def reason_about_case(
    dossier: LoadedDossier,
    floor_facts: list[Fact],
    *,
    model=None,
    thinking_effort: str = THINKING_EFFORT,
    prior_observations: list[Observation] | None = None,
    reviewer_directive: str | None = None,
    system_prompt: str | None = None,
    context: dict | None = None,
    ruleset=None,
    round: int = 1,
) -> tuple[list[Observation], list[Assessment]]:
    """The agentic ceiling. Needs a live ANTHROPIC_API_KEY unless `model`
    is supplied (tests inject a fake).

    `prior_observations`, when given (the escalation round), asks the model
    to resolve those specific observations rather than search for new ones.
    Observations never become assessments. The one judged rule KYA owns,
    `REG-03` (activity fits the registered classification), is asked for
    only when it is active in `ruleset` — a draft rule is not judged — and
    its verdict cites the floor's `activity_summary` measurement.
    """
    reg_03 = _judged_rule(ruleset, "agent_activity_matches_classification")
    tool = _OBSERVATION_TOOL
    if reg_03 is not None:
        tool = {**_OBSERVATION_TOOL, "input_schema": {
            **_OBSERVATION_TOOL["input_schema"],
            "properties": {**_OBSERVATION_TOOL["input_schema"]["properties"],
                           "classification_fit": _CLASSIFICATION_FIT},
            "required": [*_OBSERVATION_TOOL["input_schema"]["required"], "classification_fit"],
        }}
    model = model or get_model()
    bound = model.bind(
        output_config={"effort": thinking_effort},
        tools=[tool],
        tool_choice={"type": "auto"},
    )

    system = system_prompt or REASONING_SYSTEM_PROMPT
    if prior_observations:
        system += format_escalation_addendum(prior_observations)
    if reviewer_directive:
        system += format_reviewer_addendum(reviewer_directive)

    response = await bound.ainvoke([
        system_message(system),
        # A pre-composed context (canonical base + orchestrator-added blocks,
        # agents/context.py) is used verbatim — it is exactly what
        # dispatch_recorded logged. Absent one, the canonical view alone.
        briefing_message(context if context is not None else structured_view(dossier, floor_facts, ruleset)),
    ])
    log_cache_usage(response, "kya")

    tool_input = get_tool_call(response, "record_observations")
    case_id = dossier.dossier.dossier_id
    observations = parse_observations(tool_input.get("observations", []), case_id=case_id,
                                      agent="kya", cited_key="cited_field")
    assessments: list[Assessment] = []
    fit = tool_input.get("classification_fit") if reg_03 is not None else None
    if isinstance(fit, dict) and "consistent" in fit:
        measurement = next((f for f in floor_facts if f.kind == "measurement"
                            and f.rule_id == reg_03.rule_id), None)
        assessments.append(Assessment(
            assessment_id=f"{case_id}:kya:{reg_03.rule_id}:r{round}", case_id=case_id, round=round,
            scope="case", agent="kya", rule_id=reg_03.rule_id,
            fact_ids=[measurement.fact_id] if measurement else [],
            verdict="clear" if fit["consistent"] else "breach", confidence="probable",
            severity_floor=reg_03.severity_weight, severity_assessed=reg_03.severity_weight,
            narrative=fit.get("explanation", ""), subject=fit.get("cited_evidence") or None))
    return observations, assessments


NARRATION_PROMPT_ID = "KYA-NARRATION"
NARRATION_SYSTEM_PROMPT = assemble(NARRATION_PROMPT_ID).effective

_NARRATION_TOOL = with_reasoning({
    "name": "write_narration",
    "description": "Write the plain-English KYA review summary.",
    "input_schema": {
        "type": "object",
        "properties": {"narration": {"type": "string"}},
        "required": ["narration"],
    },
})


async def narrate_findings(
    case_id: str,
    assessments: list[Assessment],
    *,
    model=None,
    thinking_effort: str = THINKING_EFFORT,
    system_prompt: str | None = None,
) -> str:
    """Grounded narration of `assessments` only — never raw case data. Needs
    a live ANTHROPIC_API_KEY unless `model` is supplied."""
    model = model or get_model()
    bound = model.bind(
        output_config={"effort": thinking_effort},
        tools=[_NARRATION_TOOL],
        tool_choice={"type": "auto"},
    )

    payload = {
        "case_id": case_id,
        "findings": [{"rule_id": a.rule_id, "verdict": a.verdict, "summary": a.narrative,
                      "runs": a.run_refs} for a in assessments],
    }

    response = await bound.ainvoke([
        system_message(system_prompt or NARRATION_SYSTEM_PROMPT),
        briefing_message(payload),
    ])
    log_cache_usage(response, "kya-narration")

    tool_input = get_tool_call(response, "write_narration")
    return tool_input["narration"]
