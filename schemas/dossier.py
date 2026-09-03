"""An authorisation dossier — one agent, many independent runs.

docs/synthetic-data-spec.md. The regulatory act this models is *authorising an
agent*: an institution submits the runs its client's agent actually executed,
and the supervisor decides authorise / refuse / authorise with conditions.

Deliberately a NEW type rather than a change to CaseBundle. The existing
pipeline, its seven cases and its tests are built on the single-cart shape;
mutating that model would break them all at once and force the migration and
the data work to happen in the same change. Dossier lands alongside it, the
corpus is built against it, and the pipeline moves over deliberately.

The one idea the whole shape rests on: **runs are independent.** Each starts
cold, with its own task, its own tool calls, its own cart. Anything resembling
continuity between runs — a drifting objective, a creeping amount, a supplier
quietly taking over — is something the *supervisor* infers across runs, never
something the agent carried forward. That is why it is worth detecting, and it
is why 24 of the 73 failures in coverage-model.md cannot occur inside one run.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .kya import KYACredential
from .mandate import CartMandate, IntentMandate, PaymentMandate
from .submission import ConsentCeremony, ConstructionContext
from .transaction import TransactionLogEntry

FailureId = Annotated[str, StringConstraints(pattern=r"^F\d{1,2}$")]
SubmissionFailureId = Annotated[str, StringConstraints(pattern=r"^S\d$")]


# ---------------------------------------------------------------------------
# controls — split by owner, not tagged
# ---------------------------------------------------------------------------

class DeclaredControl(BaseModel):
    """Split into two lists on Controls rather than carrying an `owner` field.

    A bypassed operator control is a client conduct issue the institution
    should have caught; a bypassed institution control is a supervised-entity
    conduct issue. Different accountable party, different severity, different
    report. One list with an owner field would force every CTL-* rule to
    filter before it could say anything.
    """

    model_config = ConfigDict(extra="forbid")

    control_id: str
    risk_addressed: str
    rule: str
    enforcement: Literal["blocking", "advisory"]
    version: str


class Controls(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_declared: list[DeclaredControl] = Field(default_factory=list)
    institution_declared: list[DeclaredControl] = Field(default_factory=list)


class ControlOverride(BaseModel):
    """An anonymous override is not a supervisable fact. The conduct question
    is who, on what authority, and how often — so all three are required."""

    model_config = ConfigDict(extra="forbid")

    by: str
    reason: str
    at: str


class ControlExecution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control_id: str
    evaluated_at: str
    outcome: Literal["passed", "triggered", "not_evaluated"]
    override: ControlOverride | None = None


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

class Run(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    # A run file is filed on its own and must be readable on its own, so it
    # names its dossier rather than relying on which directory it sits in.
    dossier_id: str
    environment: Literal["sandbox", "production_pilot"]
    started_at: str
    ended_at: str
    trigger: Literal["user_initiated", "scheduled", "event_driven"]

    # The per-run task. UNTRUSTED TEXT — the one place operator-authored free
    # text reaches a model, so it is delimited, schema-constrained on output
    # and separately heuristic-flagged (CLAUDE.md cross-cutting rule 4).
    # Distinct from agent_version.prompt_hash, which is the SYSTEM prompt: one
    # is the reviewed release, the other is what somebody typed today.
    user_prompt: str

    # AP2's human-present flow: the shopper states what they want, and THAT
    # becomes an Intent Mandate for this shopping task — not a standing
    # entitlement. So the mandate lives on the run, and every run file is a
    # complete, self-contained chain: intent → cart → payment, one shopper.
    #
    # It is also what makes F49 ("within the rules but not what the person
    # meant") a real test. Checking a cart against a three-month envelope is
    # nearly vacuous; checking it against "white running shoes, size 10, under
    # $120" is not.
    intent_mandate: IntentMandate

    # The data contract's block, kept as a named block with its own field names
    # (coverage-model.md Part 3.1). It is published as "the minimum reporting
    # schema for supervised agentic payments", so its shape is the deliverable
    # — flattening it here would make the corpus and the schema disagree.
    construction_context: ConstructionContext

    consent_ceremony: ConsentCeremony | None = None

    cart: CartMandate | None = None
    payment: PaymentMandate | None = None
    controls_evaluated: list[ControlExecution] = Field(default_factory=list)

    outcome: Literal["completed", "abandoned", "blocked", "failed"]

    @model_validator(mode="after")
    def _outcome_matches_artifacts(self) -> Run:
        if self.outcome == "completed" and (self.cart is None or self.payment is None):
            raise ValueError(f"{self.run_id}: a completed run must carry both a cart and a payment")
        if self.outcome == "blocked" and self.payment is not None:
            raise ValueError(f"{self.run_id}: a blocked run must not carry a payment")
        if self.outcome == "blocked" and not any(
            e.outcome == "triggered" for e in self.controls_evaluated
        ):
            # Otherwise "blocked" is an unevidenced claim, and a control that
            # never appears in the log cannot be credited with having worked.
            raise ValueError(f"{self.run_id}: a blocked run must show a triggered control")
        return self


# ---------------------------------------------------------------------------
# submission context — what the operator chose to send, and what it will deploy
# ---------------------------------------------------------------------------

class DeploymentTarget(BaseModel):
    """What will actually run if this agent is authorised.

    Compared against the runs, this catches S3: certifying one configuration
    and shipping another. Three fields, and it is the oldest failure in
    conformance testing.
    """

    model_config = ConfigDict(extra="forbid")

    model_version: str
    prompt_release_ref: str
    tool_servers: list[str] = Field(default_factory=list)


class SubmissionContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submitted_at: str
    executed_from: str
    executed_to: str
    environment: Literal["sandbox", "production_pilot"]

    # Declared by the operator about itself. A gap between the two is S2 in one
    # comparison: the supervisor is looking at a subset somebody chose. It does
    # not prove curation and the report should not imply it does — the same
    # posture the spec takes on self-attested model versions.
    runs_executed_total: int
    runs_submitted: int

    deployment_target: DeploymentTarget

    @model_validator(mode="after")
    def _submitted_not_more_than_executed(self) -> SubmissionContext:
        if self.runs_submitted > self.runs_executed_total:
            raise ValueError("runs_submitted exceeds runs_executed_total")
        return self


# ---------------------------------------------------------------------------
# ground truth — eval only, stripped before the pipeline sees a dossier
# ---------------------------------------------------------------------------

class PlantedDefect(BaseModel):
    """Named to a run. With fifty runs, a specialist reporting F29 *somewhere*
    has a one-in-fifty chance of being accidentally right; run_ref closes that.

    `run_ref` is None for the S-failures, which are properties of the
    submission rather than of any run — an unrepresentative selection or a
    deployment target that differs from what was tested belongs to the dossier.
    Forcing them onto run 1 made that run simultaneously clean and defective,
    which is not a thing a run can be.
    """

    model_config = ConfigDict(extra="forbid")

    run_ref: str | None = None
    failure: FailureId | SubmissionFailureId
    what: str
    control_id: str | None = None
    rule_id: str | None = None


class GroundTruth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planted: list[PlantedDefect] = Field(default_factory=list)
    # Listed, never derived by subtraction: a run nobody classified should fail
    # the verifier rather than silently count as clean and inflate the
    # false-positive denominator.
    clean_runs: list[str] = Field(default_factory=list)
    narrative: str | None = None


# ---------------------------------------------------------------------------
# the dossier
# ---------------------------------------------------------------------------

class AgentCard(BaseModel):
    """The agent's own signed capability descriptor.

    Provenance's cross-check needs four sources that should all agree: the
    card, the KYA credential, the agent registry, and the tool calls actually
    observed. Any pair disagreeing is a finding — an agent calling a server its
    own card never declared is a different failure from one calling a server
    the *regulator* never authorised.
    """

    model_config = ConfigDict(extra="forbid")

    url: str
    card_hash: str
    declared_capabilities: list[str] = Field(default_factory=list)
    declared_tool_servers: list[str] = Field(default_factory=list)
    signature: dict = Field(default_factory=dict)


class ChangeEvent(BaseModel):
    """Something the operator changed, with a timestamp.

    Drift can already find a change-point. F65 is the *causal* version — "the
    agent does not behave like it used to, AND SOMETHING SPECIFIC CHANGED IT" —
    which needs something for the onset estimate to land on. Without this log,
    Drift can only ever say "something changed", which is the finding a
    supervisor can do least with.
    """

    model_config = ConfigDict(extra="forbid")

    at: str
    kind: Literal["prompt_release", "model_version", "control_version",
                  "credential_reissue", "tool_server", "merchant_onboarded",
                  "policy_change"]
    ref: str
    detail: str | None = None


class RunRef(BaseModel):
    """One entry in the case's run index.

    The digest is what makes the index an attestation rather than a table of
    contents: the case says which runs were filed and what each contained, so a
    run added, removed or edited after submission is detectable. That turns S2
    (partial submission) from a number the operator declares about itself into
    something structural.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    file: str                    # relative to the dossier directory
    sha256: str


