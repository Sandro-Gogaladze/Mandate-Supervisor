"""agents/llm.py::parse_observations — born from a live crash (PLAN item 10
UI work): KYA's record_observations tool returned one non-conforming
element in its `observations` array (tool_choice is "auto", not forced, so
schema adherence is a strong prior, not a guarantee), and a raw
`o["note"]` inside a list comprehension turned that into an unhandled
TypeError that crashed the whole graph run."""
from __future__ import annotations

import logging

from agents.llm import parse_observations


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
