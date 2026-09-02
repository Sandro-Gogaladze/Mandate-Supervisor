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

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

RuleStatus = Literal["active", "draft", "retired"]

# Rule `type` is the key a checker function is registered under. It was a
# closed Literal through v2026.1, which worked at 33 rules in two domains and
# stops working at ~110 across nine: every new rule in any domain would edit
# this shared schema file, which is the opposite of rules-as-data.
#
# The real safety net is the checker registry, not this type. An ACTIVE
# computable rule whose type has no registered checker raises
# NotImplementedError at evaluation (agents/*_checks.py::run_policy_checks) —
# a loud failure, and the one that actually matters. What remains here is a
# shape check that catches typos and casing drift.
RuleType = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", min_length=3, max_length=80),
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


Evaluation = Literal["computable", "judged"]


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    type: RuleType
    version: int
    status: RuleStatus
    effective_from: str
    # architecture-v3 Part I·5: how this rule is evaluated, declared on the
    # rule rather than inferred from the agent. `computable` runs in the
    # owning agent's check() — plain functions, no model. `judged` can only
    # be evaluated by that agent's reasoning pass, over the measurements
    # check() produced for it.
    #
    # Defaults to computable because most rules are, and because a judged
    # rule that forgot to say so fails loudly: the checker registry has no
    # function for it and run_policy_checks() raises NotImplementedError
    # rather than skipping it silently.
    evaluation: Evaluation = "computable"
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
    def _validate_rule_types_unique(self) -> "Ruleset":
        """Two rules sharing a type both resolve to one checker, so one of
        them silently never fires. Loud at load time instead."""
        types = [r.type for r in self.rules]
        if len(types) != len(set(types)):
            dupes = sorted({t for t in types if types.count(t) > 1})
            raise ValueError(f"duplicate rule type(s) in {self.ruleset_id}: {dupes}")
        return self

    @model_validator(mode="after")
    def _validate_rule_ids_unique(self) -> "Ruleset":
        ids = [r.rule_id for r in self.rules]
        if len(ids) != len(set(ids)):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"duplicate rule_id(s) in ruleset: {dupes}")
        return self