class Dossier(BaseModel):
    """The case: everything the 50 runs share, plus the index of those runs.

    Runs live in their own files because that is how they are produced — one
    execution, one moment, one record. What stays here is what is genuinely
    common to all of them: one Intent Mandate, one credential series, one set
    of controls. Copying those into every run file would duplicate them and,
    worse, let them drift out of agreement with each other.
    """

    model_config = ConfigDict(extra="forbid")

    dossier_id: str
    submission_purpose: Literal["authorisation", "renewal", "periodic_supervision", "incident"]

    institution_id: str          # → registry/institutions.json — the submitter
    operator_id: str             # → registry/operators.json
    agent_id: str                # → registry/agents.json — SUBJECT OF THE DECISION

    submission_context: SubmissionContext

    kya_credential: KYACredential
    # Prior credentials for this agent. Capability creep is invisible in a
    # single credential by definition — F20/F21/F22/F23 all need the series.
    credential_history: list[KYACredential] = Field(default_factory=list)

    # No mandate here. Each run carries its own — see Run.intent_mandate.
    agent_card: AgentCard | None = None
    controls: Controls
    change_log: list[ChangeEvent] = Field(default_factory=list)
    run_index: list[RunRef]

    @model_validator(mode="after")
    def _run_ids_unique(self) -> Dossier:
        ids = [r.run_id for r in self.run_index]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate run_id in the run index")
        return self


