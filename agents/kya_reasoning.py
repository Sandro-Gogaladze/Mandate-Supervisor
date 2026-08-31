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


REASONING_SYSTEM_PROMPT = """You are assisting a bank regulator's KYA (Know Your Agent) \
review of one AI payment agent's identity credential. A fixed set of deterministic rules \
has already been evaluated against this credential — their results are provided to you, \
and you are not re-checking them or second-guessing their verdicts.

Your only job is to look at the structured data below for anything those fixed rules \
would not catch — for example, an issuer or delegation-chain holder name that closely \
resembles a real trusted name (possible impersonation or typosquatting), or anything else \
structurally unusual worth a human reviewer's second look.

You are NOT authorized to state that a rule was violated, assign a severity, or restate \
a finding that's already listed. If you notice nothing beyond what's already listed, \
call the tool with an empty observations list — do not invent a concern to have something \
to report. Every observation must quote the exact field and value it concerns via
cited_field.

Take as long as you need to think this through carefully before answering — consider \
each field in the data individually, and specifically consider whether an issuer or \
holder name that looks like it resembles a known trusted entity might instead simply BE \
that trusted entity's own legitimate, correctly-issued credential; resemblance to a real \
name is only meaningful as a red flag when the credential is not already the genuine \
article, so weigh that possibility explicitly before treating resemblance as suspicious.

However you reason, your final response MUST be a call to the record_observations tool \
and nothing else — do not end your turn with plain text."""


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


def _structured_view(case: IngestedCase, floor_findings: list[Finding]) -> dict:
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

    system = REASONING_SYSTEM_PROMPT
    if prior_observations:
        system += format_escalation_addendum(prior_observations)
    if reviewer_directive:
        system += format_reviewer_addendum(reviewer_directive)

    response = await bound.ainvoke([
        SystemMessage(content=system),
        HumanMessage(content=json.dumps(_structured_view(case, floor_findings), indent=2)),
    ])

    tool_input = get_tool_call(response, "record_observations")
    raw = tool_input.get("observations", [])
    return parse_observations(raw, case_id=case.case.case_id, agent="kya", cited_key="cited_field")


NARRATION_SYSTEM_PROMPT = """You write a short, plain-English summary of a KYA (Know Your \
Agent) review for a bank case officer. You will be given a list of findings that were \
already verified by deterministic checks. Cite only these findings, using their exact \
type and summary text — do not add any claim that is not present in the list provided. \
If the list is empty, say plainly in one sentence that the credential passed every check.

However you reason, your final response MUST be a call to the write_narration tool and \
nothing else — do not end your turn with plain text."""

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
        SystemMessage(content=NARRATION_SYSTEM_PROMPT),
        HumanMessage(content=json.dumps(payload, indent=2)),
    ])

    tool_input = get_tool_call(response, "write_narration")
    return tool_input["narration"]
