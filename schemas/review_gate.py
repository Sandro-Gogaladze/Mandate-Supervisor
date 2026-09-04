"""The human gate's typed records (PLAN item 13).

`ReviewerDecision` is what resolves the `interrupt()` at the gate — a
*named* human's call, stamped server-side, accumulated in state (and, once
PLAN item 15 exists, anchored into the hash-chained ledger: who decided
what, when, on which report).

`ReviewerDirective` is the re-analysis instruction: unlike the machine
escalation loop (triggered by unresolved Observations, capped at 1), this
loop is human-triggered — the officer names the specialists to re-examine
and says what to look at. The instruction text is regulator-authored
(trusted-principal input, not firm text), so it may reach the specialists'
prompts as free text — the same is never true of anything firm-submitted.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .finding import FindingAgent

ReportStatus = Literal["draft", "issued", "rejected"]


class ReviewerDirective(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instructions: str = Field(min_length=1)
    target_agents: list[FindingAgent] = Field(min_length=1)
    run_scope: list[str] = Field(default_factory=list)


class ReviewerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["approve", "reject", "rerun"]
    reviewer: str = Field(min_length=1)
    comment: str | None = None
    directive: ReviewerDirective | None = None
    decided_at: str  # ISO timestamp, stamped by the gate node, not the client
