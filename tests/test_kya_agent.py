import pytest

from agents.kya import KYAAgent, KYAReview
from agents.kya_checks import run_policy_checks
from agents.kya_reasoning import ModelDidNotCallTool, Observation, narrate_findings, reason_about_case
from agents.llm import THINKING_EFFORT, LLMUnavailable, get_model
from data.loader import CASES_DIR, DATA_DIR, load_manifest
from ingestion.normalize import normalize_case
from registry.loader import load_kya_ruleset
from schemas import Rule
from tests.fakes import FakeChatModel

FULL_FLOOR_EXPECTED = {
    "CASE-2026-001": [],
    "CASE-2026-002": [],
    "CASE-2026-003": [],
    "CASE-2026-004": [
        "issuer_not_in_trust_registry",
        "delegation_chain_no_human_terminus",
        "delegation_terminus_principal_mismatch",
    ],
    "CASE-2026-005": [],
    "CASE-2026-006": [],
    "CASE-2026-007": [],
    "CASE-2026-101": [],
    "CASE-2026-102": [],
    "CASE-2026-103": [],
}


def test_full_floor_matches_ground_truth_across_the_corpus() -> None:
    ruleset = load_kya_ruleset()
    agent = KYAAgent()
    for entry in load_manifest():
        case = normalize_case(DATA_DIR / entry["file"])
        findings = agent.run(case, ruleset)
        assert [f.type for f in findings] == FULL_FLOOR_EXPECTED[entry["case_id"]], entry["case_id"]
        assert all(f.agent == "kya" for f in findings)


def test_finding_ids_unique_across_crypto_and_policy_passes() -> None:
    ruleset = load_kya_ruleset()
    case = normalize_case(CASES_DIR / "case-004-synthetic-identity.json")
    findings = KYAAgent().run(case, ruleset)
    ids = [f.finding_id for f in findings]
    assert len(ids) == len(set(ids))
    # crypto pass and policy pass use visibly different id schemes
    assert any("-KYC-" in i for i in ids)
    assert any("-POL-" in i for i in ids)


def test_coverage_gap_raises_loudly_not_silently_skipped() -> None:
    ruleset = load_kya_ruleset()
    case = normalize_case(CASES_DIR / "case-001-compliant.json")
    broken = ruleset.model_copy(deep=True)
    fabricated = Rule.model_validate({
        "rule_id": "KYA-FAKE-01",
        "type": "issuer_trust_required",  # placeholder to pass validation
        "version": 1,
        "status": "active",
        "effective_from": "2026-08-01",
        "severity_weight": 0.5,
        "finding_type": "made_up_finding",
        "description": "test-only rule with a type nothing checks for",
        "params": {},
    })
    object.__setattr__(fabricated, "type", "this_type_has_no_checker")
    broken.rules.append(fabricated)

    with pytest.raises(NotImplementedError):
        run_policy_checks(case.case, broken)


def test_reference_date_is_the_case_payment_date_not_wallclock() -> None:
    from agents.kya_checks import build_policy_context

    case = normalize_case(CASES_DIR / "case-001-compliant.json")
    ctx = build_policy_context(case.case)
    assert ctx.reference_date.isoformat() == case.case.mandate_chain.payment.authorized_at[:10]


def test_get_model_raises_clearly_without_api_key(monkeypatch) -> None:
    # .env may genuinely have a key now (agents/llm.py loads it at import
    # time) — force the no-key scenario explicitly rather than relying on
    # the environment happening to be empty.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMUnavailable):
        get_model()


async def test_reason_about_case_parses_fake_tool_response() -> None:
    case = normalize_case(CASES_DIR / "case-004-synthetic-identity.json")
    fake = FakeChatModel({
        "record_observations": {
            "observations": [
                {"note": "Issuer name resembles a trusted one", "cited_field": "kya_credential.issuer.issuer_name"},
            ]
        }
    })

    observations = await reason_about_case(case, [], model=fake)

    assert len(observations) == 1
    assert isinstance(observations[0], Observation)
    assert observations[0].case_id == "CASE-2026-004"
    assert not hasattr(observations[0], "rule_id")
    assert not hasattr(observations[0], "severity_weight")
    # forced tool_choice isn't compatible with thinking — must be "auto"
    assert fake.call_log == ["record_observations"]


async def test_reason_about_case_empty_observations_is_fine() -> None:
    case = normalize_case(CASES_DIR / "case-001-compliant.json")
    fake = FakeChatModel({"record_observations": {"observations": []}})

    observations = await reason_about_case(case, [], model=fake)

    assert observations == []


async def test_narrate_findings_parses_fake_tool_response() -> None:
    fake = FakeChatModel({"write_narration": {"narration": "Everything checked out for this credential."}})

    narration = await narrate_findings("CASE-2026-001", [], model=fake)

    assert narration == "Everything checked out for this credential."


async def test_model_not_calling_tool_raises_clearly() -> None:
    """Without forced tool_choice, the model could in principle respond
    with only plain text. That must surface as a clear, specific error,
    not an opaque failure to find a matching tool call."""

    class _NoToolCallModel:
        def bind(self, **kwargs):
            return self

        async def ainvoke(self, messages):
            from tests.fakes import FakeAIMessage
            return FakeAIMessage(tool_calls=[])

    with pytest.raises(ModelDidNotCallTool):
        await narrate_findings("CASE-2026-001", [], model=_NoToolCallModel())


async def test_review_combines_floor_ceiling_and_narration_with_fake_client() -> None:
    case = normalize_case(CASES_DIR / "case-004-synthetic-identity.json")
    ruleset = load_kya_ruleset()
    fake = FakeChatModel({
        "record_observations": {"observations": []},
        "write_narration": {"narration": "Two identity concerns were found on this credential."},
    })

    review = await KYAAgent().review(case, ruleset, model=fake)

    assert isinstance(review, KYAReview)
    assert len(review.findings) == 3
    assert review.observations == []
    assert review.narration == "Two identity concerns were found on this credential."


async def test_review_skips_llm_calls_when_disabled() -> None:
    case = normalize_case(CASES_DIR / "case-001-compliant.json")
    ruleset = load_kya_ruleset()

    review = await KYAAgent().review(case, ruleset, reason=False, narrate=False)

    assert review.findings == []
    assert review.observations == []
    assert review.narration is None
