"""The conversational orchestrator (architecture-v2 §9.7, Stage 8).

A dispatcher that speaks, not a chatbot that knows. Its output is
structurally a routing decision — {intent, targets, instruction,
context_blocks, message_to_officer} via a forced-shape tool — never free
prose about the firm. Asked "is this structuring?", it routes to Log; it has
no channel through which to offer a verdict of its own, because its one tool
has no field for one.

It names skills from the registry and names context blocks from the record;
code resolves both. Unknown skill ids are dropped (logged) and a dispatch
with nothing valid left degrades to a reply — the model's creativity is
allowed in *what to ask for*, never in *what exists*.
"""
from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from ledger.projection import CaseRecord

from .llm import THINKING_EFFORT, get_model, get_tool_call
from .prompts import assemble
from .skills import SKILLS, skill_catalog

logger = logging.getLogger(__name__)

PROMPT_ID = "ORCH-SESSION"
SYSTEM_PROMPT = assemble(PROMPT_ID).effective

_ROUTE_TOOL = {
    "name": "route_supervisor_request",
    "description": "Route the officer's message: dispatch work to skills, or reply from the record.",
    "input_schema": {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": ["dispatch", "reply", "run_triage", "draft_report"],
            },
            "targets": {
                "type": "array", "items": {"type": "string"},
                "description": "skill_ids to dispatch (empty for a reply).",
            },
            "instruction": {
                "type": "string",
                "description": "The specific briefing for the dispatched skill(s), phrased from the officer's concern.",
            },
            "context_blocks": {
                "type": "array", "items": {"type": "string"},
                "description": "Record items to attach verbatim: finding:<id>, answer:<question_id>, score.",
            },
            "message_to_officer": {"type": "string"},
        },
        "required": ["intent", "message_to_officer"],
    },
}


class OrchestratorDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # "dispatch" and "reply" resolve inside the investigation run;
    # "run_triage" and "draft_report" are routing decisions the CALLER
    # executes (the UI starts the corresponding run) — the orchestrator
    # still only routes, it never runs anything itself.
    intent: str  # "dispatch" | "reply" | "run_triage" | "draft_report"
    targets: list[str] = Field(default_factory=list)
    instruction: str = ""
    context_blocks: list[str] = Field(default_factory=list)
    message_to_officer: str


def record_summary(record: CaseRecord) -> dict:
    """The structured record the orchestrator reasons over — findings,
    observations, answers, score. Our own agents' typed output, never the
    raw firm submission."""
    return {
        "case_id": record.case_id,
        "status": record.status,
        "risk_score": (
            {"total": record.risk_score.total, "tier": record.risk_score.tier}
            if record.risk_score else None
        ),
        "findings": [
            {"finding_id": f.finding_id, "agent": f.agent, "type": f.type,
             "rule_id": f.rule_id, "summary": f.summary}
            for f in record.findings
        ],
        "observations": [
            {"agent": o.agent, "note": o.note, "cited_evidence": o.cited_evidence}
            for o in record.observations
        ],
        "answers": [
            {"question_id": a.question_id, "question": a.question, "answer": a.answer}
            for a in record.answers
        ],
        "correlations": [c.model_dump() for c in record.correlations],
    }


async def route(
    officer_message: str,
    record: CaseRecord,
    *,
    model=None,
    thinking_effort: str = THINKING_EFFORT,
    system_prompt: str | None = None,
) -> OrchestratorDecision:
    """Needs a live ANTHROPIC_API_KEY unless `model` is supplied."""
    model = model or get_model()
    bound = model.bind(
        output_config={"effort": thinking_effort},
        tools=[_ROUTE_TOOL],
        tool_choice={"type": "auto"},
    )

    payload = {
        "officer_message": officer_message,
        "case_record": record_summary(record),
        "available_skills": [
            {"skill_id": s.skill_id, "agent": s.agent, "produces": s.produces,
             "description": s.description}
            for s in skill_catalog()
        ],
    }
    response = await bound.ainvoke([
        SystemMessage(content=system_prompt or SYSTEM_PROMPT),
        HumanMessage(content=json.dumps(payload, indent=2)),
    ])

    result = get_tool_call(response, "route_supervisor_request")
    intent = result.get("intent", "reply")
    if intent not in ("dispatch", "reply", "run_triage", "draft_report"):
        intent = "reply"
    decision = OrchestratorDecision.model_validate({
        "intent": intent,
        "targets": result.get("targets") or [],
        "instruction": result.get("instruction") or "",
        "context_blocks": result.get("context_blocks") or [],
        "message_to_officer": result.get("message_to_officer", ""),
    })

    # Only registry skills exist. Anything else the model invented is
    # dropped, logged, and a dispatch with nothing valid left degrades to a
    # reply — never an improvised capability.
    valid_targets = [t for t in decision.targets if t in SKILLS]
    invented = set(decision.targets) - set(valid_targets)
    if invented:
        logger.warning("Orchestrator named unknown skill(s) %s — dropped", sorted(invented))
    if decision.intent == "dispatch" and not valid_targets:
        return decision.model_copy(update={
            "intent": "reply", "targets": [],
            "message_to_officer": decision.message_to_officer
            or "I couldn't map that to an available skill — could you rephrase what you'd like examined?",
        })
    return decision.model_copy(update={"targets": valid_targets})
