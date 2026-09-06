"""Defensive parsing of a reasoning tool's free-form array fields."""
def test_observation_field_arriving_as_json_text_is_recovered_not_iterated(caplog):
    """A streamed tool call can present the array as the JSON text of one.
    Iterating that yields characters — every real observation lost and one
    warning per character. It is parsed back instead."""
    from agents.llm import parse_observations
    raw = '[{"note": "Issuer name is a near-match.", "cited_evidence": "issuer.issuer_name"}]'
    out = parse_observations(raw, case_id="C1", agent="kya")
    assert [o.note for o in out] == ["Issuer name is a near-match."]


def test_observation_field_that_is_neither_list_nor_json_fails_once(caplog):
    from agents.llm import parse_observations
    with caplog.at_level("WARNING"):
        assert parse_observations("...method\"}]}", case_id="C1", agent="kya") == []
        assert parse_observations({"note": "x"}, case_id="C1", agent="kya") == []
    assert len(caplog.records) == 2, "one warning per bad field, not one per character"


def test_a_collapsed_tool_argument_object_is_reconstructed():
    """Streamed tool arguments are assembled by a partial-JSON parser, and its
    failure has a signature: the whole object collapses into the first key's
    value as a string. Observed live — Drift's verdict was rejected as
    malformed and its reasoning and observations were thrown away with it."""
    from agents.llm import repair_tool_args
    # Verbatim shape of the live failure, trailing brace included: the value
    # is everything that followed `"drift":` in the original arguments.
    collapsed = {"drift": '{"anomalous": true, "explanation": "e"}, '
                          '"reasoning": "r", "other_observations": [{"note": "n", "cited_evidence": "c"}]}'}
    out = repair_tool_args(dict(collapsed))
    assert out["drift"] == {"anomalous": True, "explanation": "e"}
    assert out["reasoning"] == "r"
    assert len(out["other_observations"]) == 1


def test_a_field_that_is_plain_json_text_is_parsed():
    from agents.llm import repair_tool_args
    out = repair_tool_args({"verdicts": '[{"run_id": "RUN-1", "consistent": true}]'})
    assert out["verdicts"] == [{"run_id": "RUN-1", "consistent": True}]


def test_well_formed_arguments_are_left_alone():
    from agents.llm import repair_tool_args
    args = {"drift": {"anomalous": False}, "reasoning": "fine", "note": "not json"}
    assert repair_tool_args(dict(args)) == args


def test_observations_wrapped_in_an_object_are_unwrapped_not_discarded(caplog):
    """KYA's observations arrived as a dict and were dropped entirely."""
    from agents.llm import parse_observations
    wrapped = {"observations": [{"note": "Issuer name is a near-match.",
                                 "cited_evidence": "issuer.issuer_name"}]}
    out = parse_observations(wrapped, case_id="C1", agent="kya")
    assert [o.note for o in out] == ["Issuer name is a near-match."]


def test_a_single_observation_sent_unwrapped_is_accepted():
    from agents.llm import parse_observations
    one = {"note": "n", "cited_evidence": "c"}
    assert len(parse_observations(one, case_id="C1", agent="kya")) == 1


def test_correlations_wrapped_in_an_object_are_unwrapped():
    """The synthesizer had the same dict-instead-of-list failure the
    observation parser did — seen live on a sweep."""
    import asyncio
    from agents.synthesizer import synthesize
    from schemas import Finding

    findings = [Finding(finding_id=f"F{i}", case_id="C1", agent="mandate",
                        type="t", summary="s") for i in (1, 2)]

    class Fake:
        def bind(self, **_): return self
        async def ainvoke(self, _messages):
            class R:
                tool_calls = [{"name": "record_correlations", "args": {"correlations": {
                    "correlations": [{"finding_ids": ["F1", "F2"], "relationship": "same_event",
                                      "explanation": "one event"}]}}}]
            return R()

    out = asyncio.run(synthesize("C1", findings, model=Fake()))
    assert [c.relationship for c in out] == ["same_event"]
