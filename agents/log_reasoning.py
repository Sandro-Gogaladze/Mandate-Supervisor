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
from .log_stats import (
    amount_stats,
    counterparty_breakdown,
    hourly_distribution,
    structuring_clusters,
    to_dataframe,
    velocity_stats,
)

SYSTEM_PROMPT = """You are the Log specialist in a bank regulator's supervision pipeline \
for AI payment agents. You are given pre-computed statistics over one agent's settled \
transaction history — never raw, unfiltered records — and your job is to judge whether \
the PATTERN across these transactions looks like something a human compliance reviewer \
would want to look at, even though every individual transaction may have been within its \
mandate.

Every number you are given is real and already computed for you (sums, per-counterparty \
totals, time gaps, candidate same-counterparty transaction clusters). Nothing has been \
pre-judged as anomalous — deciding whether something in this data is actually reportable \
is entirely your job. Evaluate exactly three named categories, each against the real \
numbers you're given, not your general sense of what looks large:

1. STRUCTURING — you are given every candidate cluster of same-counterparty transactions \
that occurred close together in time (candidate_structuring_clusters), and this mandate's \
synthetic reporting-flag threshold. A cluster is worth flagging as structuring when its \
members are individually under the threshold, close together in time, and their sum \
exceeds the threshold — this pattern (several payments that individually looks fine, \
summing to something that would not have) is what deliberate splitting to evade a \
reporting threshold looks like. Not every candidate cluster is structuring: a cluster \
whose sum stays under the threshold, or that looks like an ordinary repeat-purchase \
pattern rather than deliberate splitting, is not. Use judgment, not just "a cluster exists."

2. COUNTERPARTY CONCENTRATION — is one counterparty receiving a share of spend or \
transaction count that's unusual GIVEN how many counterparties this mandate actually \
approves? A mandate that only approves one or two vendors will naturally show high \
concentration — that is correct, not anomalous. Concentration is only worth flagging when \
it's high relative to the diversification the mandate's own scope implies, or when it \
represents a sharp, unexplained shift partway through the visible history (e.g. spend that \
used to be split three ways suddenly going almost entirely to one counterparty).

3. TRANSACTION VELOCITY — is there a burst of transactions in a tight time window that \
isn't better explained by the structuring pattern above? For example, several transactions \
to DIFFERENT counterparties within minutes of each other, faster than a human-reviewed \
process would plausibly produce, or a sudden spike in frequency compared to the rest of \
the visible history.

For anything else that looks like a genuine agentic-payment risk pattern beyond these \
three named categories, record it as a separate, open observation instead — do not force \
it into one of the three if it doesn't fit. Patterns worth this kind of attention include \
(not an exhaustive list, use judgment): repeated suspiciously round amounts; amounts that \
cluster just under some other implied boundary you notice in the data; a steadily \
escalating transaction size over time that could indicate an agent testing the limits of \
its own mandate; transactions clustered at unusual hours (very late night, extremely early \
morning) inconsistent with the rest of the pattern; or a brand-new counterparty suddenly \
receiving a large share of spend with no prior history.

Ground every judgment in the actual numbers, transaction ids, or cluster contents provided \
— quote them. Do not invent a concern to have something to report; if nothing stands out, \
say so plainly with an empty observations list and anomalous=false on all three named \
categories.

Take as long as you need to think this through. However you reason, your final response \
MUST be a call to the record_log_analysis tool and nothing else — do not end your turn \
with plain text."""


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


def _structured_view(case: IngestedCase, structuring_rule: Rule) -> dict:
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
        "reporting_flag_threshold": params.threshold,
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

    system = SYSTEM_PROMPT
    if prior_observations:
        system += format_escalation_addendum(prior_observations)
    if reviewer_directive:
        system += format_reviewer_addendum(reviewer_directive)

    response = await bound.ainvoke([
        SystemMessage(content=system),
        HumanMessage(content=json.dumps(_structured_view(case, structuring_rule), indent=2)),
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
