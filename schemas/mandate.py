"""Intent / Cart / Payment mandate chain.

Field shapes follow docs/phases/01-synthetic-data.md §2.2-2.4.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import ChainLink, SignatureEnvelope
from .submission import SubMerchant


class Principal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # KYA-ACC-02 asserts the delegation chain terminates in the principal who
    # signed the Intent. That holds for corporate delegation, where one officer
    # both delegates to the agent and signs the mandate. It is structurally
    # false for consumer shopping: the shopper signs their own Intent, while
    # the agent's credential chain terminates at the OPERATOR's accountable
    # officer. Different people, by design.
    #
    # So the rule needs a scope rather than a fudge. For a consumer principal
    # the equivalent assurance is not the delegation chain at all — it is that
    # the consent ceremony records the same principal who signed, which is SCA
    # evidence the bank already holds.
    principal_type: Literal["consumer", "delegated_officer"] = "delegated_officer"

    name: str
    role: str
    principal_id: str
    org: str


class AgentInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    agent_name: str
    operator_firm: str
    model_version: str


class AllowedCounterparty(BaseModel):
    model_config = ConfigDict(extra="forbid")

    counterparty_id: str
    name: str


class MandateUsage(BaseModel):
    """How many times this authority may be drawn on.

    Without it F50 ("the same authorisation was used twice") has no baseline to
    violate — a mandate that never says how often it may be used cannot be
    used too often. In AP2's human-present flow a task mandate is single-use by
    nature: the user approved *this* basket, not a standing entitlement.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["single_use", "recurring"]
    max_uses: int | None = None
    uses_consumed: int = 0


class AuthorizationScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose_category: str
    max_transaction_amount: float
    max_cumulative_amount: float
    currency: str
    valid_from: str
    valid_until: str
    allowed_merchant_categories: list[str]
    allowed_counterparties: list[AllowedCounterparty] = Field(default_factory=list)
    # Present when allowed_counterparties is deliberately empty, to say why
    # (e.g. category-governed eligibility rather than a fixed vendor list).
    counterparty_policy: str | None = None
    geographic_scope: str
    human_presence_required: bool
    usage: MandateUsage | None = None


class Consent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str
    timestamp: str
    device_id: str


class IntentMandate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_mandate_id: str
    protocol_version: str
    issued_at: str
    expires_at: str
    principal: Principal
    agent: AgentInfo
    natural_language_intent: str
    authorization_scope: AuthorizationScope
    consent: Consent
    signature: SignatureEnvelope


class Merchant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchant_id: str
    name: str
    mcc: str
    country: str
    # Geographic scope carries sanctions, cross-border reporting and tax
    # weight — an agent transacting outside its permitted region can breach
    # obligations unrelated to the payment. Unblocks MND-CAP-04, which is
    # written and has been blocked on this field's absence (F48).
    region: str | None = None
    # F52 — marketplace fronting. Optional because a direct merchant has none.
    sub_merchant: SubMerchant | None = None


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str
    # Merchant-authored free text — the one field in the whole schema that
    # can carry adversarial content (see case-007-prompt-injection).
    description: str
    qty: int
    unit_price: float


class AgentAttestation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reasoning: str


class CartMandate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cart_mandate_id: str
    chain_link: ChainLink
    created_at: str
    merchant: Merchant
    line_items: list[LineItem]
    cart_total: float
    currency: str
    agent_attestation: AgentAttestation
    signature: SignatureEnvelope


class PaymentMethod(BaseModel):
    """The instrument the money left FROM."""

    model_config = ConfigDict(extra="forbid")

    type: str
    instrument_id_masked: str
    issuer: str


class Payee(BaseModel):
    """Where the money went TO.

    `payment_method` describes the payer's card; nothing in the signed record
    said anything about the destination, which is precisely what F51 ("nobody
    knows who was paid") and F53 ("a wallet with no identifiable owner") are
    about. Comparing `beneficiary_name_on_account` against the merchant's legal
    name is also Confirmation-of-Payee, which banks already run.
    """

    model_config = ConfigDict(extra="forbid")

    settlement_account_masked: str
    scheme: str                          # SEPA | FPS | ACH | card_settlement | ...
    country: str
    beneficiary_name_on_account: str | None = None


class PaymentMandate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_mandate_id: str
    chain_link: ChainLink
    authorized_at: str
    amount: float
    currency: str
    payment_method: PaymentMethod
    payee: Payee | None = None
    settlement_status: Literal["settled", "declined", "reversed"]
    signature: SignatureEnvelope


class MandateChain(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: IntentMandate
    cart: CartMandate
    payment: PaymentMandate
