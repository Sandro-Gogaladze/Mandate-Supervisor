"""Typed finding — CLAUDE.md cross-cutting rule 2: "every agent returns a
typed Finding, never a print statement or loose dict."

Ingestion (this phase) is the first producer: a broken chain or a bad
signature must turn into a Finding, not an exception. `agent` attributes a
finding to whichever specialist domain owns that concern (matching the
corpus's own ground truth in data/corpus_manifest.json) even when, as here,
the check actually ran deterministically during ingestion before that
specialist was ever dispatched.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FindingAgent = Literal["mandate", "kya", "log", "drift"]


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str
    case_id: str
    agent: FindingAgent
    type: str
    # The registry rule that produced this, if any — lets a finding cite a
    # specific rule_id/version (drafting-agent grounding, PLAN item 12).
    rule_id: str | None = None
    severity_weight: float | None = None
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
