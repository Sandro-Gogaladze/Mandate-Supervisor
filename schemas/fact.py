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

`absent` means a rule could not be evaluated, and the reason is required
because the reasons call for different responses: the firm did not submit
the block (`missing_block`) is a data-gap finding against the submission;
the rule does not apply to this shape (`out_of_scope`) is nothing at all;
the regulator's own register has no record (`no_registry_record`) is a
question for the regulator, not the firm. Collapsing them into silence —
which is what a checker returning `None` did — made "we checked and it was
fine" indistinguishable from "we could not look."

**Scope.** A dossier is one agent and many runs. A rule about a run (was this
cart within this shopper's cap) produces one fact per run, carrying
`run_ref`; a rule about the agent or the submission (does the delegation
chain end in a human) produces one fact with no `run_ref`. The run list in
the console and per-run precision/recall in the eval both read this field,
which is why it is on the fact and not reconstructed from the statement.

**Identity.** `fact_id` is deterministic — `<case>:<rule>[:<run>]` — so a
retried node reproduces the same ids and the state reducer dedups them,
and so a fact can be cited before anything has been persisted.
"""
from __future__ import annotations

from typing import Any, Literal

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ruleset import Rule

FactKind = Literal["breach", "satisfied", "measurement", "absent"]

AbsentReason = Literal[
    "missing_block",          # the firm did not submit the evidence this rule needs
    "insufficient_history",   # the block is there but too thin — e.g. Drift below its baseline minimum
    "out_of_scope",           # the rule does not apply to this case or run shape
    "rule_draft",             # the rule exists but is not active in this ruleset version
    "no_registry_record",     # the regulator's own register has no entry to check against
    "awaiting_peers",         # the rule consumes another specialist's output, not yet supplied
]

# Reasons that must say WHAT is missing. `out_of_scope` and `rule_draft`
# are about the rule, not about a gap in the evidence, and carry nothing.
_REASONS_NAMING_A_GAP: frozenset[str] = frozenset({
    "missing_block", "insufficient_history", "no_registry_record", "awaiting_peers",
})

# The reasons that roll up into a data-gap finding against the SUBMISSION.
# A firm that cannot produce a field has told you something; a rule that
# does not apply has not.
DATA_GAP_REASONS: frozenset[str] = frozenset({"missing_block", "insufficient_history"})


class EvidenceRef(BaseModel):
    """A structured pointer to what a claim rests on.

    Prose evidence ("cluster sum 8700.0 vs threshold 3000.0") cannot be
    resolved by anything downstream: the UI cannot link to it, the critic can
    only regex numbers out of it, and a report cannot cite it. A ref can be
    checked mechanically, which is what makes agents/critic.py a real
    grounding check rather than a heuristic.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "run", "transaction", "line_item", "tool_call", "control",
        "credential_field", "field", "statistic", "rule", "registry",
    ]
    ref: str          # "RUN-2026-0811-0043" | "cart.line_items[0]" | "counterparty_mix_psi"
    value: Any = None  # the value as the agent saw it — what the critic compares against


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str
    case_id: str
    domain: str                      # the specialist that owns the rule: "kya", "mandate", ...
    rule_id: str | None = None       # None only for measurements with no single owning rule
    run_ref: str | None = None       # the run this fact is about; None for dossier-level facts
    kind: FactKind
    statement: str                   # one sentence, readable by a human without context
    values: dict[str, Any] = Field(default_factory=dict)
    refs: list[EvidenceRef] = Field(default_factory=list)
    absent_reason: AbsentReason | None = None
    # What the rule needed and did not have: a submission block or field
    # ("consent_ceremony.rendered_values"), a register entry
    # ("registry:operators[OPR-009]"), or another agent's output. This is the
    # field the console's AbsentNotice renders and the data-gap finding names.
    missing: str | None = None

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
    def _a_gap_names_what_is_missing(self) -> "Fact":
        if self.kind != "absent" and self.missing is not None:
            raise ValueError(f"{self.fact_id}: `missing` is only valid when kind='absent'")
        if self.absent_reason in _REASONS_NAMING_A_GAP and not self.missing:
            raise ValueError(
                f"{self.fact_id}: absent_reason={self.absent_reason!r} must name what is "
                f"missing — 'could not evaluate' without saying why is not a supervisory fact"
            )
        return self

    @model_validator(mode="after")
    def _rule_outcomes_cite_a_rule(self) -> "Fact":
        if self.kind in ("breach", "satisfied", "absent") and not self.rule_id:
            raise ValueError(
                f"{self.fact_id}: kind={self.kind!r} is a rule outcome and must name its rule_id"
            )
        return self


