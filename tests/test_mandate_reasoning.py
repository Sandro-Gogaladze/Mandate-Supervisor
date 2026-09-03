import pytest

# PARKED — migration-plan.md Phase 2/3.
#
# These cover Mandate's prompt, which is real and still wanted. They are parked because
# their FIXTURE is gone: every one built its case from data/cases/*.json, and
# the corpus is now two dossiers with a different shape.
#
# Parked rather than deleted, and loudly rather than quietly: the logic under
# test did not stop mattering, and a silently shrinking suite is how a
# migration loses coverage nobody notices. Each comes back when the pipeline
# consumes a Dossier and a dossier fixture exists to replace the case one.
pytestmark = pytest.mark.skip(reason="fixture removed with the case corpus — migration Phase 2/3")

import pytest

from agents.llm import ModelDidNotCallTool
from agents.mandate import MandateAgent
from agents.mandate_reasoning import check_cart_reasoning_matches_intent
from data.loader import CASES_DIR
from ingestion.normalize import normalize_case
from registry.loader import load_mandate_ruleset
from schemas import Finding
from tests.fakes import FakeChatModel


def _rule():
    ruleset = load_mandate_ruleset()
    return next(r for r in ruleset.rules if r.type == "cart_reasoning_matches_intent")


async def test_returns_finding_when_inconsistent() -> None:
    case = normalize_case(CASES_DIR / "case-007-prompt-injection.json")
    fake = FakeChatModel({"record_semantic_check": {
        "consistent": False,
        "quoted_evidence": "gift-card top-up of ₾1,200",
        "explanation": "The cart includes a gift-card top-up unrelated to garden/landscaping supplies.",
    }})

    finding = await check_cart_reasoning_matches_intent(case, _rule(), model=fake)

    assert isinstance(finding, Finding)
    assert finding.agent == "mandate"
    assert finding.type == "cart_reasoning_semantic_mismatch"
    assert finding.rule_id == "MND-SEM-01"
    assert finding.severity_weight == 0.85
    assert finding.details["quoted_evidence"] == "gift-card top-up of ₾1,200"


async def test_returns_none_when_consistent() -> None:
    case = normalize_case(CASES_DIR / "case-001-compliant.json")
    fake = FakeChatModel({"record_semantic_check": {
        "consistent": True,
        "quoted_evidence": "",
        "explanation": "Cart matches the grocery-restocking intent.",
    }})

    assert await check_cart_reasoning_matches_intent(case, _rule(), model=fake) is None


async def test_untrusted_line_item_text_is_delimited_in_the_prompt() -> None:
    case = normalize_case(CASES_DIR / "case-007-prompt-injection.json")
    fake = FakeChatModel({"record_semantic_check": {"consistent": False, "quoted_evidence": "x", "explanation": "x"}})

    await check_cart_reasoning_matches_intent(case, _rule(), model=fake)

    payload = fake.last_messages[1].content
    assert "<<<UNTRUSTED_MERCHANT_TEXT>>>" in payload
    assert "<<<END_UNTRUSTED_MERCHANT_TEXT>>>" in payload
    assert "Note to purchasing agent" in payload  # the actual injected text, present but fenced


async def test_model_not_calling_tool_raises_clearly() -> None:
    case = normalize_case(CASES_DIR / "case-001-compliant.json")
    fake = FakeChatModel({"wrong_tool": {"consistent": True}})

    with pytest.raises(ModelDidNotCallTool):
        await check_cart_reasoning_matches_intent(case, _rule(), model=fake)


async def test_review_merges_semantic_finding_into_the_same_findings_list() -> None:
    case = normalize_case(CASES_DIR / "case-001-compliant.json")
    ruleset = load_mandate_ruleset()
    fake = FakeChatModel({"record_semantic_check": {
        "consistent": False, "quoted_evidence": "x", "explanation": "hypothetical mismatch",
    }})

    findings = await MandateAgent().review(case, ruleset, model=fake)

    assert any(f.type == "cart_reasoning_semantic_mismatch" for f in findings)
    assert all(isinstance(f, Finding) for f in findings)  # merged, no separate Observation-like type


async def test_review_skips_semantic_check_when_rule_is_draft() -> None:
    case = normalize_case(CASES_DIR / "case-001-compliant.json")
    ruleset = load_mandate_ruleset().model_copy(deep=True)
    for rule in ruleset.rules:
        if rule.type == "cart_reasoning_matches_intent":
            rule.status = "draft"

    # no model passed at all — if the code tried to call the LLM, this
    # would raise LLMUnavailable/attempt a real network call and fail
    findings = await MandateAgent().review(case, ruleset)

    assert not any(f.type == "cart_reasoning_semantic_mismatch" for f in findings)


async def test_review_skips_semantic_check_when_disabled() -> None:
    case = normalize_case(CASES_DIR / "case-001-compliant.json")
    ruleset = load_mandate_ruleset()

    findings = await MandateAgent().review(case, ruleset, semantic_check=False)

    assert not any(f.type == "cart_reasoning_semantic_mismatch" for f in findings)
