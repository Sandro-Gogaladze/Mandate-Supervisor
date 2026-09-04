"""Mandate's deterministic floor, per run, against the real dossiers."""
from __future__ import annotations

import pytest

from agents.facts import breaches, by_rule
from agents.mandate_checks import CHAIN_HANDLED_TYPES, _RUN_CHECKERS, run_policy_checks
from data.dossier_loader import load
from registry.loader import load_mandate_ruleset
from schemas import AllowedCounterparty, Rule

KST = "data/dossiers/DOSSIER-KST-2026-001"
HAL = "data/dossiers/DOSSIER-HAL-2026-001"


@pytest.fixture(scope="module")
def dossier():
    return load(KST)


@pytest.fixture(scope="module")
def halcyon():
    return load(HAL)


@pytest.fixture(scope="module")
def ruleset():
    return load_mandate_ruleset()


@pytest.fixture(scope="module")
def facts(dossier, ruleset):
    return run_policy_checks(dossier, ruleset)


def _run(dossier, run_id):
    return next(r for r in dossier.runs if r.run_id == run_id)


def _fact(facts, rule_id, run_id):
    f, = [f for f in facts if f.rule_id == rule_id and f.run_ref == run_id]
    return f


# --- the contract ----------------------------------------------------------

def test_every_rule_is_accounted_for(facts, ruleset):
    grouped = by_rule(facts)
    # Intake owns the chain/signature rules while they are active; a draft
    # one still gets its absent/rule_draft fact here.
    chain = {r.rule_id for r in ruleset.rules
             if r.type in CHAIN_HANDLED_TYPES and r.status == "active"}
    assert set(grouped) == {r.rule_id for r in ruleset.rules} - chain
    draft, = grouped["MND-SIG-01"]
    assert (draft.kind, draft.absent_reason, draft.run_ref) == ("absent", "rule_draft", None)
    assert len(grouped["MND-CAP-04"]) == 50  # promoted in Phase 3


def test_every_run_level_rule_answers_for_every_run(facts, dossier, ruleset):
    run_ids = {r.run_id for r in dossier.runs}
    for r in ruleset.rules:
        if r.type in _RUN_CHECKERS and r.evaluation == "computable":
            fs = by_rule(facts)[r.rule_id]
            assert {f.run_ref for f in fs} == run_ids and len(fs) == len(run_ids), r.rule_id


def test_a_judged_rule_records_its_evidence_as_a_measurement(facts, dossier):
    """MND-SEM-01 is decided by the reasoning pass. check() records the pair
    the judgement rests on so the assessment has a fact to cite and the
    critic has something to compare its quoted values against."""
    fs = by_rule(facts)["MND-SEM-01"]
    assert {f.kind for f in fs} == {"measurement"}
    with_cart = {r.run_id for r in dossier.runs if r.cart is not None}
    assert {f.run_ref for f in fs} == with_cart
    f = _fact(facts, "MND-SEM-01", "RUN-2026-0625-0011")
    assert "vitamin" in f.values["natural_language_intent"].lower()
    assert f.values["line_items"] and "agent_reasoning" in f.values


def test_an_active_computable_rule_with_no_checker_raises(dossier, ruleset):
    bogus = Rule(rule_id="MND-XXX-99", type="cart_smells_right", version=1, status="active",
                 effective_from="2026-01-01", severity_weight=0.1, finding_type="x",
                 description="nobody wrote this")
    broken = ruleset.model_copy(update={"rules": [*ruleset.rules, bogus]})
    with pytest.raises(NotImplementedError, match="MND-XXX-99"):
        run_policy_checks(dossier, broken)


# --- planted defects -------------------------------------------------------

def test_cap_breach_is_found_with_its_numbers(facts):
    f = _fact(facts, "MND-CAP-01", "RUN-2026-0811-0043")
    assert f.kind == "breach"
    assert f.values == {"cart_total": 708.0, "max_transaction_amount": 500.0}
    assert {r.ref for r in f.refs} == {"cart.cart_total",
                                       "intent_mandate.authorization_scope.max_transaction_amount"}


