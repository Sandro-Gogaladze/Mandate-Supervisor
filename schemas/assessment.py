"""An `Assessment` — an agent's meaning, attached to facts.

architecture-v3 Part VII. Where a `Fact` is mechanical, an Assessment is
judgment: this breach reads as deliberate, this one is explained by context,
this pattern is worse than the sum of its parts.

Four verdicts, and two of them are new capabilities rather than renames:

- `breach`       — a supervisory concern. The only verdict that scores.
- `concern`      — worth the officer's attention, below the bar for a breach.
- `explained`    — a rule tripped and, in context, it is fine. **"We looked
                   and it's fine" has to be distinguishable from "we didn't
                   look"**, and in v2 it wasn't: a passing case was silent.
- `inconclusive` — the rule applies, the agent evaluated it, and cannot
                   decide. In v2 this had to lie in one direction. It scores
                   nothing, routes to a human, and replaces the
                   unresolved-Observation escalation trigger.

**Severity is propose-enforce, applied to weight.** The floor comes from the
ruleset and is deterministic — same facts, same floor, always. An agent may
raise it, never lower it, and must say why. Both totals are shown, so
"explainable, factor-level scoring" stays literally true (the floor is a
printable derivation from rules and weights) while an agent can still say
"four detectors converged on one injected line item; as coordinated
manipulation this is materially worse than the sum." The validator below is
what makes "never lower" a guarantee rather than an instruction.

`supersedes` is how an iterative review changes its mind. Round 1 finds an
unapproved counterparty; round 3, given context, establishes it is the
approved supplier's disclosed subsidiary. **Both stay on the ledger** — the
projection marks the earlier one superseded, scoring reads only current
assessments, and the audit trail shows the case changing its mind and why.
Nothing is ever edited in place; append-only is untouched.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .fact import EvidenceRef

Verdict = Literal["breach", "concern", "explained", "inconclusive"]
Confidence = Literal["certain", "probable", "possible"]

# Only a breach contributes to the risk score. Everything else is recorded,
# surfaced and citable, but priced at nothing — which is what keeps the score
# a function of supervisory concerns rather than of activity.
SCORING_VERDICTS: frozenset[str] = frozenset({"breach"})

# Multiplies the severity when scoring. Rules-as-data would be better long
# term (registry/scoring.json), but these are the defaults the pure function
# in pipeline/scoring.py uses when the config omits them.
CONFIDENCE_FACTOR: dict[str, float] = {"certain": 1.0, "probable": 0.7, "possible": 0.4}


class Assessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment_id: str
    case_id: str
    round: int = 1
    scope: Literal["case", "portfolio"] = "case"

    agent: str
    skill_id: str | None = None
    rule_id: str | None = None       # None for a judgment that isn't rule-backed
    ruleset_version: str | None = None

    # What this rests on. agents/critic.py resolves every id against the
    # facts the agent was actually given — an assertion with no fact behind
    # it is the failure mode this exists to make detectable.
    fact_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)

    verdict: Verdict
    confidence: Confidence = "certain"

    severity_floor: float = Field(ge=0.0, le=1.0, default=0.0)
    severity_assessed: float = Field(ge=0.0, le=1.0, default=0.0)
    severity_rationale: str | None = None

    subject: str | None = None            # the sku / transaction / counterparty it is about
    subject_refs: list[str] = Field(default_factory=list)  # case ids, for portfolio scope
    narrative: str

    supersedes: str | None = None

    @model_validator(mode="after")
    def _severity_never_below_floor(self) -> "Assessment":
        """The guarantee, in code rather than in a prompt."""
        if self.severity_assessed < self.severity_floor:
            raise ValueError(
                f"{self.assessment_id}: severity_assessed {self.severity_assessed} is below the "
                f"ruleset floor {self.severity_floor}. An agent may argue a finding up, never down."
            )
        return self

    @model_validator(mode="after")
    def _escalation_needs_a_reason(self) -> "Assessment":
        if self.severity_assessed > self.severity_floor and not self.severity_rationale:
            raise ValueError(
                f"{self.assessment_id}: severity was raised above the floor without a rationale. "
                f"An unexplained escalation is not reviewable."
            )
        return self

    @model_validator(mode="after")
    def _assertions_rest_on_facts(self) -> "Assessment":
        """A scoring verdict with no fact behind it cannot be checked by the
        critic and cannot be defended to a firm."""
        if self.verdict in SCORING_VERDICTS and not self.fact_ids:
            raise ValueError(
                f"{self.assessment_id}: verdict={self.verdict!r} must cite at least one fact_id"
            )
        return self

    @model_validator(mode="after")
    def _portfolio_scope_names_its_cases(self) -> "Assessment":
        if self.scope == "portfolio" and not self.subject_refs:
            raise ValueError(
                f"{self.assessment_id}: portfolio scope must list the case ids it spans "
                f"in subject_refs"
            )
        return self

    @property
    def scores(self) -> bool:
        return self.verdict in SCORING_VERDICTS

    def weighted(self, *, use_assessed: bool = True) -> float:
        """Contribution to the risk score. `use_assessed=False` gives the
        floor-only total — the printable derivation from rules and weights
        alone, shown alongside the assessed total so a firm can see both."""
        if not self.scores:
            return 0.0
        severity = self.severity_assessed if use_assessed else self.severity_floor
        return round(severity * CONFIDENCE_FACTOR[self.confidence], 4)


class ControlPosture(BaseModel):
    """Control Assurance's output — the second axis on a finding.

    "Cap exceeded" is a fact about a payment. "Cap exceeded, and the firm's
    own GEL 500 control was present and bypassed by an operator override" is
    a supervisory fact about the firm, and it is the one that supports
    action. `absent` is emitted with no breach attached: a firm that declared
    no control for a risk its own mandate creates has a governance failure
    whether or not anything has gone wrong yet.
    """

    model_config = ConfigDict(extra="forbid")

    case_id: str
    assessment_id: str | None = None      # None for a pure coverage finding (CTL-REP-02)
    control_id: str | None = None         # None when posture is "absent"
    posture: Literal["absent", "failed", "bypassed", "ineffective", "effective"]
    override_by: str | None = None
    override_reason: str | None = None
    narrative: str

    @model_validator(mode="after")
    def _bypassed_names_who(self) -> "ControlPosture":
        if self.posture == "bypassed" and not self.override_by:
            raise ValueError(
                f"{self.case_id}: posture='bypassed' must name who overrode the control — "
                f"an anonymous override is not a supervisable fact"
            )
        return self
