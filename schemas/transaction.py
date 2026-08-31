"""Settled transaction log entry — what Log and Drift read.

Field shapes follow docs/phases/01-synthetic-data.md §2.6.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TransactionLogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: str
    timestamp: str
    agent_id: str
    payment_mandate_ref: str
    counterparty_name: str
    counterparty_id: str
    mcc: str
    amount: float
    currency: str
    status: str
    channel: str