def test_category_breach_is_found(facts):
    f = _fact(facts, "MND-CAP-02", "RUN-2026-0805-0039")
    assert f.kind == "breach"
    assert f.values["mcc"] == "5964" and f.values["merchant_id"] == "MER-QVC-8801"


def test_cumulative_cap_catches_the_second_draw_on_a_single_use_mandate(facts):
    """RUN-2026-0818-0048 re-used IM-KST-0817-0047 (F50). Per mandate — not
    per calendar month — the two settled draws exceed the mandate's cap."""
    f = _fact(facts, "MND-CAP-05", "RUN-2026-0818-0048")
    assert f.kind == "breach"
    assert f.values["draws"] == ["RUN-2026-0817-0047", "RUN-2026-0818-0048"]
    assert f.values["cumulative_settled"] == 112.0 and f.values["max_cumulative_amount"] == 70.0
    # ...and the FIRST draw, evaluated as of its own time, was fine.
    first = _fact(facts, "MND-CAP-05", "RUN-2026-0817-0047")
    assert first.kind == "satisfied" and first.values["draws"] == ["RUN-2026-0817-0047"]


def test_cumulative_cap_does_not_sum_unrelated_tasks(facts, dossier):
    """On single-task mandates the cumulative cap equals the per-transaction
    cap; a calendar-month sum would breach every run. Per mandate, the only
    other breach is the over-cap cart itself."""
    assert {f.run_ref for f in breaches(facts) if f.rule_id == "MND-CAP-05"} == {
        "RUN-2026-0811-0043", "RUN-2026-0818-0048"}


def test_halcyon_has_exactly_one_mandate_breach(halcyon, ruleset):
    bs = breaches(run_policy_checks(halcyon, ruleset))
    assert [(f.rule_id, f.run_ref) for f in bs] == [("MND-CAP-02", "RUN-2026-0813-0015")]


# --- runs that never reached a cart or a payment ---------------------------

def test_a_failed_run_is_out_of_scope_for_every_cart_rule(facts, dossier):
    failed = _run(dossier, "RUN-2026-0724-0032")
    assert failed.cart is None
    fs = [f for f in facts if f.run_ref == failed.run_id]
    cart_rules = {"MND-CAP-01", "MND-CAP-02", "MND-CAP-03", "MND-CAP-04", "MND-CAP-05",
                  "MND-CON-01", "MND-CUR-01", "MND-CUR-02", "MND-VAL-01"}
    assert {(f.kind, f.absent_reason) for f in fs if f.rule_id in cart_rules} == {("absent", "out_of_scope")}
    assert {f.rule_id for f in fs} == cart_rules | {"MND-USE-01"}
    # the mandate itself still exists on a failed run: its first draw is on record
    assert _fact(facts, "MND-USE-01", failed.run_id).kind == "satisfied"


def test_an_abandoned_run_still_has_its_cart_checked(facts, dossier):
    """RUN-2026-0624-0010 built a cart and was abandoned before payment. The
    cart rules answer; the payment rules cannot."""
    assert _fact(facts, "MND-CAP-01", "RUN-2026-0624-0010").kind == "satisfied"
    assert _fact(facts, "MND-CUR-01", "RUN-2026-0624-0010").kind == "satisfied"
    for rule_id in ("MND-CON-01", "MND-CUR-02", "MND-VAL-01", "MND-CAP-05"):
        f = _fact(facts, rule_id, "RUN-2026-0624-0010")
        assert (f.kind, f.absent_reason) == ("absent", "out_of_scope"), rule_id


def test_the_blocked_run_is_a_cap_breach_at_the_fact_level(facts):
    """RUN-2026-0722-0030: a $770 cart against a $400 cap, stopped by the
    firm's own control. The FACT is a breach — the agent built that cart. That
    the control held is the assessment layer's context (agents/assess.py),
    not a reason for the fact to lie."""
    f = _fact(facts, "MND-CAP-01", "RUN-2026-0722-0030")
    assert f.kind == "breach" and f.values["cart_total"] == 770.0


# --- the mandate itself: reuse and region ------------------------------------

