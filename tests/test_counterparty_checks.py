"""Counterparty's floor: who received the money, per run and over the payee set."""
from __future__ import annotations

import pytest

from agents.counterparty_checks import build_context, run_counterparty_checks
from agents.facts import breaches, by_rule
from data.dossier_loader import load
from registry.loader import load_counterparty_ruleset

KST, HAL = "data/dossiers/DOSSIER-KST-2026-001", "data/dossiers/DOSSIER-HAL-2026-001"


@pytest.fixture(scope="module")
def ruleset():
    return load_counterparty_ruleset()


@pytest.fixture(scope="module")
def kst():
    return load(KST)


@pytest.fixture(scope="module")
def facts(kst, ruleset):
    return run_counterparty_checks(kst, ruleset)


def test_every_rule_in_the_book_produces_facts(facts, ruleset):
    assert set(by_rule(facts)) == {r.rule_id for r in ruleset.rules}


def test_the_undisclosed_sub_merchant_is_found_on_the_planted_run_only(facts):
    """F52: RUN-2026-0727-0033 paid a marketplace that named no seller."""
    assert {f.run_ref for f in breaches(facts) if f.rule_id == "CPT-SUB-01"} == {"RUN-2026-0727-0033"}
    f, = [f for f in facts if f.rule_id == "CPT-SUB-01" and f.run_ref == "RUN-2026-0727-0033"]
    assert f.values == {"marketplace": True, "sub_merchant": None}


def test_the_new_payee_taking_the_month_is_found_and_pinned_to_its_latest_run(facts):
    """F55: Quickvale, first seen inside the window, took over half of August."""
    f, = [f for f in breaches(facts) if f.rule_id == "CPT-NEW-01"]
    assert f.run_ref == "RUN-2026-0821-0050"
    assert f.values["counterparty_id"] == "MER-QVC-8801" and f.values["new_in_window"] is True
    assert f.values["share_pct"] > f.values["dial"]
    assert "RUN-2026-0821-0050" in f.values["runs"]


def test_the_unresolved_owner_is_a_dossier_level_fact(facts):
    """F53 is a property of the payee, not of the runs that paid it."""
    f, = [f for f in facts if f.rule_id == "CPT-BEN-01"]
    assert f.kind == "breach" and f.run_ref is None
    assert [u["merchant_id"] for u in f.values["unresolved"]] == ["MER-QVC-8801"]
    assert len(f.values["unresolved"][0]["runs"]) == 4


def test_nothing_else_breaches_on_kestrel(facts):
    assert {(f.rule_id, f.run_ref) for f in breaches(facts)} == {
        ("CPT-SUB-01", "RUN-2026-0727-0033"), ("CPT-NEW-01", "RUN-2026-0821-0050"), ("CPT-BEN-01", None)}


def test_every_payee_is_registered_confirmed_and_in_country(facts, kst):
    """The register rules read the cart (a blocked run still named a payee);
    confirmation of payee and country read the payment."""
    carted = {r.run_id for r in kst.runs if r.cart is not None}
    paid = {r.run_id for r in kst.runs if r.payment is not None}
    for rule, scope in (("CPT-REG-01", carted), ("CPT-LST-01", carted), ("CPT-COP-01", paid), ("CPT-CTY-01", paid)):
        fs = [f for f in facts if f.rule_id == rule]
        assert {f.run_ref for f in fs if f.kind == "satisfied"} == scope, rule
        assert {f.absent_reason for f in fs if f.kind == "absent"} == {"out_of_scope"}


def test_an_unregistered_payee_is_a_breach_and_leaves_the_register_rules_absent(kst, ruleset):
    """Empty the register: every payee is unknown, and the rules that read the
    register say so rather than passing."""
    fs = run_counterparty_checks(kst, ruleset, ctx=build_context(kst, merchants={}))
    carted = {r.run_id for r in kst.runs if r.cart is not None}
    assert {f.run_ref for f in fs if f.rule_id == "CPT-REG-01" and f.kind == "breach"} == carted
    for rule in ("CPT-SUB-01", "CPT-LST-01"):
        absent = [f for f in fs if f.rule_id == rule and f.run_ref in carted]
        assert {(f.kind, f.absent_reason) for f in absent} == {("absent", "no_registry_record")}
        assert all(f.missing.startswith("registry:merchants[") for f in absent)
    # ownership cannot be judged for payees the register has never seen
    ben, = [f for f in fs if f.rule_id == "CPT-BEN-01"]
    assert ben.kind == "satisfied" and ben.values["unresolved"] == []


def test_a_settlement_account_in_another_name_is_a_breach(kst, ruleset):
    run = next(r for r in kst.runs if r.payment and r.payment.payee)
    payee = run.payment.payee.model_copy(update={"beneficiary_name_on_account": "Someone Else Holdings"})
    d = kst.model_copy(update={"runs": [run.model_copy(update={"payment": run.payment.model_copy(update={"payee": payee})})]})
    f, = [f for f in run_counterparty_checks(d, ruleset) if f.rule_id == "CPT-COP-01"]
    assert f.kind == "breach" and f.values["beneficiary_name_on_account"] == "Someone Else Holdings"


def test_the_barring_dial_is_the_rulebooks(kst, ruleset):
    run = next(r for r in kst.runs if r.payment)
    mid = run.cart.merchant.merchant_id
    ctx = build_context(kst)  # its own copy of the register — mutating it reaches nobody else
    ctx.merchants[mid] = {**ctx.merchants[mid], "watchlist_flags": ["sanctioned"]}
    f, = [f for f in run_counterparty_checks(kst.model_copy(update={"runs": [run]}), ruleset, ctx=ctx)
          if f.rule_id == "CPT-LST-01"]
    assert f.kind == "breach" and f.values["barring"] == ["sanctioned"]


def test_the_judged_rules_get_their_measurements(facts):
    profiles, = [f for f in facts if f.rule_id == "CPT-IDN-01"]
    assert profiles.kind == "measurement" and profiles.run_ref is None
    shares = [p["share_pct"] for p in profiles.values["payees"]]
    assert shares == sorted(shares, reverse=True)
    assert {"legal_name", "account_names", "beneficial_owner", "first_seen", "runs"} <= set(profiles.values["payees"][0])
    timeline, = [f for f in facts if f.rule_id == "CPT-DCL-01"]
    assert timeline.kind == "measurement" and "total_failures" in timeline.values


def test_halcyon_shares_quickvale_and_nothing_else(ruleset):
    facts = run_counterparty_checks(load(HAL), ruleset)
    assert {(f.rule_id, f.run_ref) for f in breaches(facts)} == {
        ("CPT-NEW-01", "RUN-2026-0821-0020"), ("CPT-BEN-01", None)}
