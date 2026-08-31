"""Risk score types (PLAN item 11).

The score is arithmetic, not judgment: `pipeline/scoring.py` sums finding
`severity_weight`s per agent and in total, and the disposition tier comes
from `registry/scoring.json`. `RiskScore.factors` keeps the per-agent
breakdown so "why this score" is always answerable as a printable
derivation — these findings × these ruleset weights × this tier config —
which is the only honest meaning of "explainable, factor-level scoring"
(CLAUDE.md). Observations contribute nothing, ever.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .finding import FindingAgent

DispositionTier = Literal["clear", "review", "escalate"]


class RiskFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: FindingAgent
    score: float
    finding_count: int


class RiskScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    total: float
    tier: DispositionTier
    tier_label: str
    tier_guidance: str
    factors: list[RiskFactor]
    config_version: str


class ScoringTier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier: DispositionTier
    min_score: float
    label: str
    guidance: str


class ScoringConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")  # tolerates the JSON's description field

    version: str
    tiers: list[ScoringTier] = Field(min_length=1)