def test_a_single_use_mandate_drawn_on_twice_is_a_breach_on_the_second_draw(facts):
    """F50 — RUN-2026-0818-0048 re-used IM-KST-0817-0047. The first draw is
    satisfied; the second is the breach, naming the earlier run."""
    first = _fact(facts, "MND-USE-01", "RUN-2026-0817-0047")
    second = _fact(facts, "MND-USE-01", "RUN-2026-0818-0048")
    assert first.kind == "satisfied" and first.values["earlier_draws"] == []
    assert second.kind == "breach"
    assert second.values["earlier_draws"] == ["RUN-2026-0817-0047"] and second.values["uses_consumed"] == 2
    assert {f.run_ref for f in breaches(facts) if f.rule_id == "MND-USE-01"} == {"RUN-2026-0818-0048"}


def test_a_mandate_with_no_usage_is_a_named_gap(dossier, ruleset):
    run = _run(dossier, "RUN-2026-0811-0043")
    scope = run.intent_mandate.authorization_scope.model_copy(update={"usage": None})
    intent = run.intent_mandate.model_copy(update={"authorization_scope": scope})
    d = dossier.model_copy(update={"runs": [run.model_copy(update={"intent_mandate": intent})]})
    f, = by_rule(run_policy_checks(d, ruleset))["MND-USE-01"]
    assert (f.kind, f.absent_reason, f.missing) == ("absent", "missing_block",
                                                   "intent_mandate.authorization_scope.usage")


def test_geographic_scope_is_global_everywhere_and_enforced_when_named(facts, dossier, ruleset):
    """F48. Every scope in the corpus is GLOBAL, so the rule is satisfied on
    every cart; a named region breaches a merchant elsewhere and a missing
    region is a gap, not a pass."""
    assert {f.kind for f in by_rule(facts)["MND-CAP-04"] if f.run_ref != "RUN-2026-0724-0032"} == {"satisfied"}
    run = _run(dossier, "RUN-2026-0811-0043")
    elsewhere = "APAC" if run.cart.merchant.region != "APAC" else "NA"
    scope = run.intent_mandate.authorization_scope.model_copy(update={"geographic_scope": elsewhere})
    intent = run.intent_mandate.model_copy(update={"authorization_scope": scope})
    d = dossier.model_copy(update={"runs": [run.model_copy(update={"intent_mandate": intent})]})
    f, = by_rule(run_policy_checks(d, ruleset))["MND-CAP-04"]
    assert f.kind == "breach"
    assert f.values == {"region": run.cart.merchant.region, "geographic_scope": elsewhere}
    merchant = run.cart.merchant.model_copy(update={"region": None})
    d = dossier.model_copy(update={"runs": [run.model_copy(update={"cart": run.cart.model_copy(update={"merchant": merchant})})]})
    f, = by_rule(run_policy_checks(d, ruleset))["MND-CAP-04"]
    assert (f.kind, f.absent_reason, f.missing) == ("absent", "missing_block", "cart.merchant.region")


# --- counterparty allowlist ------------------------------------------------

def test_no_allowlist_means_category_governed_not_deny_all(facts, dossier):
    fs = by_rule(facts)["MND-CAP-03"]
    assert {(f.kind, f.absent_reason) for f in fs if f.run_ref != "RUN-2026-0724-0032"} == {
        ("absent", "out_of_scope")}


def test_an_allowlist_is_enforced_when_present(dossier, ruleset):
    run = _run(dossier, "RUN-2026-0811-0043")
    scope = run.intent_mandate.authorization_scope
    listed = scope.model_copy(update={"allowed_counterparties": [
        AllowedCounterparty(counterparty_id=run.cart.merchant.merchant_id, name="the one")]})
    other = scope.model_copy(update={"allowed_counterparties": [
        AllowedCounterparty(counterparty_id="MER-NOBODY", name="someone else")]})
    for scope_, expected in ((listed, "satisfied"), (other, "breach")):
        intent = run.intent_mandate.model_copy(update={"authorization_scope": scope_})
        d = dossier.model_copy(update={"runs": [run.model_copy(update={"intent_mandate": intent})]})
        f, = by_rule(run_policy_checks(d, ruleset))["MND-CAP-03"]
        assert f.kind == expected
