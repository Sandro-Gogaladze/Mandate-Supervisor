"""The skill registry and the mandatory floor (architecture-v2 §13).

The orchestrator selects work by skill — semantic matching by a model, which
is allowed to be creative because the floor is not: `enforce_skill_floor()`
is a deterministic function that can only ADD. On pass 1, Mandate and KYA
run whatever the orchestrator proposed and whatever any prompt said; Log and
Drift are added whenever each has enough history to say anything (their
minimums differ — see pipeline/dispatch.py's module docstring for why the
single "30 tx" number was split per agent).

Adding a sixth specialist later means adding a Skill entry here, not editing
a routing function.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ingestion.normalize import IngestedCase
from registry.loader import load_drift_ruleset
from schemas import Ruleset, typed_params


class Skill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str
    agent: str
    # What the orchestrator matches a situation against — written for a
    # model reader, so it says what the skill answers, not how it works.
    description: str
    produces: Literal["finding", "observation"]
    # Declarative data-availability note (shown to the orchestrator);
    # enforcement is `eligible()` below, in code.
    requires: dict = Field(default_factory=dict)
    context_blocks: list[str] = Field(default_factory=list)


SKILLS: dict[str, Skill] = {
    skill.skill_id: skill
    for skill in [
        Skill(
            skill_id="mandate.review",
            agent="mandate",
            description=(
                "Check this specific transaction against the human-signed Intent: "
                "caps, merchant category, counterparty, currency, validity window, "
                "chain-hash integrity, and whether the agent's cart semantically "
                "matches what the human actually asked for."
            ),
            produces="finding",
            context_blocks=["mandate_canonical"],
        ),
        Skill(
            skill_id="kya.review",
            agent="kya",
            description=(
                "Verify the agent's identity credential: Ed25519 signatures, issuer "
                "trust and revocation, delegation chain to an accountable human, "
                "capabilities and consent — plus an open look for anything the fixed "
                "rules would not catch (impersonation, structural oddities)."
            ),
            produces="finding",
            context_blocks=["kya_canonical"],
        ),
        Skill(
            skill_id="log.analyze",
            agent="log",
            description=(
                "Judge the transaction PATTERN: structuring under a reporting "
                "threshold, counterparty concentration relative to the mandate's own "
                "scope, and velocity bursts — over pre-computed statistics."
            ),
            produces="finding",
            requires={"min_transactions": 1},
            context_blocks=["log_canonical"],
        ),
        Skill(
            skill_id="drift.analyze",
            agent="drift",
            description=(
                "Compare recent behaviour against the agent's own baseline window: "
                "amount z-score, counterparty and category mix PSI, frequency shift."
            ),
            produces="finding",
            requires={"min_transactions": "drift ruleset min_total_transactions (default 30)"},
            context_blocks=["drift_canonical"],
        ),
        Skill(
            skill_id="investigator.lookup",
            agent="investigator",
            description=(
                "Answer an open question about this case with read-only lookups: "
                "transactions, counterparty profiles, issuer records, rule text, "
                "recomputed statistics. Produces unscored observations, never a "
                "rule verdict — dispatch a specialist for that."
            ),
            produces="observation",
            context_blocks=["case_record_summary"],
        ),
    ]
}

# Canonical display/dispatch order — deterministic output ordering everywhere.
_SKILL_ORDER = ["mandate.review", "kya.review", "log.analyze", "drift.analyze", "investigator.lookup"]

SPECIALIST_SKILLS_BY_AGENT = {
    "mandate": "mandate.review",
    "kya": "kya.review",
    "log": "log.analyze",
    "drift": "drift.analyze",
}


def skill_catalog() -> list[Skill]:
    return [SKILLS[sid] for sid in _SKILL_ORDER]


def _drift_minimum(drift_ruleset: Ruleset | None) -> int:
    drift_ruleset = drift_ruleset or load_drift_ruleset()
    rule = next(
        (r for r in drift_ruleset.rules if r.type == "behavioral_drift_detected" and r.status == "active"),
        None,
    )
    return typed_params(rule).min_total_transactions if rule else 30


def enforce_skill_floor(
    selected: list[str],
    case: IngestedCase,
    *,
    pass_number: int = 1,
    drift_ruleset: Ruleset | None = None,
) -> list[str]:
    """The deterministic validator. Can only ADD — never silently drop a
    skill the orchestrator proposed. Applies on pass 1 only: a directed or
    investigative pass targets exactly what the human or orchestrator named,
    because coverage was already guaranteed when the case first arrived."""
    unknown = [s for s in selected if s not in SKILLS]
    if unknown:
        raise ValueError(f"unknown skill id(s): {unknown} — the registry is {sorted(SKILLS)}")

    result = set(selected)
    if pass_number == 1:
        result |= {"mandate.review", "kya.review"}  # mandatory, no exceptions
        tx_count = len(case.case.transaction_history)
        if tx_count > 0:
            result.add("log.analyze")
        if tx_count >= _drift_minimum(drift_ruleset):
            result.add("drift.analyze")
    return [sid for sid in _SKILL_ORDER if sid in result]
