"""Propose-enforce dispatch (PLAN item 9) — CLAUDE.md: "LLM proposes a
DispatchPlan, a deterministic validator enforces a mandatory floor."

The floor resolves the tension documented in docs/phases/07-log-agent.md
and 08-drift-agent.md: CLAUDE.md's single stated "Log+Drift run when
history >= 30 tx" bundles two agents with very different actual minimums.
Drift's own `min_total_transactions` ruleset param (default 30) is exactly
where that number belongs — a baseline/comparison split needs real volume.
Log's structuring check can validly fire on a handful of transactions, so
its floor is just "non-empty," not 30.
"""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm import THINKING_EFFORT, get_model, get_tool_call
from agents.prompts import assemble
from ingestion.normalize import IngestedCase
from registry.loader import load_drift_ruleset
from schemas import DispatchPlan, Ruleset, typed_params

PROMPT_ID = "ORCH-DISPATCH"
SYSTEM_PROMPT = assemble(PROMPT_ID).effective

_DISPATCH_PLAN_TOOL = {
    "name": "record_dispatch_plan",
    "description": "Record which specialists should run for this case.",
    "input_schema": {
        "type": "object",
        "properties": {
            "run_mandate": {"type": "boolean"},
            "run_kya": {"type": "boolean"},
            "run_log": {"type": "boolean"},
            "run_drift": {"type": "boolean"},
            "reasoning": {"type": "string"},
        },
        "required": ["run_mandate", "run_kya", "run_log", "run_drift", "reasoning"],
    },
}


def _case_summary(case: IngestedCase) -> dict:
    intent = case.case.mandate_chain.intent
    return {
        "firm": case.case.firm.name,
        "purpose_category": intent.authorization_scope.purpose_category,
        "transaction_count": len(case.case.transaction_history),
    }


async def propose_dispatch_plan(
    case: IngestedCase, *, model=None, thinking_effort: str = THINKING_EFFORT,
    system_prompt: str | None = None,
) -> DispatchPlan:
    """Needs a live ANTHROPIC_API_KEY unless `model` is supplied."""
    model = model or get_model()
    bound = model.bind(
        output_config={"effort": thinking_effort},
        tools=[_DISPATCH_PLAN_TOOL],
        tool_choice={"type": "auto"},
    )

    response = await bound.ainvoke([
        SystemMessage(content=system_prompt or SYSTEM_PROMPT),
        HumanMessage(content=json.dumps(_case_summary(case), indent=2)),
    ])

    result = get_tool_call(response, "record_dispatch_plan")
    return DispatchPlan.model_validate(result)


def enforce_floor(plan: DispatchPlan, case: IngestedCase, drift_ruleset: Ruleset | None = None) -> DispatchPlan:
    """The deterministic validator. Can only turn False into True — never
    silently drop a specialist the LLM proposed to run."""
    drift_ruleset = drift_ruleset or load_drift_ruleset()
    drift_rule = next(
        (r for r in drift_ruleset.rules if r.type == "behavioral_drift_detected" and r.status == "active"),
        None,
    )
    min_drift_tx = typed_params(drift_rule).min_total_transactions if drift_rule else 30
    tx_count = len(case.case.transaction_history)

    return plan.model_copy(update={
        "run_mandate": True,  # mandatory, no exceptions
        "run_kya": True,  # mandatory, no exceptions
        "run_log": plan.run_log or tx_count > 0,
        "run_drift": plan.run_drift or tx_count >= min_drift_tx,
    })
