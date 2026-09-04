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
FailureRef = Annotated[str, StringConstraints(pattern=r"^[FS]\d{1,2}$")]

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
    # The reporting threshold structuring aims to stay under. A POLICY DIAL,
    # not firm data and not a constant: it is jurisdiction-specific, and it is
    # exactly the sort of number the sandbox exists to tune.
    #
    # It is also profile-specific, which is easy to miss. Set at 3000 it is
    # meaningful for a corporate procurement agent and inert for a consumer
    # shopping agent whose largest transaction ever is $867 — no split can
    # "stay under" a threshold nothing approaches. A dial set beyond an
    # agent's entire operating range is not a conservative setting, it is a
    # rule silently switched off, and the eval will read the resulting zero
    # findings as clean behaviour.
    threshold: float
    # Per agent classification, because one number cannot serve two profiles.
    # A shopping agent and a procurement agent operate an order of magnitude
    # apart; the resolved value falls back to `threshold` for classifications
    # not named here.
    threshold_by_classification: dict[str, float] = Field(default_factory=dict)
    min_cluster_size: int = 2
    window_hours: float = 24.0

    def resolve(self, classification: str | None) -> float:
        return self.threshold_by_classification.get(classification or "", self.threshold)


class BarringFlagsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Which register flags are a hard prohibition rather than information.
    # A dial only in the sense that the vocabulary is the regulator's.
    barring_flags: list[str] = Field(default_factory=lambda: ["sanctioned", "prohibited", "frozen"])


class ConcentrationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # F55: a payee the register first saw INSIDE the review window that
    # already holds this share of the latest month's spend. A dial, not a
    # fact — where "a brand-new recipient getting most of the money" starts
    # is a supervisory judgement.
    new_payee_min_share_pct: float = 20.0


class DriftBaselineParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_window_days: int = 30
    # Below this many total transactions, a baseline/comparison split
    # isn't statistically meaningful — DriftAgent.review() short-circuits
    # to insufficient_baseline=True instead of calling the model at all.
    min_total_transactions: int = 30


class MandateRiskCoverageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # The risks a mandate of this shape creates. CTL-REP-02 asks whether the
    # operator declared a control for each; a risk absent from this list is one
    # the regulator has not yet decided is mandatory, which is a policy dial.
    required_risks: list[str] = Field(default_factory=list)


class OverrideRateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Override as exception versus override as routine. Where that line sits is
    # a supervisory judgement, so it is a dial the sandbox tunes rather than a
    # constant in code.
    max_override_rate: float = 0.05
    # Below this many evaluations a "rate" is noise, not a rate.
    min_evaluations: int = 20


class CapabilityCreepParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Growth is not automatically creep — an agent that gains a function should
    # gain the capability for it. This is how much widening may happen at one
    # renewal before it needs explaining, which is a supervisory judgement and
    # therefore a dial.
    max_new_capabilities_per_reissue: int = 1


class AuditLogCoverageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # How long a stretch with no logged activity stops reading as a quiet week
    # and starts reading as a hole. A dial: the right value depends on how
    # busy the agent is meant to be.
    max_gap_days: int = 10


class RevocationStalenessParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # How old a revocation check may be before it stops counting as evidence.
    # A dial, not a fact: how fresh "current" has to be is a policy call, which
    # is exactly the kind of thing the sandbox exists to tune.
    max_age_days: int = 30


_PARAM_MODEL_BY_TYPE: dict[str, type[BaseModel]] = {
    "revocation_check_not_stale": RevocationStalenessParams,
    "every_mandate_risk_has_a_control": MandateRiskCoverageParams,
    "override_rate_within_maximum": OverrideRateParams,
    "audit_log_covers_period": AuditLogCoverageParams,
    "capability_creep_across_reissuance": CapabilityCreepParams,
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
    "counterparty_concentration_anomaly": ConcentrationParams,
    "new_payee_concentration": ConcentrationParams,
    "payee_not_on_a_barring_list": BarringFlagsParams,
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
    # The coverage-model failures this rule detects ("F42"). Declared on the
    # rule so that Control Assurance can learn from its peers by rule rather
    # than by a hand-kept map, and so an eval can read the mapping as data.
    failures: list[FailureRef] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_params_shape(self) -> "Rule":
        validated = typed_params(self)
        self.params = validated.model_dump()
        return self


class Ruleset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ruleset_id: str
    # Was a closed four-value Literal. architecture-v3 has NINE rulebooks
    # (~110 rules), so a fixed enum would need editing every time a specialist
    # gains one — the same rules-as-data argument that loosened RuleType. The
    # real safety net is the checker registry: a domain nobody has written
    # checkers for cannot have active rules.
    domain: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", max_length=32)]
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
