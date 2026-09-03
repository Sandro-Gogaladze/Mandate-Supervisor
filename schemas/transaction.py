"""Settled transaction log entry — what Log and Drift read.

Field shapes follow docs/phases/01-synthetic-data.md §2.6.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TransactionLogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: str
    # The run that produced it. None is legitimate for ledger entries predating
    # the submitted window — that trailing history is what gives Drift a
    # baseline. Inside the window it is a finding: money moved outside any
    # recorded episode.
    run_ref: str | None = None
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
