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

import logging


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


logger = logging.getLogger(__name__)

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


def capability_profile(dossier: LoadedDossier) -> dict:
    """What `CAP-04` compares: the capabilities the credential grants against
    what the agent's registered purpose and its own observed activity show it
    actually needed. Least privilege is a judgement — how much unused breadth
    is too much depends on the agent — so the floor computes the comparison
    and records it, and the verdict is the model's.

    Everything here comes from evidence the submission already carries plus
    the regulator's own register. No new firm data."""
    from data.registries import load_agents

    record = load_agents().get(dossier.dossier.agent_id) or {}
    granted = list(dossier.dossier.kya_credential.capabilities)
    card = dossier.dossier.agent_card
    declared_on_card = sorted(card.declared_capabilities) if card else []
    # A capability the card never declares is breadth nothing has claimed a
    # use for — the cheapest signal of over-grant there is.
    return {
        "granted_capabilities": granted,
        "granted_count": len(granted),
        "declared_on_agent_card": declared_on_card,
        "granted_but_not_on_card": sorted(set(granted) - set(declared_on_card)) if card else [],
        "registered_classification": record.get("classification"),
        "registered_risk_class": record.get("risk_class"),
        "declared_purpose": record.get("declared_purpose"),
        "purpose_categories_exercised": sorted({r.intent_mandate.authorization_scope.purpose_category
                                                for r in dossier.runs}),
        "channels_observed": sorted({t.channel for t in dossier.transaction_history}),
        "runs": len(dossier.runs),
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


_LEAST_PRIVILEGE = {
    "type": "object",
    "description": "KYA-CAP-04: are the credential's capabilities materially broader than its purpose requires?",
    "properties": {
        "proportionate": {"type": "boolean",
                          "description": "false when the grant is materially broader than the purpose needs."},
        "explanation": {"type": "string", "description": "One sentence."},
        "cited_evidence": {"type": "string",
                           "description": "Quote the specific capabilities and the purpose text this rests on."},
    },
    "required": ["proportionate", "explanation", "cited_evidence"],
}

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


# Every judged rule KYA owns, and the tool slot that carries its verdict. The
# single source of truth for "which rules does this agent decide with a model"
# — read by reason_about_case() to build the tool, and by the ownership test
# that asserts no active rule is owned by nobody.
JUDGED_SLOTS: dict[str, tuple[str, dict]] = {
    "agent_activity_matches_classification": ("classification_fit", _CLASSIFICATION_FIT),
    "capabilities_least_privilege": ("least_privilege", _LEAST_PRIVILEGE),
}

# The boolean each slot answers with: a judged rule is clear when its own
# question comes back affirmative.
_OK_KEY = {"classification_fit": "consistent", "least_privilege": "proportionate"}


def _measurement_ids(facts: list[Fact], rule) -> list[str]:
    return [f.fact_id for f in facts if f.kind == "measurement" and f.rule_id == rule.rule_id]


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
    # One slot per ACTIVE judged rule this agent owns. Built from the ruleset
    # rather than hardcoded, so promoting a judged rule in the sandbox starts
    # producing its verdict with no code change — and retiring one stops it.
    judged = [(rule, key, schema) for rule_type, (key, schema) in JUDGED_SLOTS.items()
               if (rule := _judged_rule(ruleset, rule_type)) is not None]
    tool = _OBSERVATION_TOOL
    if judged:
        tool = {**_OBSERVATION_TOOL, "input_schema": {
            **_OBSERVATION_TOOL["input_schema"],
            "properties": {**_OBSERVATION_TOOL["input_schema"]["properties"],
                           **{key: schema for _, key, schema in judged}},
            "required": [*_OBSERVATION_TOOL["input_schema"]["required"],
                         *[key for _, key, _ in judged]],
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
    # `ok_key` is the boolean the model answers with: a judged rule is clear
    # when its own question is answered in the affirmative.
    ok_key = _OK_KEY
    for rule, key, _schema in judged:
        verdict = tool_input.get(key)
        if not isinstance(verdict, dict) or ok_key[key] not in verdict:
            # A judged rule whose verdict did not arrive is undecided, on the
            # record — never silently clear.
            logger.warning("KYA: no usable %s verdict on %s: %r", key, case_id, verdict)
            assessments.append(Assessment(
                assessment_id=f"{case_id}:kya:{rule.rule_id}:r{round}", case_id=case_id, round=round,
                scope="case", agent="kya", rule_id=rule.rule_id,
                fact_ids=_measurement_ids(floor_facts, rule),
                verdict="inconclusive", confidence="possible",
                severity_floor=rule.severity_weight, severity_assessed=rule.severity_weight,
                narrative=f"The model returned no usable {key} verdict; the evidence stands unjudged."))
            continue
        assessments.append(Assessment(
            assessment_id=f"{case_id}:kya:{rule.rule_id}:r{round}", case_id=case_id, round=round,
            scope="case", agent="kya", rule_id=rule.rule_id,
            fact_ids=_measurement_ids(floor_facts, rule),
            verdict="clear" if verdict[ok_key[key]] else "breach", confidence="probable",
            severity_floor=rule.severity_weight, severity_assessed=rule.severity_weight,
            narrative=verdict.get("explanation", ""), subject=verdict.get("cited_evidence") or None))
    return observations, assessments


# Narration moved to agents/narration.py — one voice, one prompt, all eight
# specialists. Re-exported so the KYA tests and any caller keep working.
from .narration import narrate as _narrate  # noqa: E402


async def narrate_findings(case_id: str, assessments, *, model=None, system_prompt=None, **_):
    return await _narrate("kya", case_id, assessments, model=model, system_prompt=system_prompt)
