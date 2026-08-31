"""The synthesizer's output (architecture-v2 §15.2) — a relationship BETWEEN
findings, never a finding itself.

Three properties make invention impossible in any way that matters:
every finding_id must resolve to a finding that exists (checked in Python by
agents/synthesizer.py, not by a second model); a Correlation cannot modify or
remove the findings it references — it only exists alongside them; and
scoring never reads it (pipeline/scoring.py's signature is unchanged). If the
synthesizer produces nonsense, the score is untouched and the blast radius is
one display panel.

`min_length=2` on finding_ids is structural: a "relationship" over one
finding is just a restatement, which is the drafting agent's job, not this.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Correlation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    finding_ids: list[str] = Field(min_length=2)
    relationship: Literal["same_event", "causal", "corroborating", "contradictory"]
    explanation: str
