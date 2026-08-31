"""Shared LangChain-based Anthropic model factory.

Rewritten from a raw `anthropic.Anthropic()` SDK client to
`langchain_anthropic.ChatAnthropic` specifically so CopilotKit's AG-UI
LangGraph adapter can automatically stream thinking/reasoning content to
the frontend: that streaming rides LangChain's own async callback/event
system, which only fires for LangChain-native model calls, not raw SDK
calls — confirmed against the official AG-UI LangGraph example
(agentic_chat_reasoning) before rewriting anything here. Every reasoning
call is `async`/`ainvoke()` for the same reason.

`anthropic` is pinned to 0.125.0 (not >=1.0.0) — no published
langchain-anthropic release yet supports the anthropic>=1.0.0 SDK line,
confirmed via a real dependency-resolution failure, not assumed. All the
functionality this project relies on (adaptive thinking, `output_config`
effort, tool calling) is present at this version — verified with a live call.

`model=None` is the injection point every reasoning function exposes
(same role `client=None` played before): tests pass a duck-typed fake with
an async `ainvoke()` and a `bind()` returning itself, without a live key
or network access.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

from schemas import Observation, ObservationAgent

logger = logging.getLogger(__name__)

# Loaded once at import time (not inside get_model()) so a test can
# monkeypatch os.environ afterward without a later call silently
# re-populating it from the file.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DEFAULT_MODEL = "claude-sonnet-5"
THINKING_EFFORT = "high"


class LLMUnavailable(RuntimeError):
    """Raised when a live call is attempted with no API key configured."""


def get_model(*, model: str = DEFAULT_MODEL) -> ChatAnthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise LLMUnavailable(
            "ANTHROPIC_API_KEY is not set. Every agent's deterministic floor "
            "(run()) works fine without one — this is only needed for review()'s LLM passes."
        )
    return ChatAnthropic(model=model, thinking={"type": "adaptive"})


class ModelDidNotCallTool(RuntimeError):
    """The model responded without calling the required tool."""


def get_tool_call(response, tool_name: str) -> dict:
    """The args dict from the first tool call matching `tool_name` in
    `response.tool_calls` (LangChain's normalized list — no more manually
    scanning raw content blocks for tool_use vs. thinking vs. text)."""
    for call in response.tool_calls:
        if call["name"] == tool_name:
            return call["args"]
    raise ModelDidNotCallTool(
        f"Model response did not include a call to {tool_name!r}. "
        f"tool_calls received: {response.tool_calls}."
    )


# Appended to a reasoning module's base system prompt on an escalation
# round (PLAN item 9's "re-dispatch capped at 1 extra round when a
# specialist is ambiguous/under-evidenced"). The trigger for escalation is
# exactly the existence of unresolved Observations from round 1 — that's
# the whole reason Observation is a separate, lower-confidence type in the
# first place. This round asks the model to resolve what it already
# raised, not go looking for new ambiguity.
ESCALATION_ADDENDUM = """

This is an escalation round. In the previous round, a specialist raised the following \
open observation(s) that were not resolved into a firm finding — you are being asked to \
look again, specifically at these, with fresh attention and (if relevant) any new context \
provided below. For each one: either explain concretely why it now warrants being raised \
as a genuine, citable finding, or explicitly state you are dropping it as not actually \
worth flagging. Do not raise brand-new open-ended observations this round beyond resolving \
what's listed — this round is about resolving existing ambiguity, not finding more of it.

Observation(s) to resolve:
{observations}"""


def format_escalation_addendum(prior_observations: list) -> str:
    lines = "\n".join(f"- ({o.agent}) {o.note} [evidence: {o.cited_evidence}]" for o in prior_observations)
    return ESCALATION_ADDENDUM.format(observations=lines)


# Appended when a *human* case officer sends the case back for a directed
# second look (PLAN item 13's re-analysis loop). Different trigger, same
# containment as the escalation addendum: the instruction is regulator-
# authored (trusted-principal input — never firm text), delimited, and the
# output remains schema-constrained via the same tool the agent always uses.
REVIEWER_ADDENDUM = """

A named human case officer has reviewed this case's findings and is sending it back to you \
for a directed second look. Their instruction:

<reviewer_instruction>
{instructions}
</reviewer_instruction>

Address this instruction directly and concretely against the data you are given. If your \
judgment changes as a result, reflect that in your normal structured output; if it does not, \
say why in the relevant explanation/observation rather than ignoring the instruction."""


def format_reviewer_addendum(instructions: str) -> str:
    return REVIEWER_ADDENDUM.format(instructions=instructions)


def parse_observations(
    raw: list, *, case_id: str, agent: ObservationAgent, note_key: str = "note", cited_key: str = "cited_evidence"
) -> list[Observation]:
    """Builds `Observation`s from a tool call's array field, skipping (and
    logging) any element that doesn't match the schema instead of crashing
    the whole node.

    `tool_choice` on every reasoning call is `{"type": "auto"}`, not
    forced — Anthropic's own thinking modes require that — so schema
    adherence on a tool call's arguments is a strong prior, not a
    guarantee. A single non-conforming element (e.g. a bare string instead
    of `{note, cited_evidence}`) reaching a raw `o["note"]` inside a list
    comprehension crashed the entire node with an opaque `TypeError`,
    confirmed live: KYA's `record_observations` returned one such element,
    which crashed the graph run, which crashed the FastAPI stream, which
    crashed the Node CopilotKit proxy reading it. An open-ended-reasoning
    tool's array field is exactly where a model is most likely to drift
    from its schema, so this is the one shape parsed defensively across
    every reasoning module rather than validated once and trusted forever.
    """
    observations = []
    for entry in raw:
        if not isinstance(entry, dict) or note_key not in entry or cited_key not in entry:
            logger.warning(
                "Skipping malformed observation from %s for case %s: expected an object with "
                "%r/%r, got %r",
                agent, case_id, note_key, cited_key, entry,
            )
            continue
        observations.append(Observation(case_id=case_id, agent=agent, note=entry[note_key], cited_evidence=entry[cited_key]))
    return observations
