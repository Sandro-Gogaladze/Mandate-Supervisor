"""The skill registry.

The orchestrator selects work by skill — semantic matching by a model. A
skill's description is written for that reader: what the skill answers,
not how it works. Adding a specialist means adding a Skill entry here, not
editing a routing function.

A first pass is comprehensive by code policy: every review skill is selected
without a routing model call. Later officer requests are matched to skills by
the orchestrator model.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field



class Skill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str
    agent: str
    # What the orchestrator matches a situation against — written for a
    # model reader, so it says what the skill answers, not how it works.
    description: str
    produces: Literal["finding", "observation"]
    # Declarative data-availability note (shown to the orchestrator);
    # enforcement is `enforce_skill_floor()` below, in code.
    requires: dict = Field(default_factory=dict)
    context_blocks: list[str] = Field(default_factory=list)


SKILLS: dict[str, Skill] = {
    skill.skill_id: skill
    for skill in [
        Skill(
            skill_id="mandate.review",
            agent="mandate",
            description=(
                "Check every run's cart and payment against the Intent Mandate the shopper "
                "signed for that task: caps, merchant category, counterparty, currency, "
                "validity window, cumulative draw on the mandate, chain-hash integrity."
            ),
            produces="finding",
            context_blocks=["mandate_canonical"],
        ),
        Skill(
            skill_id="kya.review",
            agent="kya",
            description=(
                "Verify the agent's identity credential: Ed25519 signatures, issuer "
                "trust and revocation, delegation chain to an accountable human, the "
                "operator's and agent's register entries, capabilities, lifecycle — plus "
                "an open look for anything the fixed rules would not catch."
            ),
            produces="finding",
            context_blocks=["kya_canonical"],
        ),
        Skill(
            skill_id="log.analyze",
            agent="log",
            description=(
                "Judge the transaction PATTERN across the whole history: structuring under "
                "a reporting threshold, counterparty concentration, velocity bursts — over "
                "pre-computed statistics."
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
                "Answer an open question about this dossier with read-only lookups: "
                "transactions, counterparty profiles, issuer records, rule text, "
                "recomputed statistics. Produces unscored observations, never a "
                "rule verdict — dispatch a specialist for that."
            ),
            produces="observation",
            context_blocks=["case_record_summary"],
        ),
    ]
}

for name, question in {
    "provenance": "Reconcile the declared, observed, registered and deployment versions and tools.",
    "injection": "Did untrusted content redirect the agent, and through which channel?",
    "counterparty": "Who actually received payment, and are they the represented merchant?",
    "consent": "Did the shopper see and authorise this exact purchase; was value distorted?",
    "control_assurance": "After the peer review, did the institution's and operator's controls work?",
    "systemic": "Sweep accepted dossiers for shared dependencies, exposures and attack payloads.",
}.items():
    sid = f"{name}.review"
    SKILLS[sid] = Skill(skill_id=sid, agent=name, description=question, produces="finding",
                        context_blocks=[f"{name}_canonical"])

_SKILL_ORDER = ["mandate.review", "kya.review", "provenance.review", "injection.review",
                "counterparty.review", "consent.review", "log.analyze", "drift.analyze",
                "control_assurance.review", "systemic.review", "investigator.lookup"]

SPECIALIST_SKILLS_BY_AGENT = {
    "mandate": "mandate.review",
    "kya": "kya.review",
    "log": "log.analyze",
    "drift": "drift.analyze",
}
SPECIALIST_SKILLS_BY_AGENT.update({s.agent: s.skill_id for s in SKILLS.values() if s.produces == "finding"})


def skill_catalog() -> list[Skill]:
    return [SKILLS[sid] for sid in _SKILL_ORDER]



# The skills a first pass covers: every reviewing specialist, plus Systemic.
#
# Control Assurance is not dispatched here — the graph runs it after the
# peers, because CTL-EFF-01 needs their findings.
#
# Systemic IS dispatched. Its question ("is this agent part of something
# larger?") is one an officer needs answered while reviewing the case, not
# only when somebody remembers to press a button on another page; a shared
# payee or a correlated rhythm is context for the verdict, not an afterthought
# to it. It is cheap enough to belong here — loading four submissions and
# sweeping them measured 35 ms — and it cannot distort the decision, because
# every portfolio finding is a `concern` and only breaches score.
#
# The cost is O(portfolio) per review: every case re-loads every other case's
# submission. At four dossiers that is nothing; at four hundred it is the
# first thing to make incremental.
REVIEW_SKILLS: tuple[str, ...] = tuple(
    sid for sid in _SKILL_ORDER
    if SKILLS[sid].produces == "finding" and SKILLS[sid].agent != "control_assurance"
)
