"""Shared envelope types used across every mandate/credential object.

Field shapes follow docs/phases/01-synthetic-data.md §2.1.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class SignatureEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alg: Literal["Ed25519"]
    signer_key_id: str
    value: str
    # Delegation-chain entries sign a small self-attestation and don't carry
    # these two fields (see §2.5); every other signed object does.
    signed_payload_hash: str | None = None
    signed_at: str | None = None


class ChainLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prev_mandate_id: str
    prev_mandate_hash: str
