"""agents/llm.py::parse_observations — born from a live crash (PLAN item 10
UI work): KYA's record_observations tool returned one non-conforming
element in its `observations` array (tool_choice is "auto", not forced, so
schema adherence is a strong prior, not a guarantee), and a raw
`o["note"]` inside a list comprehension turned that into an unhandled
TypeError that crashed the whole graph run."""
from __future__ import annotations

import logging

import agents.llm as llm
from agents.llm import parse_observations


def test_live_model_is_configured_to_stream(monkeypatch):
    """The AG-UI adapter cannot invent deltas from a buffered model call."""
    captured = {}

    class StubChatAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(llm, "ChatAnthropic", StubChatAnthropic)

    llm.get_model()

    assert captured["streaming"] is True
    assert captured["thinking"] == {"type": "adaptive"}
    assert captured["max_tokens"] == 16000


def test_parses_well_formed_entries():
    raw = [
        {"note": "first", "cited_evidence": "field a"},
        {"note": "second", "cited_evidence": "field b"},
    ]
    observations = parse_observations(raw, case_id="CASE-1", agent="log")
    assert [o.note for o in observations] == ["first", "second"]
    assert [o.cited_evidence for o in observations] == ["field a", "field b"]
    assert all(o.case_id == "CASE-1" and o.agent == "log" for o in observations)


def test_skips_non_dict_entry_instead_of_crashing(caplog):
    # The exact shape of the live crash: a bare string among otherwise
    # well-formed elements.
    raw = [
        {"note": "kept", "cited_evidence": "fine"},
        "a malformed bare string element",
    ]
    with caplog.at_level(logging.WARNING):
        observations = parse_observations(raw, case_id="CASE-2", agent="kya")
    assert [o.note for o in observations] == ["kept"]
    assert "malformed" in caplog.text.lower()


def test_skips_entry_missing_required_key():
    raw = [{"note": "no evidence field here"}]
    assert parse_observations(raw, case_id="CASE-3", agent="drift") == []


def test_custom_cited_key_for_kya_schema():
    # kya_reasoning.py's tool schema names the field "cited_field", not
    # "cited_evidence" — parse_observations must honor that override.
    raw = [{"note": "n", "cited_field": "f"}]
    observations = parse_observations(raw, case_id="CASE-4", agent="kya", cited_key="cited_field")
    assert observations[0].cited_evidence == "f"


def test_empty_input_returns_empty_list():
    assert parse_observations([], case_id="CASE-5", agent="mandate") == []


# --------------------------------------------------------------- caching
# Prompt caching fails silently: a broken prefix raises nothing, it just
# costs money. These lock the two things that can quietly stop working —
# the breakpoints being present, and langchain-anthropic still carrying
# them through to the wire shape Anthropic reads.


def test_the_system_prompt_and_the_briefing_each_carry_a_breakpoint():
    system = llm.system_message("You are the KYA specialist.")
    briefing = llm.briefing_message({"dossier_id": "D-1", "runs": []})

    assert system.content == [{"type": "text", "text": "You are the KYA specialist.",
                               "cache_control": {"type": "ephemeral"}}]
    assert briefing.content[0]["cache_control"] == {"type": "ephemeral"}
    assert llm.message_text(briefing) == '{\n  "dossier_id": "D-1",\n  "runs": []\n}'


def test_a_volatile_payload_can_opt_out_of_a_breakpoint():
    """The orchestrator's payload changes every turn; a breakpoint after
    volatile bytes only ever pays the write premium."""
    assert "cache_control" not in llm.briefing_message({"request": "run it"}, cache=False).content[0]


def test_langchain_carries_the_breakpoints_through_to_the_wire_shape():
    from langchain_anthropic.chat_models import _format_messages

    system, messages = _format_messages([
        llm.system_message("frozen instructions"),
        llm.briefing_message({"evidence": "…"}),
    ])

    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert messages[0]["content"][0]["cache_control"] == {"type": "ephemeral"}


def test_message_text_reads_both_shapes():
    from langchain_core.messages import HumanMessage

    assert llm.message_text(HumanMessage(content="plain")) == "plain"
    assert llm.message_text(llm.system_message("blocked")) == "blocked"
