"""The investigator (architecture-v2 §16) — the fifth agent.

A tool-using loop over read-only lookups, answering one named officer's
question. The trade that makes it safe to let loose: it can search freely,
iterate, and use tools — **in exchange for never minting a Finding**. Its
output is an InvestigationAnswer plus Observations: unscored, uncitable by
the drafting agent, surfaced to the human who asked. If the officer wants an
insight turned into a scored verdict, a specialist gets dispatched and a
rule decides.

The loop is bounded at MAX_TOOL_CALLS **in this node's code, not in the
prompt** — a runaway model hits the budget wall, gets told to answer with
what it has, and the trail of every call it made rides on the answer as
ToolCallRecords.
"""
from __future__ import annotations

import json
import logging

from langchain_core.messages import ToolMessage

from schemas.dossier import LoadedDossier
from ledger import LedgerStore
from schemas import InvestigationAnswer, Observation, ToolCallRecord

from .llm import (
    briefing_message, get_model, log_cache_usage, ModelDidNotCallTool, parse_observations,
    system_message, THINKING_EFFORT, with_reasoning,
)
from .prompts import assemble
from .tools import execute_tool, result_digest, tools_for

logger = logging.getLogger(__name__)

PROMPT_ID = "INVESTIGATOR"
SYSTEM_PROMPT = assemble(PROMPT_ID).effective

MAX_TOOL_CALLS = 8

_ANSWER_TOOL = with_reasoning({
    "name": "record_investigation_answer",
    "description": "Submit the final answer to the officer's question, with evidence.",
    "input_schema": {
        "type": "object",
        "properties": {
            "answer": {"type": "string", "description": "The answer, grounded in what the tools returned."},
            "cited_evidence": {
                "type": "array", "items": {"type": "string"},
                "description": "The concrete values/ids/dates from tool results the answer rests on.",
            },
            "observations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "note": {"type": "string", "description": "One sentence: the specific thing you noticed."},
                        "cited_evidence": {"type": "string", "description": "The exact field or value it rests on. A reference, not prose."},
                    },
                    "required": ["note", "cited_evidence"],
                },
                "description": "Anything noticed beyond the question that deserves separate attention.",
            },
        },
        "required": ["answer", "cited_evidence", "observations"],
    },
})


def _question_payload(dossier: LoadedDossier, question: str) -> dict:
    scopes = [r.intent_mandate.authorization_scope for r in dossier.runs]
    caps = [s.max_transaction_amount for s in scopes]
    return {
        "question": question,
        "case_id": dossier.dossier.dossier_id,
        "agent_id": dossier.dossier.agent_id,
        "runs": len(dossier.runs),
        "run_ids": [r.run_id for r in dossier.runs],
        "purpose_categories": sorted({s.purpose_category for s in scopes}),
        "transaction_count": len(dossier.transaction_history),
        "mandate_caps": {
            "max_transaction_amount_range": [min(caps), max(caps)] if caps else None,
            "allowed_merchant_categories": sorted({m for s in scopes for m in s.allowed_merchant_categories}),
            "approved_counterparty_count": max((len(s.allowed_counterparties) for s in scopes), default=0),
        },
    }


async def investigate(
    dossier: LoadedDossier,
    question: str,
    *,
    question_id: str,
    store: LedgerStore | None = None,
    model=None,
    thinking_effort: str = THINKING_EFFORT,
    system_prompt: str | None = None,
) -> tuple[InvestigationAnswer, list[Observation]]:
    """Needs a live ANTHROPIC_API_KEY unless `model` is supplied. The
    question is regulator-authored trusted input (same class as a reviewer
    directive); firm-authored strings inside tool results arrive delimited
    by agents/tools.py."""
    model = model or get_model()
    bound = model.bind(
        output_config={"effort": thinking_effort},
        tools=[*tools_for("investigator"), _ANSWER_TOOL],
        tool_choice={"type": "auto"},
    )

    # The system prompt, the tool schemas and the question are re-sent on
    # every turn of the loop below; marked as a breakpoint, each turn after
    # the first reads them from the cache instead of paying for them again.
    messages: list = [
        system_message(system_prompt or SYSTEM_PROMPT),
        briefing_message(_question_payload(dossier, question)),
    ]
    trail: list[ToolCallRecord] = []
    # Hard turn ceiling on top of the tool budget: a model that keeps trying
    # refused lookups instead of answering must terminate with a clear error,
    # not spin. Budget + a couple of refusal turns + the answer turn.
    max_turns = MAX_TOOL_CALLS + 3

    for _turn in range(max_turns):
        response = await bound.ainvoke(messages)

        answer_call = next(
            (c for c in response.tool_calls if c["name"] == "record_investigation_answer"), None
        )
        if answer_call is not None:
            args = answer_call["args"]
            answer = InvestigationAnswer(
                case_id=dossier.dossier.dossier_id,
                question_id=question_id,
                question=question,
                answer=args.get("answer", ""),
                cited_evidence=[str(e) for e in args.get("cited_evidence", [])],
                tool_calls=trail,
            )
            observations = parse_observations(
                args.get("observations", []), case_id=dossier.dossier.dossier_id, agent="investigator",
            )
            return answer, observations

        lookup_calls = [c for c in response.tool_calls if c["name"] != "record_investigation_answer"]
        if not lookup_calls:
            raise ModelDidNotCallTool(
                "Investigator ended its turn without calling any tool — neither a "
                "lookup nor record_investigation_answer."
            )

        messages.append(response)
        for call in lookup_calls:
            if len(trail) >= MAX_TOOL_CALLS:
                # The wall, in code: refuse the call, tell it to answer.
                messages.append(ToolMessage(
                    content=json.dumps({
                        "error": f"tool budget of {MAX_TOOL_CALLS} calls exhausted",
                        "instruction": "Answer now with record_investigation_answer using what you have.",
                    }),
                    tool_call_id=call["id"],
                ))
                continue
            try:
                result = execute_tool("investigator", call["name"], call["args"], dossier=dossier, store=store)
            except Exception as exc:
                logger.warning("Investigator tool %s failed: %s", call["name"], exc)
                result = {"error": str(exc)}
            trail.append(ToolCallRecord(
                tool=call["name"], arguments=call["args"] or {}, result_digest=result_digest(result),
            ))
            messages.append(ToolMessage(content=json.dumps(result, ensure_ascii=True), tool_call_id=call["id"]))

    raise ModelDidNotCallTool(
        f"Investigator did not produce a final answer within {max_turns} turns "
        f"({len(trail)}/{MAX_TOOL_CALLS} tool calls spent)."
    )
