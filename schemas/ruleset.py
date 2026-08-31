"""Rule vocabulary for the versioned rules registry (PLAN item 2).

CLAUDE.md: "Rules are data: versioned KYA/mandate registry, never hardcoded"
and "typed rule vocabulary, human-gated promotion." A `Rule` is
{rule_id, type, params, severity_weight, ...}; `params`' shape is typed
per `type` via `_PARAM_MODEL_BY_TYPE` below rather than one subclass per
type, since most rule types (25 of 33) carry no configurable params at all
— see `typed_params()` for getting a validated params object back out.

This module defines the vocabulary only. The actual ruleset instance
(which rules are active/draft/retired, what their params are) lives in
registry/rulesets/*.json and is loaded by registry/loader.py.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RuleStatus = Literal["active", "draft", "retired"]

RuleType = Literal[
    # A. Issuer trust
    "issuer_trust_required",
    "issuer_status_active",
    "issuer_min_trust_level",
    "issuer_reaccreditation_not_stale",
    # B. Credential lifecycle
    "credential_not_expired",
    "credential_min_validity_window",
    "credential_issued_before_expiry",
    "credential_rotation_no_overlap",
    # C. Cryptographic integrity
    "signature_algorithm_allowlist",
    "signature_must_verify",
    "payload_hash_must_recompute",
    # D. Delegation chain -> human accountability
    "delegation_chain_terminates_in_human",
    "delegation_chain_no_duplicate_holders",
    "delegation_chain_max_depth",
    "delegation_entry_signatures_must_verify",
    "delegation_terminus_matches_intent_principal",
    "delegation_intermediate_agents_registered",
    "delegation_terminus_in_firm_signatory_list",
    # E. Capability / scope hygiene
    "capability_vocabulary_allowlist",
    "credential_capabilities_non_empty",
    "credential_capabilities_cover_purpose",
    "capability_creep_across_reissuance",
    # F. Consent provenance
    "consent_method_allowlist",
    # Structural anomaly
    "signer_key_not_reused_across_identities",
    "credential_id_not_reused_across_agents",
    # G. Operator firm standing
    "operator_firm_registered",
    "operator_firm_good_standing",
    "operator_firm_has_compliance_contact",
    "operator_firm_ownership_unchanged",
    # H. Agent identity/registration
    "agent_pre_registered",
    "agent_classification_declared",
    "model_version_pinned_to_mandate",
    "model_version_not_blocklisted",
    # Mandate domain: chain integrity (PLAN item 3 / ingestion).
    "cart_chain_link_matches_intent",
    "payment_chain_link_matches_cart",
    # Mandate domain: scope/cap (PLAN item 6 deterministic core). Unlike
    # KYA's rules, these mostly carry no ruleset-level params at all — the
    # "threshold" is whatever the case's own Intent declares
    # (max_transaction_amount etc.), not a regulator policy constant, so
    # there's nothing for the registry to configure beyond severity/status.
    "cart_total_within_per_transaction_cap",
    "cart_merchant_category_allowed",
    "cart_counterparty_allowed",
    "cart_merchant_geographic_scope_allowed",
    "cumulative_spend_within_monthly_cap",
    "payment_amount_matches_cart_total",
    "cart_currency_matches_scope",
    "payment_currency_matches_cart",
    "payment_authorized_within_validity_window",
    # Mandate domain: prompt-injection defense (PLAN item 6 part 2). Two
    # independent mechanisms on purpose — see agents/mandate_reasoning.py
    # module docstring: the heuristic is deterministic and runs regardless
    # of what the LLM concludes, so a manipulated semantic check doesn't
    # leave injection detection with a single point of failure.
    "cart_reasoning_matches_intent",
    "line_item_description_injection_heuristic",
    # Log domain (PLAN item 7). All three LLM-evaluated — named, scoped
    # rules (unlike KYA's open-ended ceiling), backed by pre-computed
    # statistics/candidate clusters rather than raw judgment or a
    # hardcoded Python verdict. See agents/log_reasoning.py.
    "transaction_structuring_detected",
    "counterparty_concentration_anomaly",
    "transaction_velocity_anomaly",
    # Drift domain (PLAN item 8). Same reasoning as Log: PSI/z-score/
    # frequency statistics are computed deterministically
    # (agents/drift_stats.py), but whether a shift constitutes meaningful
    # drift is the model's judgment, not a threshold comparison. See
    # agents/drift_reasoning.py.
    "behavioral_drift_detected",
]


class NoParams(BaseModel):
    """Param shape for rule types that need no configuration."""

    model_config = ConfigDict(extra="forbid")


class IssuerMinTrustLevelParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_trust_level: Literal["primary", "recognized"]


class CredentialNotExpiredParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grace_period_days: int = 0


class CredentialMinValidityWindowParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_validity_days: int


class SignatureAlgorithmAllowlistParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_algs: list[str]


class DelegationMaxDepthParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_depth: int


class CapabilityVocabularyAllowlistParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_prefixes: list[str] = Field(default_factory=list)
    allowed_exact: list[str] = Field(default_factory=list)


class IssuerReaccreditationNotStaleParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_reaccreditation_age_days: int


class ConsentMethodAllowlistParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_methods: list[str]


class AmountToleranceParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Absolute currency-unit slack for float rounding — e.g. 0.01 allows a
    # one-cent difference between Payment.amount and Cart.cart_total
    # without flagging it. Not a policy leniency knob.
    tolerance: float = 0.01


class StructuringDetectionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # A synthetic reporting-flag threshold for this demo, not a real AML
    # figure (docs/phases/01-synthetic-data.md §3) — case-005's own
    # SR-STRUCT-01 value is 3000.
    threshold: float
    min_cluster_size: int = 2
    window_hours: float = 24.0


class DriftBaselineParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_window_days: int = 30
    # Below this many total transactions, a baseline/comparison split
    # isn't statistically meaningful — DriftAgent.review() short-circuits
    # to insufficient_baseline=True instead of calling the model at all.
    min_total_transactions: int = 30


_PARAM_MODEL_BY_TYPE: dict[str, type[BaseModel]] = {
    "issuer_min_trust_level": IssuerMinTrustLevelParams,
    "issuer_reaccreditation_not_stale": IssuerReaccreditationNotStaleParams,
    "credential_not_expired": CredentialNotExpiredParams,
    "credential_min_validity_window": CredentialMinValidityWindowParams,
    "signature_algorithm_allowlist": SignatureAlgorithmAllowlistParams,
    "payment_amount_matches_cart_total": AmountToleranceParams,
    "delegation_chain_max_depth": DelegationMaxDepthParams,
    "capability_vocabulary_allowlist": CapabilityVocabularyAllowlistParams,
    "consent_method_allowlist": ConsentMethodAllowlistParams,
    "transaction_structuring_detected": StructuringDetectionParams,
    "behavioral_drift_detected": DriftBaselineParams,
}


def typed_params(rule: "Rule") -> BaseModel:
    """The validated params object for `rule`, typed per its `type`."""
    model = _PARAM_MODEL_BY_TYPE.get(rule.type, NoParams)
    return model.model_validate(rule.params)


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    type: RuleType
    version: int
    status: RuleStatus
    effective_from: str
    # Consumed by scoring (PLAN item 11); a pure weighted-factor function
    # reads this straight off the rule that produced each finding.
    severity_weight: float = Field(ge=0.0, le=1.0)
    # The Finding.type this rule produces when triggered — lets a finding
    # cite a specific rule_id/version (drafting-agent grounding).
    finding_type: str
    description: str
    # Why a draft rule can't be promoted yet, or any other rationale worth
    # keeping next to the rule instead of in a commit message.
    notes: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_params_shape(self) -> "Rule":
        validated = typed_params(self)
        self.params = validated.model_dump()
        return self


class Ruleset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ruleset_id: str
    domain: Literal["kya", "mandate", "log", "drift"]
    version: str
    as_of: str
    description: str
    rules: list[Rule]

    @model_validator(mode="after")
    def _validate_rule_ids_unique(self) -> "Ruleset":
        ids = [r.rule_id for r in self.rules]
        if len(ids) != len(set(ids)):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"duplicate rule_id(s) in ruleset: {dupes}")
        return self
