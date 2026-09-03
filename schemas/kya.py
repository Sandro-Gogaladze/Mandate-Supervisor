"""KYA credential — the agent's identity, separate from any one mandate chain.

Field shapes follow docs/phases/01-synthetic-data.md §2.5.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import SignatureEnvelope


class IssuerRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issuer_id: str
    issuer_name: str


class DelegationEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: int
    holder_id: str
    holder_type: Literal["agent", "org", "human"]
    name: str
    # What THIS level was granted, so a child can be compared against its
    # parent. Without it F11 ("a middle party granted more authority than it
    # had") is undetectable: a chain that records only identities and
    # signatures is a list of names, not a record of delegated authority.
    granted_capabilities: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    signature: SignatureEnvelope


class KYACredential(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential_id: str
    agent_id: str
    agent_name: str
    operator_firm: str
    issuer: IssuerRef
    # LIF-05: staleness of the revocation check, not its answer. An institution
    # that cannot say when it last looked has a control gap regardless of
    # whether the credential turns out to be good.
    revocation_checked_at: str | None = None
    revocation_source: str | None = None
    issued_at: str
    expires_at: str
    capabilities: list[str]
    # Index 0 = agent itself; a credential is a synthetic-identity finding
    # when this doesn't terminate in a holder_type == "human" link.
    delegation_chain: list[DelegationEntry]
    signature: SignatureEnvelope
