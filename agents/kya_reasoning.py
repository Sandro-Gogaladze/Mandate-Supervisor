"""The agentic ceiling: free-text reasoning over anything the fixed KYA
rules can't catch, plus narration of the findings that did fire.

Both run with adaptive thinking at high effort and are still
schema-constrained via a tool — output is always structured, never
free-form prose to parse with regex, same discipline CLAUDE.md requires
for the one place raw firm text reaches an LLM (Mandate's prompt_playback
subcheck). `tool_choice` stays `{"type": "auto"}` rather than forced —
Anthropic's thinking modes require it — so the system prompts compensate
by instructing the model explicitly, and agents/llm.py::get_tool_call()
raises a clear error rather than crashing opaquely if the model doesn't
comply.

`model` is always a parameter, never constructed internally, so tests can
substitute a duck-typed fake and exercise everything except the actual
network call. See docs/phases/05-kya-agent.md for why Observation
(schemas/observation.py — shared with the Log agent's own open-ended tail,
Phase 7) is a separate type from Finding rather than reusing it.
"""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from ingestion.normalize import IngestedCase
from schemas import Finding, Observation

from .prompts import assemble
from .llm import (
    THINKING_EFFORT,
    ModelDidNotCallTool,
    format_escalation_addendum,
    format_reviewer_addendum,
    get_model,
    get_tool_call,
    parse_observations,
)

__all__ = [
    "Observation",
    "ModelDidNotCallTool",
    "reason_about_case",
    "narrate_findings",
]


REASONING_PROMPT_ID = "SPECIALIST-KYA"
# The default, assembled from registry/prompts/ (architecture-v2 §12) —
# preamble and tool contract are fixed; only the body is per-run overridable.
REASONING_SYSTEM_PROMPT = assemble(REASONING_PROMPT_ID).effective


_OBSERVATION_TOOL = {
    "name": "record_observations",
    "description": "Record zero or more observations about this case that the fixed rule checks would not catch.",
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
}


def structured_view(case: IngestedCase, floor_findings: list[Finding]) -> dict:
    """KYA's canonical evidence — the base every dispatch of this skill
    always contains (architecture-v2 §9.2, the evidence floor). Public so
    agents/context.py can compose it with orchestrator-added blocks."""
    credential = case.case.kya_credential
    intent = case.case.mandate_chain.intent
    return {
        "credential": {
            "issuer_name": credential.issuer.issuer_name,
            "issuer_id": credential.issuer.issuer_id,
            "capabilities": credential.capabilities,
            "delegation_chain": [
                {"level": e.level, "holder_type": e.holder_type, "holder_id": e.holder_id, "name": e.name}
                for e in credential.delegation_chain
            ],
        },
        "purpose_category": intent.authorization_scope.purpose_category,
        "already_flagged_by_fixed_rules": [f.type for f in floor_findings],
    }


async def reason_about_case(
    case: IngestedCase,
    floor_findings: list[Finding],
    *,
    model=None,
    thinking_effort: str = THINKING_EFFORT,
    prior_observations: list[Observation] | None = None,
    reviewer_directive: str | None = None,
    system_prompt: str | None = None,
    context: dict | None = None,
) -> list[Observation]:
    """The agentic ceiling. Needs a live ANTHROPIC_API_KEY unless `model`
    is supplied (tests inject a fake).

    `prior_observations`, when given (PLAN item 9's escalation round), asks
    the model to resolve those specific observations rather than search
    for new ones — see agents/llm.py::ESCALATION_ADDENDUM. The output is
    still only ever Observation, never Finding: KYA's ceiling has no rule
    to promote an escalated observation into, escalation here can only
    narrow toward a sharper/more-confident observation or drop it, see
    docs/phases/09-dispatch-and-escalation.md.
    """
    model = model or get_model()
    bound = model.bind(
        output_config={"effort": thinking_effort},
        tools=[_OBSERVATION_TOOL],
        tool_choice={"type": "auto"},
    )

    # `system_prompt` is the per-run assembled text (default or override) —
    # agents/prompts.py guarantees the tool contract survives any override.
    system = system_prompt or REASONING_SYSTEM_PROMPT
    if prior_observations:
        system += format_escalation_addendum(prior_observations)
    if reviewer_directive:
        system += format_reviewer_addendum(reviewer_directive)

    response = await bound.ainvoke([
        SystemMessage(content=system),
        HumanMessage(content=json.dumps(
            # A pre-composed context (canonical base + orchestrator-added
            # blocks, agents/context.py) is used verbatim — it is exactly what
            # dispatch_recorded logged. Absent one, the canonical view alone.
            context if context is not None else structured_view(case, floor_findings),
            indent=2,
        )),
    ])

    tool_input = get_tool_call(response, "record_observations")
    raw = tool_input.get("observations", [])
    return parse_observations(raw, case_id=case.case.case_id, agent="kya", cited_key="cited_field")


NARRATION_PROMPT_ID = "KYA-NARRATION"
NARRATION_SYSTEM_PROMPT = assemble(NARRATION_PROMPT_ID).effective

_NARRATION_TOOL = {
    "name": "write_narration",
    "description": "Write the plain-English KYA review summary.",
    "input_schema": {
        "type": "object",
        "properties": {"narration": {"type": "string"}},
        "required": ["narration"],
    },
}


async def narrate_findings(
    case_id: str,
    findings: list[Finding],
    *,
    model=None,
    thinking_effort: str = THINKING_EFFORT,
    system_prompt: str | None = None,
) -> str:
    """Grounded narration of `findings` only — never raw case data. Needs a
    live ANTHROPIC_API_KEY unless `model` is supplied."""
    model = model or get_model()
    bound = model.bind(
        output_config={"effort": thinking_effort},
        tools=[_NARRATION_TOOL],
        tool_choice={"type": "auto"},
    )

    payload = {
        "case_id": case_id,
        "findings": [{"type": f.type, "summary": f.summary, "rule_id": f.rule_id} for f in findings],
    }

    response = await bound.ainvoke([
        SystemMessage(content=system_prompt or NARRATION_SYSTEM_PROMPT),
        HumanMessage(content=json.dumps(payload, indent=2)),
    ])

    tool_input = get_tool_call(response, "write_narration")
    return tool_input["narration"]
