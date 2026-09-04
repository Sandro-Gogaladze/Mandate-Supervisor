"""What the orchestrator decided for one turn, and one specialist's briefing.

`DispatchPlan` is the orchestrator's own act on the record: which skills it
briefed, what it told each, which runs it scoped them to, and — on a first
pass — which review skills it left out. Coverage is the orchestrator's to
decide and the record's to show; nothing is added behind its back. The model
is lenient on read so the boolean plans of the four-specialist era still
project from older ledgers.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DispatchPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reasoning: str = ""
    intent: str = "dispatch"                     # dispatch | reply | draft_report
    first_pass: bool = False
    skills: list[str] = Field(default_factory=list)
    briefings: dict[str, str] = Field(default_factory=dict)          # skill -> what it was asked
    run_scope: dict[str, list[str]] = Field(default_factory=dict)    # skill -> runs; absent = whole dossier
    context_blocks: dict[str, list[str]] = Field(default_factory=dict)
    not_dispatched: list[str] = Field(default_factory=list)          # first pass: review skills left out
    message_to_officer: str = ""


class DispatchRecord(BaseModel):
    """One agent briefing, recorded in full (architecture-v2 §10.5's
    `dispatch_recorded` — the event this architecture exists to make
    possible). `context_blocks` is the verbatim payload the agent received —
    the answer to "what did the orchestrator give to whom"; `context_digest`
    is its SHA-256 so two runs can be compared cheaply. `instruction` is any
    steering text appended to the agent's own system prompt (the
    orchestrator's briefing, an escalation addendum, a reviewer directive) —
    empty string when the agent ran on its canonical brief alone."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    run_id: str
    target: str          # agent name
    skill: str           # skill_id from agents/skills.py
    instruction: str
    context_blocks: dict
    context_digest: str
