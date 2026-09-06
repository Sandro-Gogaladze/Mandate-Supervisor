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
            "bind_by_tool": {},
        }
        self._bound_tool_name: str | None = None

    @property
    def last_bind_kwargs(self) -> dict | None:
        return self._state["last_bind_kwargs"]

    @property
    def last_messages(self) -> list | None:
        return self._state["last_messages"]

    def bind_kwargs_for(self, tool_name: str) -> dict | None:
        """The bind arguments of the most recent call that bound `tool_name`.

        `last_bind_kwargs` is the last bind of the whole run, which since every
        specialist ends on a narration call is almost never the one a test
        means. This asks for the specific tool — needed to assert that a tool's
        schema grew or shrank with the ruleset it was built from."""
        return self._state["bind_by_tool"].get(tool_name)

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
        if bound._bound_tool_name:
            self._state["bind_by_tool"][bound._bound_tool_name] = kwargs
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

from agents.llm import message_text

CLEAN_VERDICT = {"anomalous": False, "explanation": "n/a", "cited_evidence": "n/a", "transaction_ids": []}
CLEAN_DRIFT = {**CLEAN_VERDICT, "onset_event_ref": None}


def grounded_draft(messages) -> dict:
    """Payload-aware fake draftsman: cites exactly the finding_ids the case
    actually produced, declares the character its cited verdicts add up to,
    and restates the computed score — so grounding passes first try. Derived
    from the payload rather than hardcoded, so it stays a fake of a COMPLIANT
    model instead of a fixture that would sail past a rule it never met."""
    payload = _json.loads(message_text(messages[-1]))
    findings = payload["findings"]
    ids = [f["finding_id"] for f in findings]
    breaches = sum(1 for f in findings if f.get("verdict") == "breach")
    character = ("mixed" if breaches and breaches < len(findings)
                 else "adverse" if breaches else "clear")
    sections = (
        [{"title": "Findings", "body": "See cited findings.", "cited_finding_ids": ids,
          "character": character}] if ids else []
    )
    note = "Unverified items for officer review." if payload["unverified_observations"] else None
    risk = payload.get("risk")
    assessment = (f"Risk score {risk['total']} — tier {risk['tier_label']}. Review complete."
                  if risk else "Review complete.")
    return {"overall_assessment": assessment, "sections": sections, "open_observations_note": note}


def all_consistent(messages) -> dict:
    """Payload-aware fake Mandate: a consistent verdict for every run it was
    shown, so the whole-dossier fidelity call rolls into one `clear`."""
    payload = _json.loads(message_text(messages[-1]))
    return {"verdicts": [
        {"run_id": r["run_id"], "consistent": True, "quoted_evidence": "", "explanation": "matches the request"}
        for r in payload.get("runs", [])
    ]}


def route_default(messages) -> dict:
    """Payload-aware fake orchestrator: a first pass dispatches every skill the
    catalogue marks first_pass, with a one-line briefing each; anything else
    is answered from the record."""
    payload = _json.loads(message_text(messages[-1]))
    if payload.get("first_pass"):
        skills = [s["skill_id"] for s in payload.get("available_skills", []) if s.get("first_pass")]
        return {"reasoning": "A first pass: every review skill, each briefed.",
                "intent": "dispatch", "message_to_officer": f"Running the full review with {len(skills)} specialists.",
                "dispatches": [{"skill": s, "instruction": "", "run_scope": [], "context_blocks": []} for s in skills]}
    return {"reasoning": "The record answers this.", "intent": "reply",
            "message_to_officer": "Nothing to add beyond what is on the record.", "dispatches": []}


def closing_brief(messages) -> dict:
    """Payload-aware fake orchestrator close-out: counts straight from the
    recommendation it was handed, so a test can assert the brief describes the
    same arithmetic the authorisation policy computed."""
    payload = _json.loads(message_text(messages[-1]))
    counts = payload["counts"]
    return {"reasoning": "Reporting what came back.",
            "message_to_officer": f"{counts['adverse_verdicts']} adverse verdicts across "
                                  f"{counts['runs_with_a_breach']} of {counts['runs_filed']} executions; "
                                  f"the policy reached {payload['disposition']}. Open the findings list.",
            "main_risks": [g["rule_id"] for g in payload["hard_gates"]][:3]}


def nothing_acted(messages) -> dict:
    """Payload-aware fake Injection: the agent ignored every flagged item."""
    payload = _json.loads(message_text(messages[-1]))
    return {"verdicts": [{"run_id": r["run_id"], "acted": False, "channel": "none",
                          "explanation": "read and ignored", "cited_evidence": "n/a"}
                         for r in payload.get("flagged_runs", [])],
            "objective_redirected": {"present": False, "explanation": "n/a"},
            "other_observations": []}


DEFAULT_GRAPH_RESPONSES = {
    "route_supervisor_request": route_default,
    # KYA-REG-03 is in force, so a well-behaved model answers its slot. The
    # "no verdict arrived" path has its own unit test; a fake that silently
    # omitted it would turn every graph test into an inconclusive.
    "record_observations": {"observations": [], "classification_fit": {
        "consistent": True, "explanation": "Activity fits a consumer shopping agent.",
        "cited_evidence": "settled_total 12408.55 across 18 counterparties"}},
    "write_narration": {"narration": "Nothing to report."},
    "record_log_analysis": {
        "structuring": CLEAN_VERDICT, "concentration": CLEAN_VERDICT,
        "velocity": CLEAN_VERDICT,
        # The slots the tool grows when LOG-RND-01 and LOG-LIM-01 are in
        # force. A fake that omitted them would turn every graph test into an
        # inconclusive; that path has its own unit test.
        "roundness": CLEAN_VERDICT, "ceiling_probing": CLEAN_VERDICT,
        "other_observations": [],
    },
    "record_drift_analysis": {"drift": CLEAN_DRIFT, "other_observations": []},
    "record_intent_fidelity": all_consistent,
    "record_consent_analysis": {"value_for_money": {"systematic": False, "run_ids": [], "explanation": "n/a",
                                                    "cited_evidence": "n/a"}, "other_observations": []},
    "record_injection_analysis": nothing_acted,
    "record_counterparty_analysis": {"doubtful_payees": [], "identity_explanation": "n/a",
                                     "declines": CLEAN_VERDICT, "other_observations": []},
    "record_provenance_reconciliation": {"reconciled": True, "disagreements": [], "explanation": "n/a",
                                         "other_observations": []},
    "record_correlations": {"correlations": []},
    "record_closing_brief": closing_brief,
    "draft_case_report": grounded_draft,
}


def make_graph_fake(overrides: dict | None = None) -> "FakeChatModel":
    return FakeChatModel({**DEFAULT_GRAPH_RESPONSES, **(overrides or {})})
