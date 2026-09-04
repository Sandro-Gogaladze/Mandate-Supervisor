"""The report drafting agent (PLAN item 12).

The only agent whose entire output is free prose — which is exactly why
its *input* is the most restricted in the pipeline (CLAUDE.md cross-
cutting rule 1): it receives the structured record only — typed findings,
observations, the dispatch plan, the escalation round — and never the raw
case file. No firm-authored text (`natural_language_intent`, line-item
descriptions, prompt playback) can reach it, so there is nothing here for
an injected instruction to ride in on. The firm's name and the case id
are the only submission-derived strings included, as identifiers.

Output is a typed `DraftReport` via a forced-shape tool call, same
pattern as every other agent. Grounding is NOT enforced here — the
deterministic validator (agents/grounding.py) does that from the graph,
with a bounded regenerate loop (pipeline/graph.py); on a retry the
validator's exact complaints are appended to the system prompt so the
model fixes the actual problems rather than re-rolling blind.
"""
from __future__ import annotations



from schemas import DispatchPlan, DraftReport, Finding, Observation, RiskScore

from .llm import (
    briefing_message, get_model, get_tool_call, log_cache_usage, system_message,
    THINKING_EFFORT, with_reasoning, without_reasoning,
)
from .prompts import assemble

PROMPT_ID = "DRAFTING"
SYSTEM_PROMPT = assemble(PROMPT_ID).effective

RETRY_ADDENDUM = """

Your previous draft FAILED grounding validation with these exact problems — fix every one of \
them; change nothing else about your approach:
{problems}"""

_REPORT_TOOL = with_reasoning({
    "name": "draft_case_report",
    "description": "Submit the drafted supervisory report for this case.",
    "input_schema": {
        "type": "object",
        "properties": {
            "overall_assessment": {
                "type": "string",
                "description": "One short paragraph: what the review found and how serious it is.",
            },
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "cited_finding_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "finding_id values from the input that this section's claims rest on.",
                        },
                    },
                    "required": ["title", "body", "cited_finding_ids"],
                },
            },
            "open_observations_note": {
                "type": ["string", "null"],
                "description": "Summary of unverified observations, or null if there are none.",
            },
        },
        "required": ["overall_assessment", "sections", "open_observations_note"],
    },
})


def _structured_view(
    firm_name: str,
    findings: list[Finding],
    observations: list[Observation],
    dispatch_plan: DispatchPlan | None,
    escalation_round: int,
    risk_score: RiskScore | None,
) -> dict:
    return {
        "firm": firm_name,
        "risk": (
            {
                "total": risk_score.total,
                "tier": risk_score.tier,
                "tier_label": risk_score.tier_label,
                "tier_guidance": risk_score.tier_guidance,
                "factors": [
                    {"agent": f.agent, "score": f.score, "finding_count": f.finding_count}
                    for f in risk_score.factors
                ],
            }
            if risk_score
            else None
        ),
        "findings": [
            {
                "finding_id": f.finding_id,
                "agent": f.agent,
                "type": f.type,
                "rule_id": f.rule_id,
                "severity_weight": f.severity_weight,
                "summary": f.summary,
                "details": f.details,
            }
            for f in findings
        ],
        "unverified_observations": [
            {"agent": o.agent, "note": o.note, "cited_evidence": o.cited_evidence}
            for o in observations
        ],
        "dispatch": (
            {
                "ran": [skill.split(".")[0] for skill in dispatch_plan.skills],
                "reasoning": dispatch_plan.reasoning,
            }
            if dispatch_plan
            else None
        ),
        "escalation_round_ran": escalation_round > 0,
    }


async def draft_case_report(
    *,
    case_id: str,
    firm_name: str,
    findings: list[Finding],
    observations: list[Observation],
    dispatch_plan: DispatchPlan | None,
    escalation_round: int,
    risk_score: RiskScore | None = None,
    prior_problems: list[str] | None = None,
    model=None,
    thinking_effort: str = THINKING_EFFORT,
    system_prompt: str | None = None,
) -> DraftReport:
    """Draft (or, with `prior_problems`, re-draft) the case report. Needs a
    live ANTHROPIC_API_KEY unless `model` is supplied (tests inject a fake)."""
    model = model or get_model()
    bound = model.bind(
        output_config={"effort": thinking_effort},
        tools=[_REPORT_TOOL],
        tool_choice={"type": "auto"},
    )

    system = system_prompt or SYSTEM_PROMPT
    if prior_problems:
        system += RETRY_ADDENDUM.format(problems="\n".join(f"- {p}" for p in prior_problems))

    payload = _structured_view(firm_name, findings, observations, dispatch_plan, escalation_round, risk_score)
    response = await bound.ainvoke([
        system_message(system),
        briefing_message(payload),
    ])
    log_cache_usage(response, "drafting")

    tool_input = get_tool_call(response, "draft_case_report")
    return DraftReport.model_validate({"case_id": case_id, **without_reasoning(tool_input)})
