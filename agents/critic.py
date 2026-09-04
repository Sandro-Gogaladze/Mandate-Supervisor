"""The critic (architecture-v2 §15.1) — deterministic, no LLM.

Same trick as agents/grounding.py, one step earlier in the pipeline: did the
subagent quote numbers that actually appear in the evidence it was given?
Answerable by value matching against the recorded dispatch context — no
second model judging the first.

Scope: only the model-judged tier is checked — Log's and Drift's
assessments, Mandate's semantic assessment, and observations.
Deterministic-floor assessments quote values straight out of the facts by
construction, and their evidence is the submission itself, not a dispatch
context.

Failures are recorded and surfaced, never suppressed: a false negative in
the critic must not delete a real finding (the officer sees the flag and
judges). Which numbers count is deliberately conservative to avoid noise:
decimals of any size (amounts, PSI, z-scores — always computed values) and
integers >= 100 (amounts, thresholds); small integer counts like "3
payments" are legitimate model phrasing and are not checked.
"""
from __future__ import annotations

import json
import re

from pydantic import BaseModel, ConfigDict, Field

from schemas import Assessment, Observation

# 1,748.10 · 2900 · 5.86 — grouped thousands allowed, sign ignored.
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

_CHECKED_AGENTS = frozenset({"log", "drift"})
_CHECKED_RULES = frozenset({"MND-SEM-01"})


class CriticResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str                  # agent whose output was checked
    checked: int                 # assessments + observations examined
    passed: bool
    unquoted_values: list[str] = Field(default_factory=list)
    # assessment_id / observation note the value came from, aligned with
    # unquoted_values — so the officer sees exactly which claim to re-read.
    sources: list[str] = Field(default_factory=list)


def _numbers_in(text: str) -> set[float]:
    values = set()
    for match in _NUMBER.finditer(text):
        token = match.group(0).replace(",", "")
        try:
            value = float(token)
        except ValueError:  # pragma: no cover - regex precludes this
            continue
        if "." in token or value >= 100:
            values.add(round(value, 4))
    return values


def _claimed_text(a: Assessment) -> str:
    return f"{a.narrative} {a.severity_rationale or ''} {a.subject or ''}"


def check_evidence_grounding(
    assessments: list[Assessment],
    observations: list[Observation],
    contexts_by_agent: dict[str, dict],
) -> list[CriticResult]:
    """One result per agent that both produced model-judged output and has a
    recorded dispatch context. An agent with no context on record cannot be
    checked (nothing was dispatched through the composer) and is skipped
    rather than vacuously passed or failed."""
    results: list[CriticResult] = []
    from registry.loader import load_all_rulesets
    judged_rules = _CHECKED_RULES | {r.rule_id for rs in load_all_rulesets().values()
                                    for r in rs.rules if r.evaluation == "judged"}
    for agent, context in contexts_by_agent.items():
        context_numbers = _numbers_in(json.dumps(context, ensure_ascii=True))
        checked = 0
        unquoted: list[str] = []
        sources: list[str] = []

        for a in assessments:
            if a.agent != agent:
                continue
            if agent not in _CHECKED_AGENTS and a.rule_id not in judged_rules:
                continue
            checked += 1
            for value in sorted(_numbers_in(_claimed_text(a)) - context_numbers):
                unquoted.append(str(value))
                sources.append(a.assessment_id)

        for observation in observations:
            if observation.agent != agent:
                continue
            checked += 1
            claimed = f"{observation.note} {observation.cited_evidence}"
            for value in sorted(_numbers_in(claimed) - context_numbers):
                unquoted.append(str(value))
                sources.append(f"observation:{observation.note[:60]}")

        if checked:
            results.append(CriticResult(
                target=agent, checked=checked, passed=not unquoted,
                unquoted_values=unquoted, sources=sources,
            ))
    return results
