"""The Orchestrator's propose-enforce dispatch plan (PLAN item 9).

CLAUDE.md: "Propose–enforce: LLM proposes a DispatchPlan, a deterministic
validator enforces a mandatory floor (Mandate+KYA always run; Log+Drift
run when history >= 30 tx)." `DispatchPlan` is the LLM's proposal;
`pipeline/dispatch.py::enforce_floor()` is the deterministic validator —
it can only ever turn a `False` into `True` (add a specialist the LLM
didn't propose but the floor requires), never the reverse. The LLM cannot
skip a mandatory specialist by proposing not to run it.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DispatchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_mandate: bool
    run_kya: bool
    run_log: bool
    run_drift: bool
    reasoning: str


class DispatchRecord(BaseModel):
    """One agent briefing, recorded in full (architecture-v2 §10.5's
    `dispatch_recorded` — the event this architecture exists to make
    possible). `context_blocks` is the verbatim payload the agent received —
    the answer to "what did the orchestrator give to whom"; `context_digest`
    is its SHA-256 so two runs can be compared cheaply. `instruction` is any
    steering text appended to the agent's own system prompt (an escalation
    addendum, a reviewer directive, an orchestrator briefing) — empty string
    when the agent ran on its canonical brief alone."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    run_id: str
    target: str          # agent name: mandate | kya | log | drift | investigator
    skill: str           # skill_id from agents/skills.py
    instruction: str
    context_blocks: dict
    context_digest: str
