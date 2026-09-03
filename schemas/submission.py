"""The three submission blocks a firm must send beyond the signed artifacts.

docs/coverage-model.md Part 3 and docs/synthetic-data-spec.md Part 3. AP2's
signatures cover the mandate chain; the largest concentration of attacks is
in the phase *before* anything is signed, and in the firm's own runtime
controls. A submission carrying only signed artifacts is structurally
incapable of revealing either.

All three are optional on CaseBundle. A firm that omits one does not get a
clean case — every rule needing that block returns an `absent` fact, and the
run emits a data-gap finding naming the block and the rules it disabled. A
firm that cannot produce a field has told you something.

Every field here is sourced from a system a bank already runs: consent from
Strong Customer Authentication logs, tool calls from agent observability,
controls from the fraud engine's own decision log. Deliberately absent:
screenshots, provider-signed model attestation, full catalog archives, and
agent-to-agent transcripts — see the spec for why each was dropped.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# consent_ceremony — was a human there, and did they see what got signed?
# ---------------------------------------------------------------------------

class RenderedLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str
    qty: int
    unit_price: float


class RenderedValues(BaseModel):
    """What the human actually saw on screen at the moment of approval.

    Compared against the signed Cart, this is the single highest-value field
    pair in the schema (F29): the screen said $50, the signature covers
    $1,240, and every other check passes because the divergence happened
    between the render and the signature — a place nothing in the signed
    record describes.
    """

    model_config = ConfigDict(extra="forbid")

    amount: float
    currency: str
    merchant: str
    line_items: list[RenderedLineItem] = Field(default_factory=list)
    caps_shown: dict[str, float] = Field(default_factory=dict)


class ConsentCeremony(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurred: bool
    # A standing authority approved once for a whole mandate window is a
    # different object from a confirmation shown for one cart, and only the
    # second makes `rendered_values.amount` comparable to `cart_total`. Without
    # this distinction the F29 check fires on every standing-consent case,
    # where the rendered amount is legitimately the cap rather than the total.
    ceremony_scope: Literal["per_transaction", "standing_authority"] = "per_transaction"
    timestamp: str | None = None
    principal_id: str | None = None          # must match Intent.principal.principal_id
    method: str | None = None                # explicit_ui_confirmation | biometric | ...
    rendered_values: RenderedValues | None = None
    rendered_hash: str | None = None
    scope_consented: dict[str, Any] = Field(default_factory=dict)
    # The chain that makes recurring authority reviewable: a renewal points
    # at the consent it replaces. None on a first consent.
    supersedes_consent_id: str | None = None


# ---------------------------------------------------------------------------
# construction_context — was the mandate built from trustworthy inputs?
# ---------------------------------------------------------------------------

class ModelAttestation(BaseModel):
    """Self-declared, and honestly labelled as such: no major provider
    cryptographically signs "this response came from model X". A declaration
    the firm is accountable for catches misconfiguration and silent model
    upgrades — not a determined liar."""

    model_config = ConfigDict(extra="forbid")

    declared_version: str        # must equal Intent.agent.model_version
    observed_version: str        # what the provider's API actually returned
    provider: str
    self_attested_by: str


class PolicyVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_hash: str             # the agent's system prompt, hashed
    release_ref: str             # the reviewed release it came from


class ResultExcerpt(BaseModel):
    """A bounded excerpt of external prose the agent actually consumed.

    F32 has four channels. Listing text is covered because it lands in the
    signed cart's line items. Tool-description poisoning is covered by
    comparing tool_schema_hash against tools.json. Agent-to-agent messages are
    parked. **Retrieved reference material was not covered at all**, because
    `result_digest` cannot do that job: a hash proves the bytes arrived
    unaltered, it cannot reveal that those bytes carry an instruction. Nobody
    reads `sha256:a04d…` and sees "no confirmation needed, this is
    pre-authorized".

    This is not the "full catalog archive" the data contract rejects. It is the
    specific fields the agent consumed, capped, already present in the
    observability trace the contract points at for tool_calls.
    """

    model_config = ConfigDict(extra="forbid")

    source: str                  # the server the prose came from
    fields: list[str] = Field(default_factory=list)
    text: str = Field(max_length=2000)
    truncated: bool = False


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int
    tool_name: str
    server_id: str               # WHICH server — the pinning check
    tool_schema_hash: str        # detects tool-description poisoning
    arguments: dict[str, Any] = Field(default_factory=dict)
    # Integrity and CORRELATION, not detection: the same digest across firms is
    # a campaign (F69), across runs a changed source. It does not reveal
    # content — that is what result_excerpt is for.
    result_digest: str
    result_excerpt: ResultExcerpt | None = None


class Alternative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str
    merchant_id: str
    price: float
    description: str | None = None


class SelectionContext(BaseModel):
    """What the agent could have chosen, bounded to the pick plus a handful
    of alternatives. Detecting systematic worse-value selection needs the
    comparison set; archiving a whole catalog response would be expensive
    and commercially sensitive for no extra signal."""

    model_config = ConfigDict(extra="forbid")

    query: str
    selected_sku: str
    # The data contract says top 5 above a value threshold. The cap is the
    # point on both sides: fewer than a handful cannot establish that an agent
    # *systematically* chooses worse (F38), and an unbounded list is the
    # catalog archive the contract rejects.
    alternatives_considered: list[Alternative] = Field(default_factory=list, max_length=5)


class ConstructionContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: ModelAttestation
    policy_version: PolicyVersion
    tool_calls: list[ToolCall] = Field(default_factory=list)
    selection_context: SelectionContext | None = None


# ---------------------------------------------------------------------------
# controls — did the firm's own runtime controls work?
# ---------------------------------------------------------------------------

class DeclaredControl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control_id: str
    risk_addressed: str          # the vocabulary CTL-REP-02 checks coverage against
    rule: str                    # human-readable statement of what it enforces
    enforcement: Literal["blocking", "advisory"]
    version: str


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
    transaction_ref: str | None = None
    evaluated_at: str
    outcome: Literal["passed", "triggered", "not_evaluated"]
    override: ControlOverride | None = None


class Controls(BaseModel):
    model_config = ConfigDict(extra="forbid")

    declared: list[DeclaredControl] = Field(default_factory=list)
    execution_log: list[ControlExecution] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# merchant disclosure
# ---------------------------------------------------------------------------

class SubMerchant(BaseModel):
    """A marketplace identity conceals the seller that actually set the terms.
    Every check runs against the platform's clean reputation while the real
    counterparty stays invisible — and the platform disclaims the seller's
    conduct, so liability evaporates too. Already a card-scheme reporting
    requirement; it simply isn't surfaced to the paying side."""

    model_config = ConfigDict(extra="forbid")

    id: str
    legal_name: str
    relationship: Literal["marketplace_seller", "direct", "reseller", "dropship"]