class LoadedDossier(BaseModel):
    """A dossier with its runs, ledger and (for eval only) ground truth read in.

    Assembled by data/dossier_loader.py. Ground truth lives in its own file, so
    withholding it from the pipeline is "do not read that file" rather than a
    code path someone can forget to call.
    """

    model_config = ConfigDict(extra="forbid")

    dossier: Dossier
    runs: list[Run]
    transaction_history: list[TransactionLogEntry] = Field(default_factory=list)
    ground_truth: GroundTruth | None = None

    @model_validator(mode="after")
    def _index_matches_runs(self) -> LoadedDossier:
        indexed = {r.run_id for r in self.dossier.run_index}
        loaded = {r.run_id for r in self.runs}
        if missing := indexed - loaded:
            raise ValueError(f"indexed but not loaded: {sorted(missing)}")
        if extra := loaded - indexed:
            raise ValueError(f"run files present but not in the index: {sorted(extra)}")
        return self

    @model_validator(mode="after")
    def _ground_truth_covers_every_run(self) -> LoadedDossier:
        if self.ground_truth is None:
            return self
        ids = {r.run_id for r in self.runs}
        named = {p.run_ref for p in self.ground_truth.planted if p.run_ref} | set(
            self.ground_truth.clean_runs)
        if unknown := named - ids:
            raise ValueError(f"ground truth names runs not in the dossier: {sorted(unknown)}")
        if unclassified := ids - named:
            raise ValueError(
                "every run must be declared clean or carry a planted defect; "
                f"unclassified: {sorted(unclassified)}"
            )
        return self
