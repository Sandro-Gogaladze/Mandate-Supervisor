"""The bounded, typed evidence handed to the KYA reasoning pass."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .fact import Fact


class KYAResultSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    counts: dict[str, int] = Field(default_factory=dict)
    fact_ids: list[str] = Field(default_factory=list)
    run_refs: list[str] = Field(default_factory=list)


class KYAEvidenceBundle(BaseModel):
    """Whole-dossier, KYA-scoped projection; never ground truth or raw noise."""

    model_config = ConfigDict(extra="forbid")

    bundle_type: str = "kya_evidence_bundle"
    case_id: str
    review_scope: dict[str, Any]
    agent_id: str
    operator_id: str
    ruleset: dict[str, Any]
    failure_catalogue_version: str

    rule_inventory: list[dict[str, Any]] = Field(default_factory=list)
    rule_results: list[KYAResultSummary] = Field(default_factory=list)
    attention_facts: list[Fact] = Field(default_factory=list)

    agent_registry_record: dict[str, Any] | None = None
    operator_registry_record: dict[str, Any] | None = None
    issuer_registry_record: dict[str, Any] | None = None
    blocked_model_records: list[dict[str, Any]] = Field(default_factory=list)
    credential: dict[str, Any]
    credential_history: list[dict[str, Any]] = Field(default_factory=list)
    activity_summary: dict[str, Any]
    run_identity_evidence: list[dict[str, Any]] = Field(default_factory=list)

    # Compatibility/readability rollups used by prompts and tests.
    registered_classification: Any = None
    registered_risk_class: Any = None
    declared_purpose: Any = None
    purpose_categories: list[str] = Field(default_factory=list)
    runs: int
    already_flagged_by_fixed_rules: list[str] = Field(default_factory=list)
    rule_outcomes: dict[str, dict[str, int]] = Field(default_factory=dict)
