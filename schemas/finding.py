"""Typed finding — CLAUDE.md cross-cutting rule 2: "every agent returns a
typed Finding, never a print statement or loose dict."

Since migration-plan.md Phase 1 a Finding is a PROJECTION of an Assessment
(agents/assess.py::project_finding), not something an agent produces
directly: checkers produce `Fact`s, agents turn facts into `Assessment`s,
and this is the view of an assessment that scoring, the ledger's
`finding_recorded` event and the report consume. `finding_id` is the
assessment id, so a re-derived assessment is the same finding to the state
reducer and the ledger. `agent` attributes it to the specialist domain that
owns the concern. Ingestion's cryptographic checks still mint Findings
directly until Phase 2 moves them onto the fact contract.
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
