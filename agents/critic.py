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
#
# A comma only separates thousands when it sits between groups of exactly
# three digits. `\d[\d,]*` did not check that, so a COMMA-SEPARATED LIST was
# swallowed as one number: KYA wrote `retail codes (5261,5499,5651)` and the
# critic looked for 526154995651, found it nowhere, and reported a correct
# assessment as quoting an unsupported figure. Matching the grouped form
# first and a plain number otherwise reads that list as the four codes it is.
_NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")

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


def _grounded(value: float, context: set[float]) -> bool:
    """Is `value` a figure the context actually carries?

    Exactly, or as the same figure written the other way round. The context
    holds proportions (0.915, 0.17396358…); a specialist writes them as
    percentages (91.5%, 17.4%) because that is how a supervisor reads them.
    Comparing the digits alone called every one of those a fabrication:
    measured live, Log was flagged on 91.5 / 99.5 / 17.4 / 6.3 while the
    context held 0.915, 0.995, 0.17396358 and 0.06317 — four correct claims
    reported as ungrounded, which downgraded Log's assessments to
    inconclusive and blocked the case on a `judgment` gap.

    Tolerance is half a unit in the last place the model actually wrote,
    measured on the scale it wrote in — so a claim of 91.5 is met by 0.9153
    and a claim of 92 by 0.915, while 93 is met by neither. Comparing on the
    claimed scale is what keeps this honest: rounding both sides down to the
    claim's precision on the FRACTION scale collapses 0.915 and 0.995 onto
    the same value, and any two-digit percentage would then match anything.
    """
    if value in context:
        return True
    places = len(f"{value:f}".rstrip('0').partition('.')[2])
    tolerance = 0.5 * 10 ** -places
    return any(abs(known - value) <= tolerance or abs(known * 100 - value) <= tolerance
               for known in context)


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
            for value in sorted(v for v in _numbers_in(_claimed_text(a)) if not _grounded(v, context_numbers)):
                unquoted.append(str(value))
                sources.append(a.assessment_id)

        for observation in observations:
            if observation.agent != agent:
                continue
            checked += 1
            claimed = f"{observation.note} {observation.cited_evidence}"
            for value in sorted(v for v in _numbers_in(claimed) if not _grounded(v, context_numbers)):
                unquoted.append(str(value))
                sources.append(f"observation:{observation.note[:60]}")

        if checked:
            results.append(CriticResult(
                target=agent, checked=checked, passed=not unquoted,
                unquoted_values=unquoted, sources=sources,
            ))
    return results