class FactBuilder:
    """Mints facts with deterministic ids for one case and one specialist
    domain. Lives with the type because intake mints facts too (the eight
    cryptographic/chain rules), and ingestion importing from `agents/` would
    be the wrong direction."""

    def __init__(self, case_id: str, domain: str) -> None:
        self.case_id = case_id
        self.domain = domain

    def _id(self, rule_id: str, run_ref: str | None) -> str:
        return f"{self.case_id}:{rule_id}" + (f":{run_ref}" if run_ref else "")

    def breach(self, rule: Rule, statement: str, *, run_ref: str | None = None,
               values: dict[str, Any] | None = None,
               refs: Sequence[EvidenceRef] = ()) -> Fact:
        return Fact(fact_id=self._id(rule.rule_id, run_ref), case_id=self.case_id,
                    domain=self.domain, rule_id=rule.rule_id, run_ref=run_ref, kind="breach",
                    statement=statement, values=values or {}, refs=list(refs))

    def satisfied(self, rule: Rule, statement: str, *, run_ref: str | None = None,
                  values: dict[str, Any] | None = None,
                  refs: Sequence[EvidenceRef] = ()) -> Fact:
        return Fact(fact_id=self._id(rule.rule_id, run_ref), case_id=self.case_id,
                    domain=self.domain, rule_id=rule.rule_id, run_ref=run_ref, kind="satisfied",
                    statement=statement, values=values or {}, refs=list(refs))

    def verdict(self, rule: Rule, breached: bool, breach_statement: str,
                satisfied_statement: str, *, run_ref: str | None = None,
                values: dict[str, Any] | None = None,
                refs: Sequence[EvidenceRef] = ()) -> Fact:
        """The common two-branch shape: one condition, two statements."""
        if breached:
            return self.breach(rule, breach_statement, run_ref=run_ref, values=values, refs=refs)
        return self.satisfied(rule, satisfied_statement, run_ref=run_ref, values=values, refs=refs)

    def absent(self, rule: Rule, reason: AbsentReason, statement: str, *,
               missing: str | None = None, run_ref: str | None = None,
               values: dict[str, Any] | None = None) -> Fact:
        return Fact(fact_id=self._id(rule.rule_id, run_ref), case_id=self.case_id,
                    domain=self.domain, rule_id=rule.rule_id, run_ref=run_ref, kind="absent",
                    statement=statement, values=values or {}, absent_reason=reason,
                    missing=missing)

    def measurement(self, name: str, statement: str, *, rule: Rule | None = None,
                    run_ref: str | None = None, values: dict[str, Any] | None = None,
                    refs: Sequence[EvidenceRef] = ()) -> Fact:
        """A number (or a bounded piece of evidence) standing behind a judged
        rule. `name` keeps its id distinct from the rule's outcome fact."""
        owner = rule.rule_id if rule else self.domain
        return Fact(fact_id=self._id(f"{owner}#{name}", run_ref), case_id=self.case_id,
                    domain=self.domain, rule_id=rule.rule_id if rule else None, run_ref=run_ref,
                    kind="measurement", statement=statement, values=values or {},
                    refs=list(refs))
