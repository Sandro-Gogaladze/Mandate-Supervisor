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

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from schemas import Observation, ObservationAgent

logger = logging.getLogger(__name__)

# Loaded once at import time (not inside get_model()) so a test can
# monkeypatch os.environ afterward without a later call silently
# re-populating it from the file.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DEFAULT_MODEL = "claude-sonnet-5"
# Thinking tokens are output tokens, and output is what sets a review's wall
# clock: at "high" a single specialist's judgement ran 59-155 s and a whole
# first pass took ten minutes. Every judgement here reasons over evidence a
# deterministic floor has already computed and laid out — which cluster,
# which measurement, which run — so the model is interpreting prepared
# numbers rather than deriving them, and that is not work "high" was for.
# Overridable per environment so a specialist that turns out to need more
# can have it without editing code.
THINKING_EFFORT = os.environ.get("MANDATE_THINKING_EFFORT", "low")


class LLMUnavailable(RuntimeError):
    """Raised when a live call is attempted with no API key configured."""


def get_model(*, model: str = DEFAULT_MODEL) -> ChatAnthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise LLMUnavailable(
            "ANTHROPIC_API_KEY is not set. Every agent's deterministic floor "
            "(run()) works fine without one — this is only needed for review()'s LLM passes."
        )
    # max_tokens: the orchestrator writes its working and a briefing per skill,
    # Injection judges every run — the library's default of 1024 would cut
    # a tool call off mid-argument.
    # AG-UI can only relay token/tool-argument deltas that LangChain emits.
    # ChatAnthropic defaults to a buffered response, which made the console
    # receive a complete tool call at the end even though every layer after
    # this one supports streaming.
    return ChatAnthropic(
        model=model,
        thinking={"type": "adaptive"},
        max_tokens=16000,
        streaming=True,
    )


# ---------------------------------------------------------------- caching
#
# Every call an agent makes has the same two parts: a frozen system prompt
# (Anthropic renders the tool schema, then system, then the messages) and
# one JSON briefing. Both are marked as cache breakpoints, so a later call
# whose bytes up to that point are identical — the same dossier reviewed
# again inside the window, a demo re-run, a second pass, a dev loop — reads
# them at ~10% of the input price instead of paying to process them again.
#
# Two things this deliberately does NOT do:
#
# - It does not move the escalation or reviewer addendum out of the system
#   prompt to keep that prefix stable. Instructions reach a specialist
#   through the system turn and evidence reaches it through the human turn;
#   that boundary is a guardrail, not a layout choice. Those rounds change
#   the prefix and miss the cache, and that is the right trade.
# - It does not mark the orchestrator's payload, which carries the officer's
#   request and a record that grows every turn — a breakpoint after volatile
#   bytes only ever pays the write premium and is never read back.
#
# Anthropic's minimum cacheable prefix on claude-sonnet-5 is 1024 tokens: a
# shorter prefix silently does not cache (no error, nothing billed). Several
# system prompts sit near that line, which is why the briefing carries its
# own breakpoint rather than relying on the system one alone.
CACHE_BREAKPOINT = {"type": "ephemeral"}  # 5-minute TTL; a read refreshes it


def system_message(text: str) -> SystemMessage:
    """The system prompt as one cache-marked block."""
    return SystemMessage(content=[{"type": "text", "text": text, "cache_control": CACHE_BREAKPOINT}])


def briefing_message(payload: dict, *, cache: bool = True) -> HumanMessage:
    """The composed context, serialized exactly as it is recorded on the
    dispatch event, as one (by default cache-marked) block."""
    block = {"type": "text", "text": json.dumps(payload, indent=2)}
    if cache:
        block["cache_control"] = CACHE_BREAKPOINT
    return HumanMessage(content=[block])


def message_text(message: BaseMessage) -> str:
    """The text of a message whose content is either a string or the block
    list the helpers above build."""
    if isinstance(message.content, str):
        return message.content
    return "".join(b["text"] for b in message.content
                   if isinstance(b, dict) and b.get("type") == "text")


def log_cache_usage(response, label: str) -> None:
    """What the cache actually did on one call. This is the only ground
    truth that caching still works after a change to prompt assembly — a
    broken prefix costs money silently, it never raises."""
    details = (getattr(response, "usage_metadata", None) or {}).get("input_token_details") or {}
    if not details:
        return
    logger.info("%s: cache read %s, written %s, uncached %s", label,
                details.get("cache_read", 0), details.get("cache_creation", 0),
                (getattr(response, "usage_metadata", None) or {}).get("input_tokens", 0))


# The console shows each specialist's working the way a Claude conversation
# shows thinking. This model returns no thinking text (only a signature), so
# the working is asked for explicitly: the FIRST field of every recording
# tool, written before any verdict, streamed as it is typed. It is the
# model's own reasoning in its own words — not a paraphrase of the output.
# Deliberately short. This used to ask for the working "in full", which was
# right when it was the only visible trace; with adaptive thinking on, that
# working is produced twice — once as thinking, once again here — and both
# halves are output tokens, which is what a review's wall clock is made of.
# What a reviewer needs from this field is the decisive consideration, not a
# transcript: the facts are cited, the runs are named, and the narrative
# carries the claim.
REASONING_HINT = (
    "Your working, briefly: the evidence that decided it and what you weighed against it. "
    "Two or three sentences. Do not restate the evidence you were given or the verdict you "
    "are about to record."
)


