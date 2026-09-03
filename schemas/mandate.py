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
    model_config = ConfigDict(extra="forbid")

    type: str
    instrument_id_masked: str
    issuer: str


class PaymentMandate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_mandate_id: str
    chain_link: ChainLink
    authorized_at: str
    amount: float
    currency: str
    payment_method: PaymentMethod
    settlement_status: Literal["settled", "declined", "reversed"]
    signature: SignatureEnvelope


class MandateChain(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: IntentMandate
    cart: CartMandate
    payment: PaymentMandate
