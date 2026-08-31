"""KYA credential — the agent's identity, separate from any one mandate chain.

Field shapes follow docs/phases/01-synthetic-data.md §2.5.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

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
    signature: SignatureEnvelope


class KYACredential(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential_id: str
    agent_id: str
    agent_name: str
    operator_firm: str
    issuer: IssuerRef
    issued_at: str
    expires_at: str
    capabilities: list[str]
    # Index 0 = agent itself; a credential is a synthetic-identity finding
    # when this doesn't terminate in a holder_type == "human" link.
    delegation_chain: list[DelegationEntry]
    signature: SignatureEnvelope
