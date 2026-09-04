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
