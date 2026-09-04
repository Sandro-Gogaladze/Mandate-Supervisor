"""The orchestrator — one voice, one job, every turn.

A dispatcher that speaks, never an analyst. Every request after the initial
review is answered by deciding which specialist skills to run, briefing each
one, and reporting what came back. The first pass itself is fixed policy,
not a semantic routing problem: code dispatches every review skill without
spending a model call. Later requests use a forced-shape routing tool; there
is no field in which it could state a verdict of its own about the firm.

It names skills from the registry and record items by id; code resolves
both. Unknown skills and run ids are dropped and logged; a dispatch with
nothing valid left degrades to a reply. Control Assurance is never
dispatched by it — the graph runs that after the peers, because CTL-EFF-01
needs their findings. The deterministic first-pass plan is still recorded,
so its coverage remains visible on the ledger.
"""
from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ledger.projection import CaseRecord
from .llm import (
    briefing_message, get_model, get_tool_call, log_cache_usage, system_message,
    THINKING_EFFORT, with_reasoning,
)
from .prompts import assemble
from .skills import REVIEW_SKILLS, SKILLS, SPECIALIST_SKILLS_BY_AGENT, skill_catalog

logger = logging.getLogger(__name__)

PROMPT_ID = "ORCHESTRATOR"
SYSTEM_PROMPT = assemble(PROMPT_ID).effective

# What the officer is taken to have asked when they press "Run review".
FIRST_PASS_REQUEST = "Run the full first-pass review of this dossier."

_ROUTE_TOOL = with_reasoning({
    "name": "route_supervisor_request",
    "description": "Answer the officer's request: dispatch skills with a briefing each, reply from the record, or start the report.",
    "input_schema": {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": ["dispatch", "reply", "draft_report"]},
            "message_to_officer": {
                "type": "string",
                "description": "What you are setting in motion and why, or the reply itself. Plain sentences; name skills and ids.",
            },
            "dispatches": {
                "type": "array",
                "description": "One entry per skill you are running. Empty for a reply.",
                "items": {
                    "type": "object",
                    "properties": {
                        "skill": {"type": "string", "description": "A skill_id from available_skills."},
                        "instruction": {
                            "type": "string",
                            "description": "The briefing for this specialist: what to weigh on this dossier, what the officer's question means for its domain, what would matter most if found.",
                        },
                        "run_scope": {
                            "type": "array", "items": {"type": "string"},
                            "description": "Execution run ids to scope this specialist to; empty means the whole dossier. Only ids on the record.",
                        },
                        "context_blocks": {
                            "type": "array", "items": {"type": "string"},
                            "description": "Record items to attach verbatim: finding:<id>, assessment:<id>, answer:<question_id>, observation:<n>, score, correlations.",
                        },
                    },
                    "required": ["skill", "instruction"],
                },
            },
        },
        "required": ["intent", "message_to_officer", "dispatches"],
    },
}, hint=("Your working, in full, before you decide: what the request asks for, what the record shows, which "
         "skills answer it and what each needs to be told. Write it as you would think it."))


class Dispatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill: str
    instruction: str = ""
    run_scope: list[str] = Field(default_factory=list)
    context_blocks: list[str] = Field(default_factory=list)


class OrchestratorDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reasoning: str = ""
    # "dispatch" and "reply" resolve inside the review run; "draft_report" is
    # a routing decision the CALLER executes (the console starts that run) —
    # the orchestrator still only routes, it never runs anything itself.
    intent: Literal["dispatch", "reply", "draft_report"]
    message_to_officer: str
    dispatches: list[Dispatch] = Field(default_factory=list)
    # The tool reply exactly as the model returned it, before validation —
    # on the record so "what it said" and "what was accepted" can be compared.
    raw: dict | None = None

    @property
    def targets(self) -> list[str]:
        return [d.skill for d in self.dispatches]

    @property
    def instruction(self) -> str:
        return next((d.instruction for d in self.dispatches if d.instruction), "")

    @property
    def context_blocks(self) -> list[str]:
        return sorted({b for d in self.dispatches for b in d.context_blocks})

    @property
    def run_scope(self) -> list[str]:
        return sorted({r for d in self.dispatches for r in d.run_scope})


def first_pass_decision() -> OrchestratorDecision:
    """Return the policy-defined initial fan-out without an LLM call.

    Specialists still make their normal model-backed judgments. Only the
    redundant routing decision is made deterministic.
    """
    return OrchestratorDecision(
        reasoning="The first-pass policy requires every review skill.",
        intent="dispatch",
        message_to_officer="Running the complete first-pass review.",
        dispatches=[Dispatch(skill=skill) for skill in REVIEW_SKILLS],
    )


