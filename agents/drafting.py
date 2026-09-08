"""The report drafting agent (PLAN item 12).

The only agent whose entire output is free prose — which is exactly why
its *input* is the most restricted in the pipeline (CLAUDE.md cross-
cutting rule 1): it receives the structured record only — typed findings,
observations, the dispatch plan, the escalation round — and never the raw
case file. No firm-authored text (`natural_language_intent`, line-item
descriptions, prompt playback) can reach it, so there is nothing here for
an injected instruction to ride in on. The firm's name and the case id
are the only submission-derived strings included, as identifiers.

Output is a typed `DraftReport` via one forced-shape tool call. Grounding is
not enforced here: the graph runs a deterministic validator afterward. It
never regenerates the report, because the findings were already established
by the specialist pipeline.
"""
from __future__ import annotations

from schemas import DispatchPlan, DraftReport, Finding, Observation, RiskScore

from .llm import (
    briefing_message, get_model, get_tool_call, log_cache_usage,
    system_message, without_reasoning,
)
from .prompts import assemble

PROMPT_ID = "DRAFTING"
SYSTEM_PROMPT = assemble(PROMPT_ID).effective

def _resolve_refs(tool_input: dict, findings: list[Finding]) -> None:
    """Turn the `cited_findings` ref numbers back into real `finding_id`s.

    The model cites numbers; every consumer downstream — the grounding
    validator, the schema, the console — still sees real ids, so nothing but
    this call knows the difference. A ref outside the range is dropped rather
    than invented: grounding then reports the finding it stands for as
    uncited, which is exactly the complaint a reviewer should see.
    """
    ids = [f.finding_id for f in findings]
    sections = tool_input.get("sections")
    if not isinstance(sections, list):
        return
    for section in sections:
        if not isinstance(section, dict):
            continue
        refs = section.pop("cited_findings", None)
        if section.get("cited_finding_ids") is not None:
            continue                      # already real ids; leave them alone
        resolved = []
        for ref in refs if isinstance(refs, list) else []:
            try:
                index = int(ref)
            except (TypeError, ValueError):
                continue
            if 1 <= index <= len(ids):
                resolved.append(ids[index - 1])
        section["cited_finding_ids"] = resolved


_REPORT_TOOL = {
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
                        "cited_findings": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": (
                                "The `ref` NUMBERS of the findings this section's claims rest on — "
                                "e.g. [3, 7, 12]. Numbers only, never the finding text or a rule id."
                            ),
                        },
                        "character": {
                            "type": "string",
                            "enum": ["adverse", "clear", "mixed"],
                            "description": (
                                "What this section asserts, checked against the findings it cites: "
                                "'adverse' if it reports something the agent got wrong, 'clear' if it "
                                "reports checks that were satisfied, 'mixed' when it presents both "
                                "sides as the conclusion. An adverse section may cite a satisfied check "
                                "as context. Every input finding carries a `verdict` — use it."
                            ),
                        },
                    },
                    "required": ["title", "body", "cited_findings", "character"],
                },
            },
            "open_observations_note": {
                "type": ["string", "null"],
                "description": "Summary of unverified observations, or null if there are none.",
            },
        },
        "required": ["overall_assessment", "sections", "open_observations_note"],
    },
}


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
        # `verdict` is derived, not new evidence: a finding with no severity
        # weight is a rule that was SATISFIED, and on the current corpus 59% of
        # findings are that kind. Leaving the drafter to infer it from a null
        # severity is how a clean check gets written up as a breach.
        "findings": [
            {
                # A SHORT REFERENCE, not the identifier. The drafter used to
                # cite findings by their real ids, which meant transcribing
                # ~900 tokens of opaque strings like
                # `DOSSIER-LRK-2026-001:systemic:F57:Quickvale Direct Ltd:r1`
                # verbatim across the report — 64 of them on one case, none
                # of which grounding lets it omit. That is the longest purely
                # mechanical stretch of any tool call in the pipeline, and it
                # is where the malformed replies clustered. The model now
                # cites `[3, 7, 12]` and the code puts the ids back.
                "ref": n,
                "agent": f.agent,
                "type": f.type,
                "rule_id": f.rule_id,
                "verdict": "breach" if (f.severity_weight or 0) > 0 else "satisfied",
                "severity_weight": f.severity_weight,
                "summary": f.summary,
                # A report needs the supporting detail for failures.  Passing
                # it again for every satisfied check made drafting reread the
                # specialist work instead of reporting its conclusion.
                "details": f.details if (f.severity_weight or 0) > 0 else None,
            }
            for n, f in enumerate(findings, start=1)
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
    model=None,
    system_prompt: str | None = None,
) -> DraftReport:
    """Turn the completed findings record into one concise report.

    This is deliberately a non-thinking, non-streaming, forced-tool call.
    The specialist pipeline has already evaluated the evidence; drafting is
    presentation, so it must not enter a regenerate-until-valid loop.
    """
    model = model or get_model(thinking=False, max_tokens=4000, streaming=False)
    bound = model.bind(
        tools=[_REPORT_TOOL],
        tool_choice={"type": "any"},
    )

    system = system_prompt or SYSTEM_PROMPT

    payload = _structured_view(firm_name, findings, observations, dispatch_plan, escalation_round, risk_score)
    messages = [system_message(system), briefing_message(payload)]

    response = await bound.ainvoke(messages)
    log_cache_usage(response, "drafting")
    tool_input = without_reasoning(get_tool_call(response, "draft_case_report"))
    _resolve_refs(tool_input, findings)
    return DraftReport.model_validate({"case_id": case_id, **tool_input})
