"""The specialist's briefing line for the case officer.

Every specialist ends its review with the same second call: a short, plain
statement of what it found and how much it matters. It is written for a
regulator opening the case, not for a developer reading a log — the risk
first, the detail deferred to the findings list.

Two properties are structural, not stylistic:

- **Grounded.** The call is given the specialist's own assessments and
  nothing else — no credential, no runs, no raw firm text. It therefore
  cannot introduce a claim the review did not make, and the injection
  surface stays closed for the one output a human reads first.
- **Shared.** One prompt and one implementation for all eight specialists,
  so the console's voice does not drift agent by agent. What differs
  between them is the evidence, which is in the briefing.

Not wrapped in `with_reasoning()`: the narration *is* prose, and asking a
model to explain its working before writing three sentences pays twice for
the same tokens — and output is what sets a review's wall clock.
"""
from __future__ import annotations

from schemas import Assessment, Observation

from .llm import (
    briefing_message, get_model, get_tool_call, log_cache_usage, system_message, THINKING_EFFORT,
)
from .prompts import assemble

PROMPT_ID = "SPECIALIST-NARRATION"
SYSTEM_PROMPT = assemble(PROMPT_ID).effective

_NARRATION_TOOL = {
    "name": "write_narration",
    "description": "Write the specialist's short briefing line for the case officer.",
    "input_schema": {
        "type": "object",
        "properties": {"narration": {"type": "string"}},
        "required": ["narration"],
    },
}

# What a specialist's line is for, in the officer's language rather than the
# rulebook's. Sent with the briefing so one shared prompt still produces a
# line that reads like it came from the specialist that wrote it.
AGENT_SUBJECT: dict[str, str] = {
    "mandate": "whether each cart and payment stayed inside what the shopper signed",
    "kya": "whether the agent's identity and authority trace to an accountable human",
    "provenance": "whether the inputs this agent's decisions were built from can be trusted",
    "injection": "whether the agent was manipulated by something it read, and through which channel",
    "counterparty": "who actually received the money",
    "consent": "whether the customer was present, saw what they signed, and is worse off",
    "log": "what the wider transaction history reveals",
    "drift": "how this agent's behaviour has changed, and when it started",
    "control_assurance": "whether the controls this institution declared it runs actually did their job",
    "systemic": "what is true across every submission on record that no single one could show",
}


async def narrate(
    agent: str,
    case_id: str,
    assessments: list[Assessment],
    *,
    observations: list[Observation] | None = None,
    model=None,
    thinking_effort: str = THINKING_EFFORT,
    system_prompt: str | None = None,
) -> str:
    """One short briefing line over this specialist's own output. Needs a
    live ANTHROPIC_API_KEY unless `model` is supplied.

    Assessments are what the review established. Observations are what it
    merely noticed — passed too, because the most useful thing a review found
    is sometimes the thing no rule asked about, but in a separate block whose
    every row says so."""
    model = model or get_model()
    bound = model.bind(
        output_config={"effort": thinking_effort},
        tools=[_NARRATION_TOOL],
        tool_choice={"type": "auto"},
    )
    payload = {
        "case_id": case_id,
        "specialist": agent,
        "question": AGENT_SUBJECT.get(agent, ""),
        # Only a breach scores. The split is given rather than left to be
        # inferred, so the line can lead with what actually matters.
        "scoring_breaches": [_row(a) for a in assessments if a.verdict == "breach"],
        "other_outcomes": [_row(a) for a in assessments if a.verdict != "breach"],
        # The open channel's output, kept in its own block and labelled on
        # every row. The officer should hear that a hunch exists — but the
        # line they trust most must not be able to state one as established,
        # so the distinction is carried by the structure, not only the prompt.
        "unverified_observations": [
            {"note": o.note, "cited_evidence": o.cited_evidence, "runs": o.run_refs,
             "status": "unverified — no rule checked this, nothing here is scored"}
            for o in (observations or [])
        ],
    }
    response = await bound.ainvoke([
        system_message(system_prompt or SYSTEM_PROMPT),
        briefing_message(payload),
    ])
    log_cache_usage(response, f"{agent}-narration")
    return get_tool_call(response, "write_narration")["narration"]


def _row(a: Assessment) -> dict:
    return {"rule_id": a.rule_id, "verdict": a.verdict, "confidence": a.confidence,
            "severity": a.severity_assessed, "summary": a.narrative, "runs": a.run_refs}
