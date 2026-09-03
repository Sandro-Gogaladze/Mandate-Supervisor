"""Log's full anomaly analysis — LLM-judged, no hardcoded detection rule
of any kind (PLAN item 7, revised: no deterministic verdict layer at all).

agents/log_stats.py still does pure arithmetic (sums, groupbys, candidate
same-counterparty clusters) — that's data preparation an LLM would do
unreliably itself (precise multi-transaction summation, minute-level gap
detection across dozens of rows), not a judgment. What changed is that
nothing in this codebase pre-decides whether a candidate cluster, a
concentration share, or a velocity burst actually *counts* as reportable —
every verdict, including structuring, is the model's judgment over the
real evidence, not a Python threshold comparison.

Three named, scoped categories become real Finding-producing rules
(structuring, concentration, velocity) — well-defined enough to be rules,
grounded in real computed evidence the model must quote, same reasoning as
agents/mandate_reasoning.py's semantic subcheck. Anything else goes into
`other_observations` — Observation-style, unscored, same tier as
agents/kya_reasoning.py's ceiling.
"""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from ingestion.normalize import IngestedCase
from schemas import Finding, Observation, Rule, typed_params

from .llm import THINKING_EFFORT, format_escalation_addendum, format_reviewer_addendum, get_model, get_tool_call, parse_observations
from .prompts import assemble
from .log_stats import (
    amount_stats,
    counterparty_breakdown,
    hourly_distribution,
    structuring_clusters,
    to_dataframe,
    velocity_stats,
)

PROMPT_ID = "SPECIALIST-LOG"
SYSTEM_PROMPT = assemble(PROMPT_ID).effective


_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "anomalous": {"type": "boolean"},
        "explanation": {"type": "string"},
        "cited_evidence": {"type": "string", "description": "Quote the specific numbers, transaction ids, or cluster contents this judgment is based on."},
    },
    "required": ["anomalous", "explanation", "cited_evidence"],
}

_LOG_ANALYSIS_TOOL = {
    "name": "record_log_analysis",
    "description": "Record the structuring, concentration, and velocity judgments, plus any other open observations.",
    "input_schema": {
        "type": "object",
        "properties": {
            "structuring": _VERDICT_SCHEMA,
            "concentration": _VERDICT_SCHEMA,
            "velocity": _VERDICT_SCHEMA,
            "other_observations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "note": {"type": "string"},
                        "cited_evidence": {"type": "string"},
                    },
                    "required": ["note", "cited_evidence"],
                },
            },
        },
        "required": ["structuring", "concentration", "velocity", "other_observations"],
    },
}


def _classification(case: IngestedCase) -> str | None:
    """This agent's registered classification, or None if it is not registered.

    None falls back to the ruleset's default threshold, which is the right
    behaviour: an agent the regulator has never heard of is a finding for KYA
    to make, not a reason for Log to guess at a number.
    """
    from data.registries import load_agents

    agent_id = case.case.kya_credential.agent_id
    record = load_agents().get(agent_id)
    return record.get("classification") if record else None


def structured_view(case: IngestedCase, structuring_rule: Rule) -> dict:
    """Log's canonical evidence — see agents/kya_reasoning.structured_view."""
    df = to_dataframe(case.case.transaction_history)
    scope = case.case.mandate_chain.intent.authorization_scope
    params = typed_params(structuring_rule)
    candidate_clusters = [
        c for c in structuring_clusters(df, window_hours=params.window_hours)
        if len(c["transaction_ids"]) >= params.min_cluster_size
    ]
    return {
        "purpose_category": scope.purpose_category,
        "approved_counterparty_count": len(scope.allowed_counterparties) or "unrestricted (category-governed)",
        # Resolved for THIS agent's classification. A threshold set beyond an
        # agent's entire operating range is not a lenient rule, it is a rule
        # switched off — and the eval would read its silence as clean
        # behaviour rather than as a dial pointing at nothing.
        "reporting_flag_threshold": params.resolve(_classification(case)),
        "candidate_structuring_clusters": candidate_clusters,
        "counterparty_breakdown": counterparty_breakdown(df),
        "velocity_stats": velocity_stats(df),
        "amount_stats": amount_stats(df),
        "hourly_distribution": hourly_distribution(df),
        "transaction_count": len(df),
    }


async def analyze_log(
    case: IngestedCase,
    structuring_rule: Rule,
    concentration_rule: Rule,
    velocity_rule: Rule,
    *,
    model=None,
    thinking_effort: str = THINKING_EFFORT,
    prior_observations: list[Observation] | None = None,
    reviewer_directive: str | None = None,
    system_prompt: str | None = None,
    context: dict | None = None,
) -> tuple[list[Finding], list[Observation]]:
    """The entire Log agent. Needs a live ANTHROPIC_API_KEY unless `model`
    is supplied.

    `prior_observations` (PLAN item 9's escalation round) asks the model
    to resolve those specific observations with fresh attention on the
    same evidence — unlike KYA's ceiling, a resolved observation here CAN
    genuinely flip one of the three named categories to anomalous=true,
    since those are real rules, not open exploration.
    """
    if not case.case.transaction_history:
        return [], []

    model = model or get_model()
    bound = model.bind(
        output_config={"effort": thinking_effort},
        tools=[_LOG_ANALYSIS_TOOL],
        tool_choice={"type": "auto"},
    )

    system = system_prompt or SYSTEM_PROMPT
    if prior_observations:
        system += format_escalation_addendum(prior_observations)
    if reviewer_directive:
        system += format_reviewer_addendum(reviewer_directive)

    response = await bound.ainvoke([
        SystemMessage(content=system),
        HumanMessage(content=json.dumps(
            context if context is not None else structured_view(case, structuring_rule),
            indent=2,
        )),
    ])

    result = get_tool_call(response, "record_log_analysis")
    case_id = case.case.case_id

    def _verdict_finding(key: str, rule: Rule, suffix: str) -> Finding | None:
        verdict = result[key]
        if not verdict["anomalous"]:
            return None
        return Finding(
            finding_id=f"{case_id}-{suffix}-001", case_id=case_id, agent="log",
            type=rule.finding_type, rule_id=rule.rule_id, severity_weight=rule.severity_weight,
            summary=verdict["explanation"], details={"cited_evidence": verdict["cited_evidence"]},
        )

    findings = [
        f for f in (
            _verdict_finding("structuring", structuring_rule, "STR"),
            _verdict_finding("concentration", concentration_rule, "CON"),
            _verdict_finding("velocity", velocity_rule, "VEL"),
        )
        if f is not None
    ]

    observations = parse_observations(result.get("other_observations", []), case_id=case_id, agent="log")
    return findings, observations
