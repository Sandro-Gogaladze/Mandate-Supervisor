"""Unverified LLM observation — deliberately NOT a Finding.

No rule_id: nothing here traces to a reproducible, deterministic check.
No severity_weight: there's nothing to weight a hunch by. Never fed into
scoring (PLAN item 11) and never citable by the drafting agent (item 12)
the way a Finding is — surfaced to a human reviewer only, clearly labeled
as unverified.

Originally KYA-specific (agents/kya_reasoning.py, Phase 5); generalized
here once the Log agent (Phase 7) needed the exact same concept for its
own open-ended anomaly-hunting tail — same reasoning, same shape, shared
rather than duplicated per agent.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from typing import Literal

from .finding import FindingAgent

# An Observation can come from the four specialists OR the investigator —
# unlike FindingAgent, which stays the four specialists only: the type system
# itself says the investigator cannot mint a Finding (architecture-v2 §16).
ObservationAgent = FindingAgent | Literal["investigator"]


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    agent: ObservationAgent
    note: str
    cited_evidence: str
