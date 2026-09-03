import pytest

# PARKED — migration-plan.md Phase 2/3.
#
# These cover the investigator, which is real and still wanted. They are parked because
# their FIXTURE is gone: every one built its case from data/cases/*.json, and
# the corpus is now two dossiers with a different shape.
#
# Parked rather than deleted, and loudly rather than quietly: the logic under
# test did not stop mattering, and a silently shrinking suite is how a
# migration loses coverage nobody notices. Each comes back when the pipeline
# consumes a Dossier and a dossier fixture exists to replace the case one.
pytestmark = pytest.mark.skip(reason="fixture removed with the case corpus — migration Phase 2/3")

"""Stage 9 — the investigator's bounded tool loop (architecture-v2 §16).

FakeChatModel keys canned responses on the single bound tool, which doesn't
fit a many-tool loop — so this file uses a small scripted fake that pops one
response per model turn.
"""
from __future__ import annotations

import pytest

from agents.investigator import MAX_TOOL_CALLS, investigate
from agents.llm import ModelDidNotCallTool
from data.loader import CASES_DIR
from ingestion.normalize import build_verification_context, normalize_case
from schemas import Finding, InvestigationAnswer

_CTX = build_verification_context()


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
        if not self.turns:
            calls = []
        else:
            calls = self.turns.pop(0)

        class Msg:
            tool_calls = [
                {"name": name, "args": args, "id": f"call_{i}", "type": "tool_call"}
                for i, (name, args) in enumerate(calls)
            ]
            content = []

        return Msg()


def _case(name: str = "case-006-drift.json"):
    return normalize_case(CASES_DIR / name, _CTX)


_FINAL = ("record_investigation_answer", {
    "answer": "MER-BEF-005 first appears 2026-07-11 and now dominates spend.",
    "cited_evidence": ["17 transactions", "first_seen 2026-07-11"],
    "observations": [
        {"note": "New MCC 4789 sits outside the fuel/service pattern.", "cited_evidence": "mccs [4789]"},
    ],
})


async def test_investigates_with_tools_and_returns_a_trailed_answer() -> None:
    fake = ScriptedFake([
        [("get_counterparty_profile", {"counterparty_id": "MER-BEF-005"})],
        [("get_transactions", {"counterparty_id": "MER-BEF-005"})],
        [_FINAL],
    ])
    answer, observations = await investigate(
        _case(), "When did Batumi Express Freight first appear?", question_id="Q-1", model=fake,
    )
    assert isinstance(answer, InvestigationAnswer)
    assert [t.tool for t in answer.tool_calls] == ["get_counterparty_profile", "get_transactions"]
    assert all(t.result_digest.startswith("sha256:") for t in answer.tool_calls)
    assert answer.question_id == "Q-1"
    (obs,) = observations
    assert obs.agent == "investigator"


async def test_never_produces_a_finding() -> None:
    fake = ScriptedFake([[_FINAL]])
    answer, observations = await investigate(_case(), "q", question_id="Q-1", model=fake)
    for out in [answer, *observations]:
        assert not isinstance(out, Finding)
    # and structurally: the observation type carries no rule_id/severity at all
    assert not hasattr(observations[0], "rule_id")
    assert not hasattr(observations[0], "severity_weight")


async def test_loop_stops_at_the_tool_budget_enforced_in_code() -> None:
    # a model that keeps trying lookups: only 8 execute; refused calls get
    # the budget message; the final answer still lands within the turn ceiling
    hungry_turns = [[("get_transactions", {})] for _ in range(10)] + [[_FINAL]]
    fake = ScriptedFake(hungry_turns)
    answer, _ = await investigate(_case(), "q", question_id="Q-1", model=fake)
    assert len(answer.tool_calls) == MAX_TOOL_CALLS


async def test_model_that_never_answers_terminates_with_a_clear_error() -> None:
    fake = ScriptedFake([[("get_transactions", {})] for _ in range(40)])
    with pytest.raises(ModelDidNotCallTool, match="did not produce a final answer"):
        await investigate(_case(), "q", question_id="Q-1", model=fake)


async def test_tool_failure_is_fed_back_not_fatal() -> None:
    fake = ScriptedFake([
        [("get_counterparty_profile", {})],  # missing required arg → impl raises → error result
        [_FINAL],
    ])
    answer, _ = await investigate(_case(), "q", question_id="Q-1", model=fake)
    assert [t.tool for t in answer.tool_calls] == ["get_counterparty_profile"]
    # the error went back to the model as a tool message, not up as a crash
    import json
    last_turn_messages = fake.messages_log[-1]
    tool_msgs = [m for m in last_turn_messages if getattr(m, "tool_call_id", None)]
    assert "error" in json.loads(tool_msgs[-1].content)
