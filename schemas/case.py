"""Case bundle — one full submission.

Field shapes follow docs/phases/01-synthetic-data.md §2.7.

`label` and `narrative` are eval-only ground truth (see the seven scenario
labels in §3). A real submission never carries them; data/loader.py strips
both before a case reaches the pipeline.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from .kya import KYACredential
from .mandate import MandateChain
from .transaction import TransactionLogEntry

ScenarioLabel = Literal[
    "compliant",
    "mandate_breaching",
    "broken_chain",
    "synthetic_identity",
    "structuring",
    "drift",
    "prompt_injection",
]


class Firm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    firm_id: str
    name: str
    sector: str
    hq: str


class CaseBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    label: ScenarioLabel | None = None
    narrative: str | None = None
    firm: Firm
    kya_credential: KYACredential
    mandate_chain: MandateChain
    transaction_history: list[TransactionLogEntry]
