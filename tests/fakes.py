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