def with_reasoning(tool: dict, hint: str = REASONING_HINT) -> dict:
    """The same tool with a required `reasoning` string as its first property.
    If the schema already has one it is moved to the front and re-described."""
    schema = dict(tool["input_schema"])
    props = dict(schema.get("properties", {}))
    props.pop("reasoning", None)
    schema["properties"] = {"reasoning": {"type": "string", "description": hint}, **props}
    required = [r for r in schema.get("required", []) if r != "reasoning"]
    schema["required"] = ["reasoning", *required]
    return {**tool, "input_schema": schema}


def without_reasoning(result: dict) -> dict:
    """A tool result with the working removed — for validators that forbid extras."""
    return {k: v for k, v in result.items() if k != "reasoning"}


class ModelDidNotCallTool(RuntimeError):
    """The model responded without calling the required tool."""


def repair_tool_args(args: dict) -> dict:
    """Undo a streamed-JSON assembly failure before anything reads the args.

    Tool arguments arrive as deltas and are assembled by a partial-JSON
    parser. It can mis-split them, and the failure has a signature: the
    WHOLE argument object collapses into the first key's value as a string,
    so `{"drift": {...}, "reasoning": ..., "other_observations": [...]}`
    comes back as `{"drift": '{...}, "reasoning": ..., "other_observations": [...]}'`.

    That string is not valid JSON on its own, but putting the key back in
    front of it makes it exactly the original object again. Observed live on
    Drift (the verdict was rejected as malformed and the specialist recorded
    inconclusive) and on KYA (observations discarded). Both lost real work
    the model had already done, including — in one case — a correct catch
    that another case's figures had leaked into the evidence.
    """
    for key, value in list(args.items()):
        if not isinstance(value, str) or not value.lstrip().startswith(("{", "[")):
            continue
        for candidate in (value, f'{{"{key}": {value}'):
            try:
                parsed = json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                continue
            if candidate is not value and isinstance(parsed, dict):
                # The reconstruction recovered sibling keys too; prefer it
                # whole rather than patching one field back in.
                logger.warning("Recovered %d tool argument(s) from a collapsed "
                               "%r value", len(parsed), key)
                return {**args, **parsed}
            logger.warning("Parsed tool argument %r from JSON text", key)
            args[key] = parsed
            break
    return args


def get_tool_call(response, tool_name: str) -> dict:
    """The args dict from the first tool call matching `tool_name` in
    `response.tool_calls` (LangChain's normalized list — no more manually
    scanning raw content blocks for tool_use vs. thinking vs. text).

    `invalid_tool_calls` is checked too: LangChain puts a call whose
    arguments failed to parse there, with the raw string. Ignoring it meant a
    recoverable response was reported as "the model did not call the tool"."""
    for call in response.tool_calls:
        if call["name"] == tool_name:
            return repair_tool_args(dict(call["args"]))
    for call in getattr(response, "invalid_tool_calls", None) or []:
        if call.get("name") != tool_name or not call.get("args"):
            continue
        try:
            parsed = json.loads(call["args"])
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if isinstance(parsed, dict):
            logger.warning("Recovered %r from an unparsed tool call", tool_name)
            return repair_tool_args(parsed)
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

    The field itself can also arrive as something other than a list. A
    streamed tool call whose arguments are assembled from deltas can present
    an array as the JSON text of one, and iterating that yields *characters*
    — one "malformed observation" warning per character, and every real
    observation lost. Recover the list where the text parses, and fail once
    and quietly where it does not.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Discarding %s's observations for case %s: the field arrived as text "
                           "that is not JSON (%d chars)", agent, case_id, len(raw))
            return []
    if isinstance(raw, dict):
        # The same streamed-assembly failure repair_tool_args() undoes, one
        # level down: the array arrives wrapped in an object. Unwrap the sole
        # list inside rather than discarding work the model actually did.
        inner = [v for v in raw.values() if isinstance(v, list)]
        if len(inner) == 1:
            logger.warning("Unwrapped %s's observations from an object for case %s",
                           agent, case_id)
            raw = inner[0]
        elif {"note", cited_key} <= set(raw):
            raw = [raw]  # a single observation sent unwrapped
    if not isinstance(raw, list):
        logger.warning("Discarding %s's observations for case %s: expected a list, got %s",
                       agent, case_id, type(raw).__name__)
        return []
    observations = []
    for entry in raw:
        if not isinstance(entry, dict) or note_key not in entry or cited_key not in entry:
            logger.warning(
                "Skipping malformed observation from %s for case %s: expected an object with "
                "%r/%r, got %r",
                agent, case_id, note_key, cited_key, entry,
            )
            continue
        observations.append(Observation(
            case_id=case_id, agent=agent, note=entry[note_key], cited_evidence=entry[cited_key],
            failure_id=entry.get("failure_id"), run_refs=entry.get("run_refs", []),
            transaction_refs=entry.get("transaction_refs", []),
        ))
    return observations
