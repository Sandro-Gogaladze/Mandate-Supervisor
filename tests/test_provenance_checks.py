"""Provenance's book, against the real dossier.

The three TEC rules moved from draft to active because the DATA changed, not
the code — `construction_context` did not exist in the old submission shape —
and then moved book, ids kept, when Provenance got its own. These assert each
finds what it was blocked on, that the card-versus-credential rule and the
four-source measurement run, and that the ownership split with KYA is exact:
a rule evaluated twice is noise, a rule evaluated by nobody is the gap the
coverage guarantee cannot catch.
"""
from __future__ import annotations

import pytest

from agents.facts import breaches, by_rule
from agents.kya_checks import CRYPTO_HANDLED_TYPES, PROVENANCE_OWNED_TYPES, _POLICY_CHECKERS
from agents.provenance_checks import (
    PROVENANCE_RULE_TYPES,
    build_context,
    run_provenance_checks,
)
from data.dossier_loader import load
from registry.loader import active_rules_by_type, load_kya_ruleset, load_provenance_ruleset

DOSSIER = "data/dossiers/DOSSIER-KST-2026-001"


@pytest.fixture(scope="module")
def dossier():
    return load(DOSSIER)


@pytest.fixture(scope="module")
def ruleset():
    return load_provenance_ruleset()


@pytest.fixture(scope="module")
def kya_ruleset():
    return load_kya_ruleset()


@pytest.fixture(scope="module")
def facts(dossier, ruleset):
    return run_provenance_checks(dossier, ruleset)


# --- ownership -------------------------------------------------------------

def test_provenance_owns_exactly_what_kya_skips():
    assert PROVENANCE_OWNED_TYPES == PROVENANCE_RULE_TYPES


def test_every_active_kya_rule_is_owned_by_someone(kya_ruleset):
    owned = set(_POLICY_CHECKERS) | CRYPTO_HANDLED_TYPES
    unowned = set(active_rules_by_type(kya_ruleset)) - owned
    assert not unowned, f"active rules with no owner: {sorted(unowned)}"
    # ...and none of Provenance's rules is left in the KYA book.
    assert not set(active_rules_by_type(kya_ruleset)) & PROVENANCE_RULE_TYPES


def test_every_active_provenance_rule_has_a_checker(ruleset):
    from agents.provenance_checks import _PROVENANCE_CHECKERS
    assert set(active_rules_by_type(ruleset)) <= set(_PROVENANCE_CHECKERS)


def test_one_fact_per_run_per_rule(facts, dossier):
    run_ids = {r.run_id for r in dossier.runs}
    grouped = by_rule(facts)
    assert set(grouped) == {"KYA-TEC-02", "KYA-TEC-05", "KYA-TEC-06", "PRV-CRD-01", "PRV-REC-01"}
    for rule_id in ("KYA-TEC-02", "KYA-TEC-05", "KYA-TEC-06"):
        fs = grouped[rule_id]
        assert {f.run_ref for f in fs} == run_ids and len(fs) == len(run_ids)
    # the card and the reconciliation are properties of the dossier, not a run
    assert [f.run_ref for f in grouped["PRV-CRD-01"] + grouped["PRV-REC-01"]] == [None, None]


# --- the three rules -------------------------------------------------------

def test_model_substitution_is_found_and_named_as_blocklisted(facts):
    f, = [f for f in breaches(facts) if f.rule_id == "KYA-TEC-02"]
    assert f.run_ref == "RUN-2026-0728-0034"
    assert f.values["observed_version"] == "claude-sonnet-4-5-20250929"
    # A barred model that actually authorised payments is a different order of
    # problem from one merely named on a form, and the fact says so.
    assert f.values["observed_blocklisted"] is True
    assert "blocklisted" in f.statement


def test_unapproved_prompt_release_is_found(facts):
    f, = [f for f in breaches(facts) if f.rule_id == "KYA-TEC-05"]
    assert f.run_ref == "RUN-2026-0723-0031"
    assert f.values["release_ref"] == "kestrel-shop-v2.4.2-hotfix"
    assert f.values["approved"] is False


