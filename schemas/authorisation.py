from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

Disposition = Literal["authorise", "monitor", "refuse", "incomplete-submission"]


class AuthorisationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reviewer: str = Field(min_length=2, max_length=120)
    disposition: Disposition
    rationale: str = Field(min_length=10, max_length=5000)
    conditions: list[str] = Field(default_factory=list)
    recommendation_digest: str


class AuthorisationRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dossier_id: str
    disposition: Disposition
    policy_version: str
    policy_status: str
    policy_digest: str
    recommendation_digest: str = ""
    evidence_digest: str = ""
    hard_gates: list[dict] = Field(default_factory=list)
    adequacy: list[dict] = Field(default_factory=list)
    factors: list[dict] = Field(default_factory=list)
    runs: list[dict] = Field(default_factory=list)
    rules_exercised: int
    active_rules: int
    rule_coverage: float
    target_runs: int
    clean_runs: int
    unresolved_assessments: int
    weight_per_run: float
    conditions: list[str] = Field(default_factory=list)
    basis_assessment_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=lambda: [
        "Prototype thresholds have not been calibrated to a regulatory population.",
        "Model identity is self-attested; a valid signature establishes integrity, not truth.",
        "The filed index cannot prove that executions omitted before filing never occurred."])
