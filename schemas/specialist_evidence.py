"""Common evidence contract attached to every specialist briefing."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

class RuleResultIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    counts: dict[str, int] = Field(default_factory=dict)
    fact_ids: list[str] = Field(default_factory=list)
    run_refs: list[str] = Field(default_factory=list)


class SpecialistEvidenceContract(BaseModel):
    """The invariant part of every domain-specific evidence bundle."""

    model_config = ConfigDict(extra="forbid")

    contract_version: str = "2026.1"
    case_id: str
    specialist: str
    skill_id: str
    review_scope: dict[str, Any]
    ruleset: dict[str, Any] | None = None
    failure_catalogue_version: str
    rule_inventory: list[dict[str, Any]] = Field(default_factory=list)
    rule_results: list[RuleResultIndex] = Field(default_factory=list)
    # Prompt-safe Fact projections. Potentially firm/merchant-authored text
    # is preserved but explicitly delimited by agents/evidence_bundle.py.
    attention_facts: list[dict[str, Any]] = Field(default_factory=list)