def test_unauthorised_tool_server_is_found_not_the_tool_name(facts):
    """The tool name in an unauthorised call is one the agent may legitimately
    call. Pinning the server is the entire point."""
    f, = [f for f in breaches(facts) if f.rule_id == "KYA-TEC-06"]
    assert f.run_ref == "RUN-2026-0720-0028"
    assert f.values["unauthorised"] == ["check_availability -> mcp://inventory.fastcheck-partners.net"]
    assert f.values["undeclared"] == []


def test_the_other_runs_are_satisfied_not_unmentioned(facts, dossier):
    # 3 run-level rules minus the 3 breaches, plus the card rule on the dossier
    assert sum(1 for f in facts if f.kind == "satisfied") == 3 * len(dossier.runs) - 3 + 1


# --- the card against the credential ------------------------------------------

def test_the_card_is_within_the_credential_and_signed(facts):
    f, = by_rule(facts)["PRV-CRD-01"]
    assert f.kind == "satisfied" and f.values["excess"] == [] and f.values["signed"] is True


def test_a_card_claiming_more_than_the_credential_grants_is_a_breach(dossier, ruleset):
    card = dossier.dossier.agent_card.model_copy(update={
        "declared_capabilities": [*dossier.dossier.agent_card.declared_capabilities, "issue_refunds"]})
    d = dossier.model_copy(update={"dossier": dossier.dossier.model_copy(update={"agent_card": card})})
    f, = by_rule(run_provenance_checks(d, ruleset))["PRV-CRD-01"]
    assert f.kind == "breach" and f.values["excess"] == ["issue_refunds"]


def test_the_four_sources_measurement_carries_what_the_judgement_needs(facts, dossier):
    f, = by_rule(facts)["PRV-REC-01"]
    assert f.kind == "measurement"
    v = f.values
    assert v["agent_card"]["filed"] and v["register"]["present"]
    assert "mcp://inventory.fastcheck-partners.net" in v["observed"]["tool_servers"]
    assert "kestrel-shop-v2.4.2-hotfix" in v["observed"]["prompt_releases"]
    assert v["credential"]["capabilities"] == list(dossier.dossier.kya_credential.capabilities)


# --- absence is a fact -----------------------------------------------------

def test_an_unregistered_agent_makes_the_release_check_absent_not_silent(dossier, ruleset):
    """No register entry means no approved-release list to compare against.
    The regulator's gap, named as such — and the two rules that do not need
    the register still run."""
    ctx = build_context(dossier, agents={})
    grouped = by_rule(run_provenance_checks(dossier, ruleset, ctx=ctx))
    assert {(f.kind, f.absent_reason, f.missing) for f in grouped["KYA-TEC-05"]} == {
        ("absent", "no_registry_record", "registry:agents[AGT-KST-SHOP-01]")}
    assert {f.kind for f in grouped["KYA-TEC-02"]} == {"satisfied", "breach"}
    assert {f.kind for f in grouped["KYA-TEC-06"]} == {"satisfied", "breach"}


def test_no_agent_card_leaves_the_declared_half_absent(dossier, ruleset):
    """Without a card the authorised half still runs; the declared half
    cannot, and the fact names the block the firm did not file."""
    d = dossier.model_copy(update={"dossier": dossier.dossier.model_copy(update={"agent_card": None})})
    grouped = by_rule(run_provenance_checks(d, ruleset))
    fs = grouped["KYA-TEC-06"]
    # ...and the card rule names the block itself
    card, = grouped["PRV-CRD-01"]
    assert (card.kind, card.absent_reason, card.missing) == ("absent", "missing_block", "agent_card")
    clean = [f for f in fs if f.run_ref != "RUN-2026-0720-0028"]
    assert {(f.kind, f.absent_reason, f.missing) for f in clean} == {
        ("absent", "missing_block", "agent_card.declared_tool_servers")}
    # the unauthorised server is a breach with or without a card
    bad, = [f for f in fs if f.run_ref == "RUN-2026-0720-0028"]
    assert bad.kind == "breach"
