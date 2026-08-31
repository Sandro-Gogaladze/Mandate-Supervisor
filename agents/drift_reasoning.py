"""Drift's LLM judgment — no hardcoded threshold decides whether a
statistical shift counts as drift, same design as agents/log_reasoning.py.

agents/drift_stats.py computes real PSI/z-score/frequency statistics
between a baseline window and everything after it — that's arithmetic an
LLM would do unreliably itself (population stability index across dozens
of transactions, precise mean/std). What it doesn't do is decide whether
the shift is *meaningful* drift versus, say, legitimate seasonal or
business-growth variation that happens to move the numbers without being
a supervisory concern. That judgment is the model's, grounded in the real
computed evidence.
"""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from ingestion.normalize import IngestedCase
from schemas import Finding, Observation, Rule, typed_params

from .drift_stats import amount_shift, distribution_psi, frequency_shift, mix_breakdown, split_baseline, to_dataframe
from .llm import THINKING_EFFORT, format_escalation_addendum, format_reviewer_addendum, get_model, get_tool_call, parse_observations
from .prompts import assemble

PROMPT_ID = "SPECIALIST-DRIFT"
SYSTEM_PROMPT = assemble(PROMPT_ID).effective


_DRIFT_ANALYSIS_TOOL = {
    "name": "record_drift_analysis",
    "description": "Record the drift judgment, plus any other open observations.",
    "input_schema": {
        "type": "object",
        "properties": {
            "drift": {
                "type": "object",
                "properties": {
                    "anomalous": {"type": "boolean"},
                    "explanation": {"type": "string"},
                    "cited_evidence": {"type": "string", "description": "Quote the specific PSI/z-score/frequency numbers this judgment is based on."},
                },
                "required": ["anomalous", "explanation", "cited_evidence"],
            },
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
        "required": ["drift", "other_observations"],
    },
}


def structured_view(case: IngestedCase, drift_rule: Rule) -> dict:
    """Drift's canonical evidence — see agents/kya_reasoning.structured_view."""
    df = to_dataframe(case.case.transaction_history)
    params = typed_params(drift_rule)
    baseline, comparison = split_baseline(df, baseline_window_days=params.baseline_window_days)
    scope = case.case.mandate_chain.intent.authorization_scope
    return {
        "purpose_category": scope.purpose_category,
        "baseline_window_days": params.baseline_window_days,
        "baseline_transaction_count": len(baseline),
        "comparison_transaction_count": len(comparison),
        "amount_shift": amount_shift(baseline, comparison),
        "frequency_shift": frequency_shift(baseline, comparison),
        "counterparty_mix_psi": distribution_psi(baseline, comparison, "counterparty_id"),
        "mcc_mix_psi": distribution_psi(baseline, comparison, "mcc"),
        "baseline_counterparty_mix": mix_breakdown(baseline, "counterparty_id"),
        "comparison_counterparty_mix": mix_breakdown(comparison, "counterparty_id"),
        "baseline_mcc_mix": mix_breakdown(baseline, "mcc"),
        "comparison_mcc_mix": mix_breakdown(comparison, "mcc"),
    }


async def analyze_drift(
    case: IngestedCase,
    drift_rule: Rule,
    *,
    model=None,
    thinking_effort: str = THINKING_EFFORT,
    prior_observations: list[Observation] | None = None,
    reviewer_directive: str | None = None,
    system_prompt: str | None = None,
    context: dict | None = None,
) -> tuple[list[Finding], list[Observation]]:
    """Needs a live ANTHROPIC_API_KEY unless `model` is supplied. Caller
    (agents/drift.py) is responsible for the insufficient_baseline gate —
    this assumes there's enough history to make a real comparison.

    `prior_observations` (PLAN item 9's escalation round) — same reasoning
    as agents/log_reasoning.py::analyze_log."""
    model = model or get_model()
    bound = model.bind(
        output_config={"effort": thinking_effort},
        tools=[_DRIFT_ANALYSIS_TOOL],
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
            context if context is not None else structured_view(case, drift_rule),
            indent=2,
        )),
    ])

    result = get_tool_call(response, "record_drift_analysis")
    case_id = case.case.case_id

    findings: list[Finding] = []
    if result["drift"]["anomalous"]:
        findings.append(Finding(
            finding_id=f"{case_id}-BHV-001", case_id=case_id, agent="drift",
            type=drift_rule.finding_type, rule_id=drift_rule.rule_id,
            severity_weight=drift_rule.severity_weight,
            summary=result["drift"]["explanation"],
            details={"cited_evidence": result["drift"]["cited_evidence"]},
        ))

    observations = parse_observations(result.get("other_observations", []), case_id=case_id, agent="drift")
    return findings, observations
