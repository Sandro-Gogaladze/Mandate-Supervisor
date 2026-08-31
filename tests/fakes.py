"""Shared fake LangChain chat model for tests — duck-types just enough of
the Runnable interface every reasoning module actually uses (`.bind()`,
async `.ainvoke()`) to exercise prompt construction and response parsing
without a live ANTHROPIC_API_KEY or network access.

Every reasoning call in this codebase binds exactly one tool per call and
expects `tool_choice: {"type": "auto"}` — `ainvoke()` picks its canned
response by looking up whichever tool was actually bound for *that* call,
so one `FakeChatModel` instance can stand in for a whole review() (which
binds a different tool per LLM call, e.g. KYA's reasoning then narration)
or a whole graph run (dispatch, all four specialists, escalation).

If the bound tool has no entry in `responses`, `ainvoke()` returns zero
tool calls — simulating "the model didn't call the tool we expected,"
which agents/llm.py::get_tool_call() must turn into a clear error.
"""
from __future__ import annotations


class FakeAIMessage:
    def __init__(self, tool_calls: list[dict]) -> None:
        self.tool_calls = tool_calls
        self.content: list = []


class FakeChatModel:
    """`responses` maps tool_name -> args dict. `call_log`, if given,
    records every tool name actually bound-and-invoked, in order — pass
    the same list across a whole graph run to assert how many times each
    tool was called (e.g. an escalation round re-invoking one agent's
    reasoning a second time).

    `.bind()` returns a new instance representing "this model with these
    tools/config bound," matching LangChain's real `Runnable.bind()`
    semantics — but `last_bind_kwargs`/`last_messages` are stored on
    shared state so the *original* instance a test holds onto still sees
    what the bound copy actually received.
    """

    def __init__(self, responses: dict[str, dict], call_log: list[str] | None = None, _state: dict | None = None) -> None:
        self.responses = responses
        self.call_log = call_log if call_log is not None else []
        self._state = _state if _state is not None else {
            "last_bind_kwargs": None,
            "last_messages": None,
            "messages_by_tool": {},
        }
        self._bound_tool_name: str | None = None

    @property
    def last_bind_kwargs(self) -> dict | None:
        return self._state["last_bind_kwargs"]

    @property
    def last_messages(self) -> list | None:
        return self._state["last_messages"]

    def last_messages_for(self, tool_name: str) -> list | None:
        """The messages sent on the most recent call that bound `tool_name` —
        lets a test assert on one specific agent's prompt (e.g. that a
        reviewer directive reached the Log agent) in a run where many tools
        were called after it."""
        return self._state["messages_by_tool"].get(tool_name)

    def bind(self, **kwargs) -> "FakeChatModel":
        self._state["last_bind_kwargs"] = kwargs
        bound = FakeChatModel(self.responses, self.call_log, self._state)
        tools = kwargs.get("tools") or []
        bound._bound_tool_name = tools[0]["name"] if tools else None
        return bound

    async def ainvoke(self, messages) -> FakeAIMessage:
        self._state["last_messages"] = messages
        tool_name = self._bound_tool_name
        self._state["messages_by_tool"][tool_name] = messages
        self.call_log.append(tool_name)
        if tool_name not in self.responses:
            return FakeAIMessage(tool_calls=[])
        args = self.responses[tool_name]
        # A callable response computes args from the actual messages sent —
        # needed where a static dict can't be right for every case, e.g. the
        # drafting agent's citations must reference whatever finding_ids the
        # case under test really produced (tests/test_pipeline.py).
        if callable(args):
            args = args(messages)
        return FakeAIMessage(tool_calls=[{"name": tool_name, "args": args, "id": f"fake_{tool_name}", "type": "tool_call"}])


# ---------------------------------------------------------------------------
# The comprehensive graph fake: one canned response per tool name used
# anywhere in the triage/drafting graphs. Shared by tests/test_triage_run.py
# and tests/test_drafting_run.py (it used to live in test_pipeline.py).
# ---------------------------------------------------------------------------

import json as _json

CLEAN_VERDICT = {"anomalous": False, "explanation": "n/a", "cited_evidence": "n/a"}


def grounded_draft(messages) -> dict:
    """Payload-aware fake draftsman: cites exactly the finding_ids the case
    actually produced, so grounding passes first try."""
    payload = _json.loads(messages[-1].content)
    ids = [f["finding_id"] for f in payload["findings"]]
    sections = (
        [{"title": "Findings", "body": "See cited findings.", "cited_finding_ids": ids}] if ids else []
    )
    note = "Unverified items for officer review." if payload["unverified_observations"] else None
    return {"overall_assessment": "Review complete.", "sections": sections, "open_observations_note": note}


DEFAULT_GRAPH_RESPONSES = {
    "record_dispatch_plan": {
        "run_mandate": True, "run_kya": True, "run_log": True, "run_drift": True,
        "reasoning": "run everything",
    },
    "record_observations": {"observations": []},
    "write_narration": {"narration": "Nothing to report."},
    "record_log_analysis": {
        "structuring": CLEAN_VERDICT, "concentration": CLEAN_VERDICT,
        "velocity": CLEAN_VERDICT, "other_observations": [],
    },
    "record_drift_analysis": {"drift": CLEAN_VERDICT, "other_observations": []},
    "record_semantic_check": {"consistent": True, "quoted_evidence": "", "explanation": "matches intent"},
    "record_correlations": {"correlations": []},
    "draft_case_report": grounded_draft,
}


def make_graph_fake(overrides: dict | None = None) -> "FakeChatModel":
    return FakeChatModel({**DEFAULT_GRAPH_RESPONSES, **(overrides or {})})
