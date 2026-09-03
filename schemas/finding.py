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

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# Was a closed four-value Literal. architecture-v3 has eleven specialists, so
# the enum would need editing every time one lands — and the real constraint is
# that a Finding names an agent that actually ran, which the dispatcher already
# enforces. Same argument as RuleType and Ruleset.domain.
FindingAgent = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", max_length=32)]


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
