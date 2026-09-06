"""The synthesizer (architecture-v2 §15.2) — relationships BETWEEN findings.

Additive only. Its output is typed `Correlation` records validated in code:
every finding_id must resolve to a finding that exists, a correlation needs
at least two of them, and scoring never reads any of this
(pipeline/scoring.py's signature is unchanged) — so a bad synthesis cannot
touch the score or the findings, only one display panel.

The value it adds is real and nothing else does it: on case-007, MND-CAP-01,
MND-SEM-02 and MND-SEM-01 are three independent detectors seeing ONE
injected line item. The findings list presents three items; a correlation
says they are one event.
"""
from __future__ import annotations

import json
import logging


from schemas import Correlation, Finding

from .llm import (
    briefing_message, get_model, get_tool_call, log_cache_usage, system_message,
    THINKING_EFFORT, with_reasoning,
)
from .prompts import assemble

logger = logging.getLogger(__name__)

PROMPT_ID = "SYNTHESIZER"
SYSTEM_PROMPT = assemble(PROMPT_ID).effective

_CORRELATIONS_TOOL = with_reasoning({
    "name": "record_correlations",
    "description": "Record zero or more relationships between this case's findings.",
    "input_schema": {
        "type": "object",
        "properties": {
            "correlations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "finding_ids": {
                            "type": "array", "items": {"type": "string"},
                            "description": "At least two finding_id values from the input.",
                        },
                        "relationship": {
                            "type": "string",
                            "enum": ["same_event", "causal", "corroborating", "contradictory"],
                        },
                        "explanation": {"type": "string", "description": "One sentence."},
                    },
                    "required": ["finding_ids", "relationship", "explanation"],
                },
            },
        },
        "required": ["correlations"],
    },
})


def _structured_view(findings: list[Finding]) -> dict:
    return {
        "findings": [
            {
                "finding_id": f.finding_id,
                "agent": f.agent,
                "type": f.type,
                "rule_id": f.rule_id,
                "summary": f.summary,
            }
            for f in findings
        ],
    }


async def synthesize(
    case_id: str,
    findings: list[Finding],
    *,
    model=None,
    thinking_effort: str = THINKING_EFFORT,
    system_prompt: str | None = None,
) -> list[Correlation]:
    """Needs a live ANTHROPIC_API_KEY unless `model` is supplied. Callers
    skip the call entirely below two findings — there is nothing to relate."""
    if len(findings) < 2:
        return []

    model = model or get_model()
    bound = model.bind(
        output_config={"effort": thinking_effort},
        tools=[_CORRELATIONS_TOOL],
        tool_choice={"type": "auto"},
    )

    response = await bound.ainvoke([
        system_message(system_prompt or SYSTEM_PROMPT),
        briefing_message(_structured_view(findings)),
    ])
    log_cache_usage(response, "synthesizer")

    result = get_tool_call(response, "record_correlations")
    real_ids = {f.finding_id for f in findings}

    raw_entries = result.get("correlations", [])
    if isinstance(raw_entries, str):
        try:
            raw_entries = json.loads(raw_entries)
            if isinstance(raw_entries, dict):
                raw_entries = raw_entries.get("correlations", [])
        except json.JSONDecodeError:
            logger.warning("Skipping malformed correlations payload for %s", case_id)
            raw_entries = []
    if isinstance(raw_entries, dict):
        # Same streamed-assembly failure the observation parser handles: the
        # array arrives wrapped in an object. Unwrap the sole list inside
        # rather than discarding work the model actually did.
        inner = [v for v in raw_entries.values() if isinstance(v, list)]
        if len(inner) == 1:
            logger.warning("Unwrapped correlations from an object for %s", case_id)
            raw_entries = inner[0]
        elif {"finding_ids", "relationship"} <= set(raw_entries):
            raw_entries = [raw_entries]  # a single correlation sent unwrapped
    if not isinstance(raw_entries, list):
        logger.warning("Skipping non-list correlations payload for %s: %r", case_id, type(raw_entries).__name__)
        raw_entries = []

    correlations: list[Correlation] = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            logger.warning("Skipping malformed correlation for %s: %r", case_id, entry)
            continue
        cited = entry.get("finding_ids") or []
        invented = [fid for fid in cited if fid not in real_ids]
        if invented:
            # The id-resolution check — the mechanical "cannot invent" rule.
            logger.warning(
                "Dropping correlation for %s citing non-existent finding_id(s) %s", case_id, invented,
            )
            continue
        try:
            correlations.append(Correlation(
                case_id=case_id,
                finding_ids=cited,
                relationship=entry.get("relationship"),
                explanation=entry.get("explanation", ""),
            ))
        except Exception:
            logger.warning("Skipping schema-invalid correlation for %s: %r", case_id, entry)
    return correlations
