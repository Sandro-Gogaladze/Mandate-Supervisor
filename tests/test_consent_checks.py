"""Consent & Harm's floor against both dossiers."""
from __future__ import annotations

import pytest

from agents.consent_checks import run_consent_checks
from agents.facts import breaches, by_rule
from data.dossier_loader import load
from registry.loader import load_consent_ruleset

KST, HAL = "data/dossiers/DOSSIER-KST-2026-001", "data/dossiers/DOSSIER-HAL-2026-001"


@pytest.fixture(scope="module")
def ruleset():
    return load_consent_ruleset()


@pytest.fixture(scope="module")
def kst():
    return load(KST)


@pytest.fixture(scope="module")
def facts(kst, ruleset):
    return run_consent_checks(kst, ruleset)


def _fact(facts, rule_id, run_id):
    f, = [f for f in facts if f.rule_id == rule_id and f.run_ref == run_id]
    return f


def test_every_rule_in_the_book_produces_facts(facts, ruleset):
    assert set(by_rule(facts)) == {r.rule_id for r in ruleset.rules}


def test_the_missing_human_is_found_on_the_planted_run_only(facts):
    """F24: RUN-2026-0810-0042 required the shopper present and completed
    with no ceremony at all."""
    assert {f.run_ref for f in breaches(facts) if f.rule_id == "CNS-PRS-01"} == {"RUN-2026-0810-0042"}
    f = _fact(facts, "CNS-PRS-01", "RUN-2026-0810-0042")
    assert f.values == {"required": True, "occurred": False, "ceremony_recorded": False}
    # the absence of the record is a fact of its own, and it names the block
    rec = _fact(facts, "CNS-REC-01", "RUN-2026-0810-0042")
    assert (rec.kind, rec.absent_reason, rec.missing) == ("absent", "missing_block", "consent_ceremony")


def test_the_screen_and_the_signature_disagree_on_the_planted_run_only(facts):
    """F29: RUN-2026-0701-0015 showed 54.99 and signed 329."""
    assert {f.run_ref for f in breaches(facts) if f.rule_id == "CNS-RND-01"} == {"RUN-2026-0701-0015"}
    f = _fact(facts, "CNS-RND-01", "RUN-2026-0701-0015")
    assert f.values["shown_amount"] == 54.99 and f.values["signed_amount"] == 329.0
    assert f.values["differences"] == ["amount shown 54.99 vs signed 329.0"]
    assert {r.ref for r in f.refs} == {"consent_ceremony.rendered_values.amount", "cart.cart_total"}


def test_nothing_else_breaches_on_kestrel(facts):
    assert {(f.rule_id, f.run_ref) for f in breaches(facts)} == {
        ("CNS-PRS-01", "RUN-2026-0810-0042"), ("CNS-RND-01", "RUN-2026-0701-0015")}


def test_a_run_that_authorised_nothing_is_out_of_scope_for_presence(facts, kst):
    not_completed = {r.run_id for r in kst.runs if r.outcome != "completed"}
    for rule in ("CNS-PRS-01", "CNS-REC-01"):
        fs = [f for f in facts if f.rule_id == rule and f.run_ref in not_completed]
        assert fs and {(f.kind, f.absent_reason) for f in fs} == {("absent", "out_of_scope")}


def test_a_ceremony_without_rendered_values_is_a_named_gap_for_both_rendering_rules(facts):
    gaps = {rule: {(f.run_ref, f.missing) for f in facts if f.rule_id == rule and f.absent_reason == "missing_block"}
            for rule in ("CNS-RND-01", "CNS-RND-02")}
    assert gaps["CNS-RND-01"] == gaps["CNS-RND-02"]
    assert len(gaps["CNS-RND-01"]) == 1
    assert {m for _, m in gaps["CNS-RND-01"]} == {"consent_ceremony.rendered_values"}


def test_value_for_money_records_a_selection_per_cart(facts, kst):
    ms = [f for f in facts if f.rule_id == "CNS-VFM-01"]
    assert all(f.kind == "measurement" for f in ms)
    assert {f.run_ref for f in ms} == {r.run_id for r in kst.runs if r.cart is not None}
    v = ms[0].values
    assert {"selected_sku", "selected_price", "alternatives", "cheapest_alternative", "premium_pct"} <= set(v)
    # merchant-written text never reaches the model undelimited
    for alt in v["alternatives"]:
        assert alt["description"] is None or alt["description"].startswith("<<<UNTRUSTED_MERCHANT_TEXT>>>")


def test_a_stale_or_future_consent_is_a_breach(kst, ruleset):
    run = next(r for r in kst.runs if r.consent_ceremony and r.payment)
    late = run.consent_ceremony.model_copy(update={"timestamp": "2027-01-01T00:00:00Z"})
    d = kst.model_copy(update={"runs": [run.model_copy(update={"consent_ceremony": late})]})
    f = _fact(run_consent_checks(d, ruleset), "CNS-FRS-01", run.run_id)
    assert f.kind == "breach" and "follows the payment" in f.statement


def test_a_method_outside_the_allowlist_is_a_breach(kst, ruleset):
    run = next(r for r in kst.runs if r.consent_ceremony)
    weak = run.consent_ceremony.model_copy(update={"method": "implied_by_silence"})
    d = kst.model_copy(update={"runs": [run.model_copy(update={"consent_ceremony": weak})]})
    f = _fact(run_consent_checks(d, ruleset), "CNS-MTH-01", run.run_id)
    assert f.kind == "breach" and f.values["method"] == "implied_by_silence"


def test_halcyon_is_clean_and_complete(ruleset):
    facts = run_consent_checks(load(HAL), ruleset)
    assert breaches(facts) == []
    assert not [f for f in facts if f.kind == "absent"]
