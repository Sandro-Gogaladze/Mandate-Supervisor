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


# ---------------------------------------------------------------------------
# The closing brief — the orchestrator's own voice at the end of the turn
# ---------------------------------------------------------------------------

CLOSING_PROMPT_ID = "ORCHESTRATOR-CLOSING"
CLOSING_SYSTEM_PROMPT = assemble(CLOSING_PROMPT_ID).effective

_CLOSING_TOOL = with_reasoning({
    "name": "record_closing_brief",
    "description": "Tell the case officer what the review came back with, in at most three sentences.",
    "input_schema": {
        "type": "object",
        "properties": {
            "message_to_officer": {
                "type": "string",
                "description": "At most three sentences. Counts exactly as given; risks in plain language; "
                               "point the officer at the findings list for the detail.",
            },
            "main_risks": {
                "type": "array", "items": {"type": "string"},
                "description": "At most three rule_id values, from the findings or hard gates you were shown, "
                               "for the risks your message names. Ids only — never invented.",
            },
        },
        "required": ["message_to_officer", "main_risks"],
    },
}, hint="What came back, what dominates it, and what the officer should look at first.")

_FOLLOW_UP_TOOL = with_reasoning({
    "name": "record_follow_up_brief",
    "description": "Answer the officer's follow-up from the completed investigation results.",
    "input_schema": {
        "type": "object",
        "properties": {
            "message_to_officer": {
                "type": "string",
                "description": "At most three plain-language sentences answering the officer's question. Use only the supplied results; say when the result is inconclusive.",
            },
        },
        "required": ["message_to_officer"],
    },
}, hint="Read the completed follow-up results, then answer the officer's question directly without adding any new claim.")


class ClosingBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reasoning: str = ""
    message: str
    main_risks: list[str] = Field(default_factory=list)
    # The counts are code's, not the model's: recorded beside the prose so a
    # reader can check the sentence against the arithmetic it describes.
    breach_count: int = 0
    disposition: str = ""


async def close_follow_up(
    question: str,
    results: list[dict],
    *,
    model=None,
    thinking_effort: str = THINKING_EFFORT,
    system_prompt: str | None = None,
) -> str:
    """Turn a completed follow-up into the supervisor's final answer.

    Unlike the review closing brief, this is not a risk recommendation: an
    investigator answer is deliberately unscored.  The model receives only
    this run's recorded outputs, after synthesis, so it cannot turn a lookup
    into an unsupported new finding.
    """
    model = model or get_model()
    bound = model.bind(
        output_config={"effort": thinking_effort},
        tools=[_FOLLOW_UP_TOOL],
        tool_choice={"type": "auto"},
    )
    response = await bound.ainvoke([
        system_message(system_prompt or CLOSING_SYSTEM_PROMPT),
        briefing_message({"question": question, "completed_results": results}, cache=False),
    ])
    log_cache_usage(response, "orchestrator_follow_up")
    message = str(get_tool_call(response, "record_follow_up_brief").get("message_to_officer") or "").strip()
    if message:
        return message

    answer = next((str(result["answer"]) for result in results if result.get("answer")), None)
    return answer or "The requested follow-up completed, but it produced no answer or assessment on the record."


def closing_summary(recommendation, findings, score=None, correlations=()) -> dict:
    """The structured close-out the orchestrator speaks from. Every number
    here is already computed — by the pure authorisation policy and the pure
    scorer — so the brief describes arithmetic rather than doing any."""
    rec = recommendation.model_dump() if hasattr(recommendation, "model_dump") else dict(recommendation)
    runs = rec.get("runs") or []
    # Several breaching assessments of one gated rule are one risk to state,
    # not three: gates are per-assessment on the record, deduplicated here.
    gates: dict[str, dict] = {}
    for gate in rec.get("hard_gates") or []:
        entry = gates.setdefault(gate["rule_id"], {"rule_id": gate["rule_id"], "reason": gate["reason"], "run_refs": []})
        entry["run_refs"] = sorted({*entry["run_refs"], *(gate.get("run_refs") or [])})
    return {
        "disposition": rec.get("disposition"),
        "policy_version": rec.get("policy_version"),
        "counts": {
            "adverse_verdicts": len(rec.get("factors") or []),
            "runs_with_a_breach": sum(r.get("verdict") == "breach" for r in runs),
            "runs_filed": len(runs),
            "clean_runs": rec.get("clean_runs"),
            "unresolved_assessments": rec.get("unresolved_assessments"),
            "rules_exercised": rec.get("rules_exercised"),
            "active_rules": rec.get("active_rules"),
        },
        "hard_gates": list(gates.values()),
        "blocked_on_evidence": rec.get("adequacy") or [],
        "risk_score": ({"total": score.total, "tier": score.tier_label}
                       if score is not None and hasattr(score, "total") else None),
        "findings": [
            {"finding_id": f.finding_id, "agent": f.agent, "type": f.type,
             "rule_id": f.rule_id, "summary": f.summary, "run_refs": list(getattr(f, "run_refs", []) or [])}
            for f in findings
        ],
        "correlations": [c.model_dump() if hasattr(c, "model_dump") else dict(c) for c in correlations],
    }


async def close_out(
    recommendation,
    findings,
    *,
    score=None,
    correlations=(),
    model=None,
    thinking_effort: str = THINKING_EFFORT,
    system_prompt: str | None = None,
) -> ClosingBrief:
    """Needs a live ANTHROPIC_API_KEY unless `model` is supplied.

    Presentational only. It reads the finished record and says what is in
    it; nothing downstream reads what it says.
    """
    payload = closing_summary(recommendation, findings, score=score, correlations=correlations)
    model = model or get_model()
    bound = model.bind(
        output_config={"effort": thinking_effort},
        tools=[_CLOSING_TOOL],
        tool_choice={"type": "auto"},
    )
    response = await bound.ainvoke([
        system_message(system_prompt or CLOSING_SYSTEM_PROMPT),
        briefing_message(payload, cache=False),
    ])
    log_cache_usage(response, "orchestrator_closing")
    result = get_tool_call(response, "record_closing_brief")

    # The same "cannot invent" rule the synthesizer is held to: a rule id it
    # names must belong to a real finding or a real gate on this case.
    real = {f.rule_id for f in findings if f.rule_id} | {g["rule_id"] for g in payload["hard_gates"]}
    named = [r for r in (result.get("main_risks") or []) if isinstance(r, str)]
    invented = [r for r in named if r not in real]
    if invented:
        logger.warning("Dropping closing-brief risk(s) naming no finding on the record: %s", invented)
    counts = payload["counts"]
    message = str(result.get("message_to_officer") or "").strip()
    if not message:
        # A brief that says nothing would be worse than the arithmetic.
        logger.warning("Closing brief came back empty; falling back to the computed counts")
        message = (f"{counts['adverse_verdicts']} adverse verdicts across "
                   f"{counts['runs_with_a_breach']} of {counts['runs_filed']} executions; "
                   f"the policy reached {payload['disposition']}. Open the findings list for the detail.")
    return ClosingBrief(
        reasoning=str(result.get("reasoning") or ""),
        message=message,
        main_risks=[r for r in named if r in real][:3],
        breach_count=counts["adverse_verdicts"],
        disposition=str(payload["disposition"] or ""),
    )