def record_summary(record: CaseRecord) -> dict:
    """The structured record the orchestrator reasons over — findings,
    observations, answers, score. Our own agents' typed output, never the
    raw firm submission."""
    return {
        "case_id": record.case_id,
        "execution_runs": sorted({f.run_ref for f in record.facts if f.run_ref}),
        "facts": [{"fact_id": f.fact_id, "rule_id": f.rule_id, "kind": f.kind,
                   "run_ref": f.run_ref, "statement": f.statement} for f in record.facts
                  if f.kind in ("breach", "absent")],
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


def _catalogue() -> list[dict]:
    return [
        {"skill_id": s.skill_id, "agent": s.agent, "produces": s.produces, "description": s.description,
         "first_pass": s.skill_id in REVIEW_SKILLS,
         "runs_after_the_others": s.agent == "control_assurance"}
        for s in skill_catalog()
    ]


async def route(
    officer_message: str,
    record: CaseRecord,
    *,
    first_pass: bool = False,
    known_runs: set[str] | frozenset[str] | None = None,
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
        "request": officer_message,
        "first_pass": first_pass,
        "case_record": record_summary(record),
        "available_skills": _catalogue(),
    }
    messages = [
        # The system prompt and the route tool are the same bytes on every
        # turn of every case, so they are a cache breakpoint. The payload is
        # not: it carries the officer's request and a record that changes
        # each turn, and a breakpoint after volatile bytes only ever pays
        # the write premium.
        system_message(system_prompt or SYSTEM_PROMPT),
        briefing_message(payload, cache=False),
    ]
    response = await bound.ainvoke(messages)
    log_cache_usage(response, "orchestrator")

    result = get_tool_call(response, "route_supervisor_request")
    intent = result.get("intent", "reply")
    dispatches = list(result.get("dispatches") or [])
    if not dispatches and result.get("targets"):
        # The earlier shape: one instruction for a list of targets.
        dispatches = [{"skill": t, "instruction": result.get("instruction") or "",
                       "run_scope": result.get("run_scope") or [], "context_blocks": result.get("context_blocks") or []}
                      for t in result.get("targets") or []]
    if intent == "run_triage":
        # The old fourth intent: the request IS a first pass.
        intent = "dispatch"
        dispatches = dispatches or [{"skill": s, "instruction": ""} for s in REVIEW_SKILLS]
    if intent not in ("dispatch", "reply", "draft_report"):
        intent = "reply"

    clean: list[Dispatch] = []
    seen: set[str] = set()
    dropped: list[str] = []
    for raw in dispatches or []:
        if not isinstance(raw, dict):
            continue
        skill = raw.get("skill") or raw.get("skill_id") or raw.get("agent")
        # An agent's name stands for its one skill: "log" means log.analyze.
        skill = SPECIALIST_SKILLS_BY_AGENT.get(skill, skill) if skill not in SKILLS else skill
        if skill == "investigator":
            skill = "investigator.lookup"
        if skill in seen:
            continue
        if skill not in SKILLS:
            logger.warning("Orchestrator named unknown skill %r — dropped", skill)
            dropped.append(str(skill))
            continue
        if SKILLS[skill].agent == "control_assurance":
            logger.info("Orchestrator named control_assurance; it runs after the peers by construction")
            continue
        scope = [r for r in (raw.get("run_scope") or []) if isinstance(r, str)]
        if known_runs is not None:
            invented = [r for r in scope if r not in known_runs]
            if invented:
                logger.warning("Orchestrator scoped to run(s) not on the record %s — dropped", invented)
            scope = [r for r in scope if r in known_runs]
        seen.add(skill)
        clean.append(Dispatch(skill=skill, instruction=str(raw.get("instruction") or ""), run_scope=scope,
                              context_blocks=[b for b in (raw.get("context_blocks") or []) if isinstance(b, str)]))

    message = str(result.get("message_to_officer") or "")
    if intent == "dispatch" and not clean:
        # Nothing it named exists. Say so — a message that still reads
        # "dispatching X" over an empty dispatch would be a lie on the record.
        why = (f"{', '.join(dropped)} is not an available skill" if dropped
               else "it named no skill from the catalogue")
        return OrchestratorDecision(
            reasoning=str(result.get("reasoning") or ""), intent="reply", dispatches=[], raw=dict(result),
            message_to_officer=f"I could not dispatch what I intended: {why}. "
                               + (message or "Could you rephrase what you would like examined?"),
        )
    return OrchestratorDecision(reasoning=str(result.get("reasoning") or ""), intent=intent, raw=dict(result),
                                message_to_officer=message, dispatches=clean if intent == "dispatch" else [])
