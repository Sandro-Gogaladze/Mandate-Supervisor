"""The Mandate agent's one contained LLM call (CLAUDE.md: "Mandate is
deterministic checks + one contained LLM call, prompt_playback vs. Cart
semantic match").

Unlike agents/kya_reasoning.py's ceiling, this produces a real `Finding`,
not an unverified `Observation`. That's a deliberate difference, not an
inconsistency: KYA's ceiling was optional, additive, free-form exploration
we chose to add beyond the original plan, over an unbounded search space
where "nothing to weight a hunch by" was the honest description. This
check is a required, scoped, first-class part of Mandate's job — CLAUDE.md
names it as such, it corresponds to an actual rule (MND-SEM-01) with a
real rule_id and severity_weight, and it compares exactly two specific
pieces of text a human reviewer could independently re-check the same way.
The judgment isn't a hunch about an open-ended search; it's the one thing
no deterministic rule can do (semantic comparison of free text) standing
in for a rule that's otherwise identical in kind to every other Mandate
rule.

Cart.line_items[].description is the one field in the whole schema
allowed to carry adversarial content (docs/phases/01-synthetic-data.md
§2.3) — delimited explicitly below and the system prompt states outright
that it is data, never an instruction, matching CLAUDE.md's injection-
containment rule. This is deliberately independent of
agents/mandate_checks.py's line_item_description_injection_heuristic —
two different mechanisms (LLM judgment vs. deterministic pattern match)
so a manipulated semantic check doesn't leave injection detection with a
single point of failure.
"""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from ingestion.normalize import IngestedCase
from schemas import Finding, Rule

from .llm import THINKING_EFFORT, format_reviewer_addendum, get_model, get_tool_call
from .prompts import assemble

PROMPT_ID = "SPECIALIST-MANDATE"
SYSTEM_PROMPT = assemble(PROMPT_ID).effective


_SEMANTIC_CHECK_TOOL = {
    "name": "record_semantic_check",
    "description": "Record whether the cart is semantically consistent with the human's authorized intent.",
    "input_schema": {
        "type": "object",
        "properties": {
            "consistent": {"type": "boolean"},
            "quoted_evidence": {
                "type": "string",
                "description": "If not consistent: the exact text (from the cart or the agent's reasoning) that shows the mismatch. Empty string if consistent.",
            },
            "explanation": {"type": "string", "description": "One or two sentences explaining the judgment."},
        },
        "required": ["consistent", "quoted_evidence", "explanation"],
    },
}


def structured_view(case: IngestedCase) -> dict:
    """Mandate's canonical evidence — see agents/kya_reasoning.structured_view."""
    intent = case.case.mandate_chain.intent
    cart = case.case.mandate_chain.cart
    return {
        "human_authorized_intent": intent.natural_language_intent,
        "authorization_scope_purpose_category": intent.authorization_scope.purpose_category,
        "cart_agent_reasoning": cart.agent_attestation.reasoning,
        "cart_total": cart.cart_total,
        "cart_line_items": [
            {
                "sku": item.sku,
                "qty": item.qty,
                "unit_price": item.unit_price,
                "description": f"<<<UNTRUSTED_MERCHANT_TEXT>>>{item.description}<<<END_UNTRUSTED_MERCHANT_TEXT>>>",
            }
            for item in cart.line_items
        ],
    }


async def check_cart_reasoning_matches_intent(
    case: IngestedCase,
    rule: Rule,
    *,
    model=None,
    thinking_effort: str = THINKING_EFFORT,
    reviewer_directive: str | None = None,
    system_prompt: str | None = None,
    context: dict | None = None,
) -> Finding | None:
    """The LLM semantic subcheck. Needs a live ANTHROPIC_API_KEY unless
    `model` is supplied (tests inject a fake, same pattern as
    agents/kya_reasoning.py)."""
    model = model or get_model()
    bound = model.bind(
        output_config={"effort": thinking_effort},
        tools=[_SEMANTIC_CHECK_TOOL],
        tool_choice={"type": "auto"},
    )

    system = system_prompt or SYSTEM_PROMPT
    if reviewer_directive:
        system += format_reviewer_addendum(reviewer_directive)

    response = await bound.ainvoke([
        SystemMessage(content=system),
        HumanMessage(content=json.dumps(
            context if context is not None else structured_view(case), indent=2
        )),
    ])

    result = get_tool_call(response, "record_semantic_check")
    if result["consistent"]:
        return None

    return Finding(
        finding_id=f"{case.case.case_id}-SEM-001",
        case_id=case.case.case_id,
        agent="mandate",
        type=rule.finding_type,
        rule_id=rule.rule_id,
        severity_weight=rule.severity_weight,
        summary=result["explanation"],
        details={"quoted_evidence": result["quoted_evidence"]},
    )
