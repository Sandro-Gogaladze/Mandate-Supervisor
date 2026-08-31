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

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from ingestion.normalize import IngestedCase
from ledger import LedgerStore
from schemas import InvestigationAnswer, Observation, ToolCallRecord

from .llm import THINKING_EFFORT, ModelDidNotCallTool, get_model, parse_observations
from .prompts import assemble
from .tools import execute_tool, result_digest, tools_for

logger = logging.getLogger(__name__)

PROMPT_ID = "INVESTIGATOR"
SYSTEM_PROMPT = assemble(PROMPT_ID).effective

MAX_TOOL_CALLS = 8

_ANSWER_TOOL = {
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
                        "note": {"type": "string"},
                        "cited_evidence": {"type": "string"},
                    },
                    "required": ["note", "cited_evidence"],
                },
                "description": "Anything noticed beyond the question that deserves separate attention.",
            },
        },
        "required": ["answer", "cited_evidence", "observations"],
    },
}


def _question_payload(case: IngestedCase, question: str) -> dict:
    scope = case.case.mandate_chain.intent.authorization_scope
    return {
        "question": question,
        "case_id": case.case.case_id,
        "purpose_category": scope.purpose_category,
        "transaction_count": len(case.case.transaction_history),
        "mandate_caps": {
            "max_transaction_amount": scope.max_transaction_amount,
            "max_cumulative_amount": scope.max_cumulative_amount,
            "allowed_merchant_categories": scope.allowed_merchant_categories,
            "approved_counterparty_count": len(scope.allowed_counterparties),
        },
    }


async def investigate(
    case: IngestedCase,
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

    messages: list = [
        SystemMessage(content=system_prompt or SYSTEM_PROMPT),
        HumanMessage(content=json.dumps(_question_payload(case, question), indent=2)),
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
                case_id=case.case.case_id,
                question_id=question_id,
                question=question,
                answer=args.get("answer", ""),
                cited_evidence=[str(e) for e in args.get("cited_evidence", [])],
                tool_calls=trail,
            )
            observations = parse_observations(
                args.get("observations", []), case_id=case.case.case_id, agent="investigator",
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
                result = execute_tool("investigator", call["name"], call["args"], case=case, store=store)
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
