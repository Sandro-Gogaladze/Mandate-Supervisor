import pytest

from agents.mandate import MandateAgent
from agents.mandate_checks import run_policy_checks
from data.loader import DATA_DIR, load_manifest
from ingestion.normalize import normalize_case
from registry.loader import load_mandate_ruleset
from schemas import Rule

FULL_FLOOR_EXPECTED = {
    "CASE-2026-001": [],
    "CASE-2026-002": [
        "per_transaction_cap_exceeded",
        "category_out_of_scope",
        "counterparty_not_approved",
    ],
    "CASE-2026-003": [
        "chain_hash_mismatch",
        "payment_amount_inconsistent_with_cart",
    ],
    "CASE-2026-004": [],
    "CASE-2026-005": [],
    "CASE-2026-006": [],
    "CASE-2026-007": ["per_transaction_cap_exceeded", "injection_heuristic_flag"],
}


def test_full_floor_matches_ground_truth_across_the_corpus() -> None:
    ruleset = load_mandate_ruleset()
    agent = MandateAgent()
    for entry in load_manifest():
        case = normalize_case(DATA_DIR / entry["file"])
        findings = agent.run(case, ruleset)
        assert [f.type for f in findings] == FULL_FLOOR_EXPECTED[entry["case_id"]], entry["case_id"]
        assert all(f.agent == "mandate" for f in findings)


def test_case_006_open_counterparty_policy_does_not_false_positive() -> None:
    """case-006 has an empty allowed_counterparties list with an explicit
    open counterparty_policy note (schemas/mandate.py) — the counterparty
    check must not treat empty-list as deny-all."""
    ruleset = load_mandate_ruleset()
    case = normalize_case(DATA_DIR / "cases" / "case-006-drift.json")
    findings = MandateAgent().run(case, ruleset)
    assert not any(f.type == "counterparty_not_approved" for f in findings)


def test_cumulative_cap_check_matches_the_cases_own_reasoning_text() -> None:
    """case-001's agent_attestation.reasoning claims month-to-date spend of
    exactly ₾1,748.10 — confirms the calendar-month interpretation
    (docs/phases/06-mandate-agent.md) is the one actually used to author
    the corpus, not a guess."""
    from agents.mandate_checks import build_policy_context, _check_cumulative_spend_within_monthly_cap

    case = normalize_case(DATA_DIR / "cases" / "case-001-compliant.json")
    ruleset = load_mandate_ruleset()
    rule = next(r for r in ruleset.rules if r.type == "cumulative_spend_within_monthly_cap")
    ctx = build_policy_context(case.case)

    finding = _check_cumulative_spend_within_monthly_cap(case.case, rule, ctx, _Counter())
    assert finding is None  # under cap — but confirm the actual sum below

    auth_month_sum = sum(
        t.amount for t in case.case.transaction_history
        if t.timestamp[:7] == case.case.mandate_chain.payment.authorized_at[:7]
    )
    assert round(auth_month_sum, 2) == 1748.10


class _Counter:
    def next(self) -> str:
        return "TEST-001"


def test_payment_amount_tolerance_is_respected() -> None:
    from agents.mandate_checks import _check_payment_amount_matches_cart_total, build_policy_context

    case = normalize_case(DATA_DIR / "cases" / "case-001-compliant.json")
    ruleset = load_mandate_ruleset()
    rule = next(r for r in ruleset.rules if r.type == "payment_amount_matches_cart_total")
    ctx = build_policy_context(case.case)

    # sanity: the compliant case's payment/cart already match exactly
    assert case.case.mandate_chain.payment.amount == case.case.mandate_chain.cart.cart_total
    assert _check_payment_amount_matches_cart_total(case.case, rule, ctx, _Counter()) is None


def test_coverage_gap_raises_loudly_not_silently_skipped() -> None:
    ruleset = load_mandate_ruleset()
    case = normalize_case(DATA_DIR / "cases" / "case-001-compliant.json")
    broken = ruleset.model_copy(deep=True)
    fabricated = Rule.model_validate({
        "rule_id": "MND-FAKE-01",
        "type": "cart_chain_link_matches_intent",  # placeholder to pass validation
        "version": 1,
        "status": "active",
        "effective_from": "2026-08-01",
        "severity_weight": 0.5,
        "finding_type": "made_up_finding",
        "description": "test-only rule with a type nothing checks for",
        "params": {},
    })
    fabricated.type = "this_type_has_no_checker"
    broken.rules.append(fabricated)

    with pytest.raises(NotImplementedError):
        run_policy_checks(case.case, broken)


def test_finding_ids_distinguishable_from_chain_pass() -> None:
    ruleset = load_mandate_ruleset()
    case = normalize_case(DATA_DIR / "cases" / "case-003-broken-chain.json")
    findings = MandateAgent().run(case, ruleset)
    ids = [f.finding_id for f in findings]
    assert len(ids) == len(set(ids))
    assert any("-CHN-" in i for i in ids)  # from ingestion's chain check
    assert any("-MND-" in i for i in ids)  # from the new policy checks
