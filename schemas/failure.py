"""Versioned failure catalogue entries and concrete detected occurrences.

Rules say how a condition is tested.  Failure definitions say which stable
supervisory failure (F1--F73) that condition represents.  An occurrence is
the auditable join between the two: it names the failure, the rule and
ruleset version, the assessment, every supporting fact and every affected
execution run.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated

from .fact import EvidenceRef

FailureId = Annotated[str, StringConstraints(pattern=r"^F(?:[1-9]|[1-6][0-9]|7[0-3])$")]


class FailureDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_id: FailureId
    name: str
    domain: str
    phase: Literal["P0", "P1", "P2", "P3", "P4", "P5", "P6", "X1"]
    default_scope: Literal["run", "run_set", "case", "portfolio"]


class FailureCatalogue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalogue_id: str
    version: str
    as_of: str
    failures: list[FailureDefinition]


class FailureOccurrence(BaseModel):
    """One rule-backed failure conclusion, suitable for UI/API/report use."""

    model_config = ConfigDict(extra="forbid")

    occurrence_id: str
    case_id: str
    failure_id: FailureId
    failure_name: str
    catalogue_version: str
    domain: str

    # Systemic F57/F67/F69 are portfolio detectors rather than per-firm
    # registry rules, so they cite their assessment/facts with no fake rule.
    rule_id: str | None = None
    ruleset_version: str | None = None
    assessment_id: str
    status: Literal["detected", "possible", "contained", "not_evaluable"]
    confidence: Literal["certain", "probable", "possible"]
    scope: Literal["run", "run_set", "case", "portfolio"]

    run_refs: list[str] = Field(default_factory=list)
    run_refs_by_case: dict[str, list[str]] = Field(default_factory=dict)
    transaction_refs: list[str] = Field(default_factory=list)
    case_refs: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    summary: str
