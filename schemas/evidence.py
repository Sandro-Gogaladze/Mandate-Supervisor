"""The `EvidencePack` — what intake establishes before any agent runs.

HANDOFF §5: intake is code, zero model calls. It verifies every signature and
chain, resolves the six registries, computes the shared statistics once and
notes which submission blocks are present. **No rules are evaluated here**
except the eight cryptographic/chain rules the rulebooks assign to intake;
rules belong to agents.

Why one pack rather than each agent computing what it needs: the same
counterparty profile is read by Counterparty, Log and Systemic, the same
baseline split by Drift and the investigator's `recompute_stats`, and the
same "is `rendered_values` present" answer by Consent's checkers and the
orchestrator's round-1 dispatch rule. Computed once, recorded once, cited
everywhere by the same numbers — which is also what lets the critic check an
assessment's quoted values against something.

Everything here is derived from the submission and the registries. It is
not the submission (that is the `LoadedDossier`) and it is not a verdict.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .fact import Fact


class CounterpartyProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    counterparty_id: str
    name: str
    count: int
    total: float
    share: float                       # of settled spend across the whole history
    in_window_count: int
    in_window_total: float
    first_seen: str
    last_seen: str
    mccs: list[str] = Field(default_factory=list)
    registered: bool                   # present in merchants.json
    beneficial_owner: str | None = None
    watchlist_flags: list[str] = Field(default_factory=list)
    registry_first_seen: str | None = None


class TimingProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hour_histogram: dict[str, int] = Field(default_factory=dict)
    weekday_histogram: dict[str, int] = Field(default_factory=dict)
    off_hours_share: float = 0.0       # before 08:00 or from 18:00, local time as filed
    min_gap_hours: float | None = None
    median_gap_hours: float | None = None
    gaps_under_1_hour: int = 0


class AmountProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = 0
    total: float = 0.0
    mean: float = 0.0
    median: float = 0.0
    std: float = 0.0
    min: float = 0.0
    max: float = 0.0
    round_number_count: int = 0


class DriftBaseline(BaseModel):
    """The baseline/comparison split Drift judges over. `sufficient` is the
    data-availability gate — below the rule's minimum there is no baseline,
    and Drift's fact says so rather than computing over too little."""

    model_config = ConfigDict(extra="forbid")

    baseline_window_days: int
    min_total_transactions: int
    sufficient: bool
    baseline_count: int = 0
    comparison_count: int = 0
    amount_shift: dict[str, Any] = Field(default_factory=dict)
    frequency_shift: dict[str, Any] = Field(default_factory=dict)
    counterparty_mix_psi: float | None = None
    mcc_mix_psi: float | None = None


class ControlProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_declared: list[str] = Field(default_factory=list)
    institution_declared: list[str] = Field(default_factory=list)
    evaluations: int = 0
    triggered: int = 0
    overridden: int = 0
    not_evaluated: int = 0
    by_control: dict[str, dict[str, int]] = Field(default_factory=dict)
    runs_without_evaluation: list[str] = Field(default_factory=list)


class RegistryResolution(BaseModel):
    """Which regulator-held records this submission resolved to. A miss here
    is not a finding by itself — the rule that needed the record says
    `absent/no_registry_record` — but it is the first thing an officer wants
    to know, and it is what the round-1 dispatch rule reads."""

    model_config = ConfigDict(extra="forbid")

    institution: bool
    operator: bool
    agent: bool
    issuer: bool
    institution_name: str | None = None
    operator_name: str | None = None
    agent_classification: str | None = None
    risk_class: str | None = None
    unresolved_merchants: list[str] = Field(default_factory=list)


class Integrity(BaseModel):
    """Cryptographic integrity of the submission, in one place. The run index
    was verified by the loader (a mismatch never reaches here); every signed
    object's signature and every chain link are verified at intake."""

    model_config = ConfigDict(extra="forbid")

    run_index_verified: bool = True
    signatures_checked: int = 0
    signature_failures: list[str] = Field(default_factory=list)
    chain_links_checked: int = 0
    chain_links_broken: list[str] = Field(default_factory=list)


class SubmissionProfile(BaseModel):
    """The raw comparisons behind S1–S4, not the verdicts. What the operator
    said it ran versus what it filed; what it will deploy versus what the
    runs observed. Scoring decides what they mean (Phase 6)."""

    model_config = ConfigDict(extra="forbid")

    purpose: str
    environment: str
    runs_executed_total: int
    runs_submitted: int
    runs_filed: int
    deployment_model_version: str
    deployment_prompt_release_ref: str
    deployment_tool_servers: list[str] = Field(default_factory=list)
    observed_model_versions: list[str] = Field(default_factory=list)
    observed_release_refs: list[str] = Field(default_factory=list)
    observed_tool_servers: list[str] = Field(default_factory=list)


class EvidencePack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dossier_id: str
    agent_id: str
    operator_id: str
    institution_id: str
    submitted_at: str
    executed_from: str
    executed_to: str

    run_ids: list[str]
    runs_by_outcome: dict[str, int] = Field(default_factory=dict)

    transactions_total: int
    transactions_in_window: int
    transactions_trailing: int
    # Money that moved inside the window with no run behind it — itself a
    # finding (HANDOFF §2.3), recorded here for the rule that will make it.
    in_window_without_run: list[str] = Field(default_factory=list)

    # Dossier-level optional blocks, and the same per run. Keys are the
    # block names the rulebooks and the console use.
    blocks: dict[str, bool] = Field(default_factory=dict)
    run_blocks: dict[str, dict[str, bool]] = Field(default_factory=dict)

    submission: SubmissionProfile
    registries: RegistryResolution
    integrity: Integrity
    counterparties: list[CounterpartyProfile] = Field(default_factory=list)
    timing: TimingProfile = Field(default_factory=TimingProfile)
    amounts: AmountProfile = Field(default_factory=AmountProfile)
    drift: DriftBaseline
    controls: ControlProfile = Field(default_factory=ControlProfile)

    # The eight intake rules, as facts, against the active rulebooks. The
    # specialists re-verify against whatever ruleset they are handed (the
    # sandbox may hand them a draft one); these are the record of intake.
    ingestion_facts: list[Fact] = Field(default_factory=list)

    def runs_with(self, block: str) -> list[str]:
        return [rid for rid, blocks in self.run_blocks.items() if blocks.get(block)]

    def runs_without(self, block: str) -> list[str]:
        return [rid for rid, blocks in self.run_blocks.items() if not blocks.get(block)]
