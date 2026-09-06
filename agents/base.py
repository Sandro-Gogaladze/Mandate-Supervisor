"""Common specialist contract (migration Phase 2): dossier + ruleset in,
facts and assessments out.

Three methods, kept structurally separate on purpose:

- `run()` — the deterministic floor. Every computable rule the agent owns,
  as `Fact`s, over the whole dossier. No model, no key, reproducible.
- `assess()` — the floor's meaning, mechanically: one `breach` assessment
  per breached rule (`explained` where the firm's own control contained it),
  one `concern` per block the submission did not carry.
- `review()` — `run()` + `assess()` + the agent's one contained model call,
  returning a `SpecialistReview`. Needs a live key unless a model is
  injected.

`ruleset` is `Ruleset | None` — taking it as an argument, rather than each
agent loading its own, is what lets the policy sandbox run the same agent
against a draft ruleset without swapping any agent code. `evidence` is what
intake established (signatures, registries, shared statistics); an agent may
use it to avoid recomputing, never as a substitute for its own rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from schemas import Assessment, ControlPosture, EvidencePack, Fact, Observation, Ruleset
from schemas.dossier import LoadedDossier

from .assess import contained_runs, data_gap_assessments, floor_assessments


@dataclass
class SpecialistReview:
    facts: list[Fact]
    assessments: list[Assessment]
    observations: list[Observation] = field(default_factory=list)
    narration: str | None = None
    insufficient_baseline: bool = False
    # Control Assurance's second axis on a finding.
    postures: list[ControlPosture] = field(default_factory=list)


class SpecialistAgent(Protocol):
    name: str

    def run(self, dossier: LoadedDossier, ruleset: Ruleset | None, *,
            evidence: EvidencePack | None = None) -> list[Fact]: ...

    def assess(self, facts: list[Fact], ruleset: Ruleset | None,
               dossier: LoadedDossier) -> list[Assessment]: ...


def scoped(dossier: LoadedDossier, run_scope: list[str] | None) -> LoadedDossier:
    """The dossier narrowed to `run_scope` — empty or None means the whole
    submission (round 1). Round 2 hands a specialist only the runs the
    officer's question concerns."""
    if not run_scope:
        return dossier
    wanted = set(run_scope)
    known = {r.run_id for r in dossier.runs}
    if wanted - known:
        raise ValueError(f"unknown run scope: {sorted(wanted - known)}")
    intents = {r.intent_mandate.intent_mandate_id for r in dossier.runs if r.run_id in wanted}
    related = {r.run_id for r in dossier.runs if r.run_id not in wanted
               and r.intent_mandate.intent_mandate_id in intents}
    return dossier.model_copy(update={
        "runs": [r for r in dossier.runs if r.run_id in wanted],
        "transaction_history": [t for t in dossier.transaction_history if t.run_ref in wanted],
        "raw_runs": {k: v for k, v in dossier.raw_runs.items() if k in wanted},
        "related_transactions": [t for t in dossier.transaction_history if t.run_ref in related],
        "related_runs": [r for r in dossier.runs if r.run_id not in wanted
                         and r.intent_mandate.intent_mandate_id in intents],
        "ground_truth": None,
    })


async def narrated(review: SpecialistReview, agent: str, dossier: LoadedDossier, *,
                   model=None, prompts: dict | None = None, narrate: bool = True) -> SpecialistReview:
    """The second call every specialist ends on: the briefing line an officer
    reads first, over this specialist's own assessments and nothing else.

    Skipped when there is nothing to narrate — a specialist that could not run
    should say nothing rather than produce prose about an empty list.
    """
    if not narrate or not review.assessments:
        return review
    from .narration import narrate as _narrate
    from .prompts import effective_text

    review.narration = await _narrate(
        agent, dossier.dossier.dossier_id, review.assessments,
        observations=review.observations, model=model,
        system_prompt=effective_text(prompts, "SPECIALIST-NARRATION") if prompts else None)
    return review


def floor(facts: list[Fact], ruleset: Ruleset, dossier: LoadedDossier, *, agent: str,
          round: int = 1) -> list[Assessment]:
    """The mechanical assessments every specialist starts from."""
    return [*floor_assessments(facts, ruleset, agent=agent, round=round,
                               contained=contained_runs(dossier)),
            *data_gap_assessments(facts, agent=agent, round=round)]
