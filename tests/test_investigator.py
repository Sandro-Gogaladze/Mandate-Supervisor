"""The investigator's bounded tool loop.

FakeChatModel keys canned responses on the single bound tool, which doesn't
fit a many-tool loop — so this file uses a small scripted fake that pops one
response per model turn.
"""
from __future__ import annotations

import json

import pytest

from agents.investigator import MAX_TOOL_CALLS, investigate
from agents.llm import ModelDidNotCallTool, message_text
from schemas import Finding, InvestigationAnswer


class ScriptedFake:
    """Pops one canned response per ainvoke turn. Each entry is a list of
    (tool_name, args) tool calls returned in that turn."""

    def __init__(self, turns: list[list[tuple[str, dict]]]) -> None:
        self.turns = list(turns)
        self.messages_log: list[list] = []

    def bind(self, **kwargs) -> "ScriptedFake":
        self.bound_tools = [t["name"] for t in kwargs.get("tools", [])]
        return self

    async def ainvoke(self, messages):
        self.messages_log.append(list(messages))
        calls = self.turns.pop(0) if self.turns else []

        class Msg:
            tool_calls = [{"name": name, "args": args, "id": f"call_{i}", "type": "tool_call"}
                          for i, (name, args) in enumerate(calls)]
            content = []

        return Msg()


_FINAL = ("record_investigation_answer", {
    "answer": "MER-QVC-8801 first appears 2026-08-05 and takes the largest share of August.",
    "cited_evidence": ["4 transactions", "first_seen 2026-08-05"],
    "observations": [
        {"note": "Beneficial owner unresolved on the merchant record.", "cited_evidence": "watchlist_flags"},
    ],
})


async def test_investigates_with_tools_and_returns_a_trailed_answer(kst) -> None:
    fake = ScriptedFake([
        [("get_counterparty_profile", {"counterparty_id": "MER-QVC-8801"})],
        [("get_transactions", {"counterparty_id": "MER-QVC-8801"})],
        [_FINAL],
    ])
    answer, observations = await investigate(kst, "When did Quickvale first appear?", question_id="Q-1", model=fake)
    assert isinstance(answer, InvestigationAnswer)
    assert [t.tool for t in answer.tool_calls] == ["get_counterparty_profile", "get_transactions"]
    assert all(t.result_digest.startswith("sha256:") for t in answer.tool_calls)
    assert answer.question_id == "Q-1" and answer.case_id == "DOSSIER-KST-2026-001"
    (obs,) = observations
    assert obs.agent == "investigator"


async def test_the_question_payload_names_runs_never_prompts(kst) -> None:
    fake = ScriptedFake([[_FINAL]])
    await investigate(kst, "q", question_id="Q-1", model=fake)
    payload = json.loads(message_text(fake.messages_log[0][1]))
    assert payload["runs"] == 50 and "RUN-2026-0811-0043" in payload["run_ids"]
    assert not any(r.user_prompt in message_text(fake.messages_log[0][1]) for r in kst.runs)


async def test_never_produces_a_finding(kst) -> None:
    answer, observations = await investigate(kst, "q", question_id="Q-1", model=ScriptedFake([[_FINAL]]))
    for out in [answer, *observations]:
        assert not isinstance(out, Finding)
    assert not hasattr(observations[0], "rule_id") and not hasattr(observations[0], "severity_weight")


async def test_loop_stops_at_the_tool_budget_enforced_in_code(kst) -> None:
    hungry = [[("get_transactions", {})] for _ in range(10)] + [[_FINAL]]
    answer, _ = await investigate(kst, "q", question_id="Q-1", model=ScriptedFake(hungry))
    assert len(answer.tool_calls) == MAX_TOOL_CALLS


async def test_model_that_never_answers_terminates_with_a_clear_error(kst) -> None:
    with pytest.raises(ModelDidNotCallTool, match="did not produce a final answer"):
        await investigate(kst, "q", question_id="Q-1", model=ScriptedFake([[("get_transactions", {})] for _ in range(40)]))


async def test_tool_failure_is_fed_back_not_fatal(kst) -> None:
    fake = ScriptedFake([[("get_counterparty_profile", {})], [_FINAL]])
    answer, _ = await investigate(kst, "q", question_id="Q-1", model=fake)
    assert [t.tool for t in answer.tool_calls] == ["get_counterparty_profile"]
    tool_msgs = [m for m in fake.messages_log[-1] if getattr(m, "tool_call_id", None)]
    assert "error" in json.loads(tool_msgs[-1].content)
