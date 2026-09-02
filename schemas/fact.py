"""A `Fact` — what an agent's deterministic `check()` establishes.

architecture-v3 Part I: "determinism establishes facts, agents establish
meaning." A check does not produce a verdict; it produces something true,
reproducible and cheap:

    "Cart total 1289.0 exceeds the per-transaction cap 350.0 by 939.0"

Nothing there says whether it was deliberate, what it connects to, or how
serious it is for this firm. That is the agent's job, and it happens in the
same pass — `check()` then `reason()` — but the two outputs stay separate
types so the audit trail can always show which half is mechanical.

Two `kind`s carry the load:

- **rule outcome** (`breach` / `satisfied` / `absent`) — a computable rule
  was evaluated. `satisfied` is not noise: it is how a clean case becomes
  provably clean rather than merely silent, and it is what gives the eval
  harness true negatives, without which a false-positive rate cannot be
  computed at all.
- **measurement** — deterministic computation standing behind a *judged*
  rule. Log's rules are all model-judged, so without measurements its
  `check()` would emit nothing and its model would be reasoning over raw
  rows. Every judged rule has measurements behind it; that is the contract,
  and agents/critic.py checks assessments against them.

`absent` means a rule could not be evaluated — almost always because the
firm did not submit the block it needs. That rolls up into a data-gap
finding, because a firm that cannot produce a field has told you something.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FactKind = Literal["breach", "satisfied", "measurement", "absent"]

AbsentReason = Literal[
    "missing_block",          # the firm did not submit the evidence this rule needs
    "insufficient_history",   # e.g. Drift below its baseline minimum
    "out_of_scope",           # the rule does not apply to this case shape
    "rule_draft",             # the rule exists but is not active in this ruleset version
]


class EvidenceRef(BaseModel):
    """A structured pointer to what a claim rests on.

    Prose evidence ("cluster sum 8700.0 vs threshold 3000.0") cannot be
    resolved by anything downstream: the UI cannot link to it, the critic can
    only regex numbers out of it, and a report cannot cite it. A ref can be
    checked mechanically, which is what makes agents/critic.py a real
    grounding check rather than a heuristic.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["transaction", "line_item", "credential_field", "statistic", "rule", "registry"]
    ref: str          # "TXN-2026-0142" | "cart.line_items[0]" | "counterparty_mix_psi"
    value: Any = None  # the value as the agent saw it — what the critic compares against


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str
    case_id: str
    domain: str                      # the ruleset that produced it: "kya", "mandate", ...
    rule_id: str | None = None       # None only for measurements with no single owning rule
    kind: FactKind
    statement: str                   # one sentence, readable by a human without context
    values: dict[str, Any] = Field(default_factory=dict)
    refs: list[EvidenceRef] = Field(default_factory=list)
    absent_reason: AbsentReason | None = None

    @model_validator(mode="after")
    def _absent_reason_iff_absent(self) -> "Fact":
        if self.kind == "absent" and self.absent_reason is None:
            raise ValueError(
                f"{self.fact_id}: kind='absent' requires absent_reason — an unexplained "
                f"gap is indistinguishable from not having looked"
            )
        if self.kind != "absent" and self.absent_reason is not None:
            raise ValueError(f"{self.fact_id}: absent_reason is only valid when kind='absent'")
        return self

    @model_validator(mode="after")
    def _rule_outcomes_cite_a_rule(self) -> "Fact":
        if self.kind in ("breach", "satisfied", "absent") and not self.rule_id:
            raise ValueError(
                f"{self.fact_id}: kind={self.kind!r} is a rule outcome and must name its rule_id"
            )
        return self
