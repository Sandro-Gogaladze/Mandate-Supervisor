"""The policy sandbox's typed record (docs/phases/14-policy-sandbox.md).

A regulator writing the Agent Supervision Rulebook — 102 rules across nine
domains, "KYA" in industry shorthand — has no way today to know whether a
threshold is right, or whether a rule has ever caught anything. The sandbox
answers that by running the *production graph* over the labelled corpus with
a candidate rulebook and reporting what changed.

Three types carry the discipline that makes those numbers mean something:

- `RulesetDraft` is a fork, never an edit in place. A published version stays
  exactly as it was when a sweep measured it; otherwise a scorecard expires
  silently the moment someone tunes a parameter.
- `SweepPins` says what a sweep is comparable to. Two sweeps can be diffed
  exactly when everything except the rulebook matches — same corpus, same
  code, same mode. Same discipline as `context_digest` on a dispatch.
- `RuleScore` carries counts, never bare rates. The corpus holds 26 planted
  defects; most per-rule numbers rest on one or two. A rule at "100% recall"
  over n=1 has told you nothing, and a bare `1.0` on screen invites exactly
  the trust it has not earned.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .ruleset import Ruleset

SweepMode = Literal["mechanical", "live"]

# Below this many labelled examples a rate is noise wearing a number. The
# page renders "insufficient evidence" instead, and `RuleScore.trustworthy`
# is what it reads.
MIN_EVIDENCE = 5


class RulesetDraft(BaseModel):
    """A candidate rulebook for one domain, forked from a published version."""

    model_config = ConfigDict(extra="forbid")

    draft_id: str
    domain: str
    base_version: str
    label: str
    ruleset: Ruleset
    digest: str
    created_by: str
    created_at: str
    notes: str | None = None
    # What this draft changed against its base, in human terms — computed on
    # write so the version graph can render without reloading both books.
    edits: list[str] = Field(default_factory=list)


class SweepPins(BaseModel):
    """Everything except the rulebook. Two sweeps compare iff these match."""

    model_config = ConfigDict(extra="forbid")

    corpus_digest: str
    code_revision: str
    mode: SweepMode


class Metrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None


class RuleScore(BaseModel):
    """One rule's showing over the corpus.

    `fired` answers "does this rule do anything at all?" without reference to
    labels — the cheapest useful signal the sandbox produces, and the one that
    finds dead rules.
    """

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    domain: str
    status: str
    evaluation: str
    severity_weight: float
    failures: list[str] = Field(default_factory=list)
    fired: int = 0
    metrics: Metrics = Field(default_factory=Metrics)
    # Labelled-clean runs this rule fired on: a real false positive, as
    # opposed to firing on a defective run for the wrong reason.
    clean_run_hits: list[str] = Field(default_factory=list)

    @property
    def labelled(self) -> int:
        return self.metrics.tp + self.metrics.fn

    @property
    def trustworthy(self) -> bool:
        """Enough labelled examples for the rate to mean anything."""
        return self.labelled >= MIN_EVIDENCE

    @property
    def dead(self) -> bool:
        return self.fired == 0 and self.status == "active"


class DossierOutcome(BaseModel):
    """Question 5 — the one a regulator actually asks. Not per-rule F1 but:
    with this rulebook, does each submission get the right disposition?"""

    model_config = ConfigDict(extra="forbid")

    dossier_id: str
    expected: str
    actual: str
    correct: bool
    planted_defects: int
    clean_runs: int
    # The continuous quantity severity drives. A disposition only moves when
    # the score crosses a tier boundary, so severity edits were invisible on a
    # scorecard that recorded the disposition alone — 0.5 -> 0.9 on a rule
    # could change nothing visible while changing how the case is weighed.
    # Recording the weight makes both kinds of edit measurable: thresholds
    # move what fires, severity moves this.
    weight_per_run: float | None = None
    hard_gates: int = 0


class Label(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dossier_id: str
    run_ref: str | None
    failure: str
    what: str = ""


class Detection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dossier_id: str
    run_ref: str | None
    failure: str
    rule_id: str | None = None


class SweepResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall: Metrics
    dossiers: list[DossierOutcome] = Field(default_factory=list)
    per_rule: dict[str, RuleScore] = Field(default_factory=dict)
    per_failure: dict[str, Metrics] = Field(default_factory=dict)
    per_domain: dict[str, Metrics] = Field(default_factory=dict)
    clean_runs: int = 0
    clean_run_false_positives: list[str] = Field(default_factory=list)
    missed: list[Label] = Field(default_factory=list)
    unexpected: list[Detection] = Field(default_factory=list)
    dead_rules: list[str] = Field(default_factory=list)
    # Labels this sweep could not score at all — every rule that declares the
    # failure is model-judged and the model did not run. Reported rather than
    # silently dropped, so the denominator cannot shrink to flatter itself.
    not_scoreable: list[Label] = Field(default_factory=list)
    # Domains whose rules a mechanical sweep could not evaluate at all —
    # Transaction Patterns is 0/3 computable, Behavioural Drift 0/1, so a
    # mechanical total that ignored them would imply coverage it does not have.
    unevaluated_domains: list[str] = Field(default_factory=list)


class Sweep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sweep_id: str
    domain: str
    # A published version ("2026.9") or a draft id.
    ruleset_ref: str
    ruleset_digest: str
    label: str
    pins: SweepPins
    started_at: str
    finished_at: str | None = None
    result: SweepResult | None = None
    error: str | None = None


class RuleDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    before: RuleScore | None = None
    after: RuleScore | None = None


class Flip(BaseModel):
    """A single (run, failure) pair that changed verdict between two sweeps.
    A rulebook change is judged by what it changed, not its absolute score."""

    model_config = ConfigDict(extra="forbid")

    dossier_id: str
    run_ref: str | None
    failure: str
    direction: Literal["caught", "lost", "new_false_positive", "fixed_false_positive"]


class SweepComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base: Sweep
    candidate: Sweep
    comparable: bool
    incomparable_reason: str | None = None
    flips: list[Flip] = Field(default_factory=list)
    rule_deltas: list[RuleDelta] = Field(default_factory=list)
    dossier_changes: list[dict] = Field(default_factory=list)
