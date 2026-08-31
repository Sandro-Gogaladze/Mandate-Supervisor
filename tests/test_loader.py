from data.loader import CASES_DIR, load_case_for_pipeline, load_labeled_case, validate_corpus


def test_validate_corpus_reports_no_problems() -> None:
    assert validate_corpus() == []


def test_labeled_case_carries_eval_ground_truth() -> None:
    case = load_labeled_case(CASES_DIR / "case-002-mandate-breaching.json")
    assert case.label == "mandate_breaching"
    assert case.narrative


def test_pipeline_case_strips_label_and_narrative() -> None:
    case = load_case_for_pipeline(CASES_DIR / "case-002-mandate-breaching.json")
    assert case.label is None
    assert case.narrative is None
    # everything else should still be present
    assert case.mandate_chain.intent.intent_mandate_id


def test_qa_notes_do_not_leak_into_the_typed_case() -> None:
    # case-003/004/006/007 carry _*_note annotations in the raw JSON; none of
    # them should survive into the typed model (extra="forbid" would have
    # raised at load time if they had).
    case = load_labeled_case(CASES_DIR / "case-003-broken-chain.json")
    assert not hasattr(case.mandate_chain.payment, "_chain_note")
