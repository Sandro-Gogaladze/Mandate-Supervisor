"""The investigator's typed output (architecture-v2 §16).

An InvestigationAnswer is deliberately NOT a Finding and NOT an input to the
drafting agent: the investigator has no rule behind it, so its conclusions
are unscored, uncitable answers to a named human's question — plus the full
tool-call trail, so "how did it reach that conclusion" is answerable from
the ledger. If the supervisor wants an investigation's insight turned into a
scored finding, she dispatches a *specialist*; the rule decides.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolCallRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    # sha256 of the canonical result JSON — the audit trail can prove what
    # the tool returned without storing every (possibly large) result body.
    result_digest: str


class InvestigationAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    question_id: str
    question: str
    answer: str
    cited_evidence: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
