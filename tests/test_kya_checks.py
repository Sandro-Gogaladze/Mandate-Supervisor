"""KYA's deterministic floor on the dossier shape.

The corpus is the fixture. Beyond the planted defects, what these tests pin
is the CONTRACT: every rule accounted for, run-level rules answering per run,
dossier-level rules answering once, and — the point of the Fact migration —
`absent` carrying its reason rather than collapsing into silence.
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from agents.facts import breaches, by_rule
from agents.kya_checks import (
    CRYPTO_HANDLED_TYPES,
    PROVENANCE_OWNED_TYPES,
    _DOSSIER_CHECKERS,
    _RUN_CHECKERS,
    build_policy_context,
    run_policy_checks,
)
from data.dossier_loader import load
from registry.loader import load_kya_ruleset

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
    return load_kya_ruleset()


@pytest.fixture(scope="module")
def facts(dossier, ruleset):
    return run_policy_checks(dossier, ruleset)


def _with_credential(dossier, **update):
    cred = dossier.dossier.kya_credential.model_copy(update=update)
    return dossier.model_copy(update={"dossier": dossier.dossier.model_copy(
        update={"kya_credential": cred})})


# --- the contract ----------------------------------------------------------

def test_every_rule_is_accounted_for(facts, ruleset):
    """Active computable rules that are KYA's produce outcomes; draft rules
    produce `absent/rule_draft`; the crypto and Provenance-owned types are
    deliberately someone else's and produce nothing here."""
    grouped = by_rule(facts)
    elsewhere = {r.rule_id for r in ruleset.rules
                 if r.type in CRYPTO_HANDLED_TYPES | PROVENANCE_OWNED_TYPES}
    assert set(grouped) == {r.rule_id for r in ruleset.rules} - elsewhere
    for r in ruleset.rules:
        if r.status == "draft":
            f, = grouped[r.rule_id]
            assert (f.kind, f.absent_reason) == ("absent", "rule_draft")
            assert r.notes and r.notes in f.statement


def test_run_level_rules_answer_per_run_and_dossier_rules_once(facts, dossier, ruleset):
    run_ids = {r.run_id for r in dossier.runs}
    for r in ruleset.rules:
        fs = by_rule(facts).get(r.rule_id)
        if fs is None:
            continue
        if r.type in _RUN_CHECKERS:
            assert {f.run_ref for f in fs} == run_ids and len(fs) == len(run_ids), r.rule_id
        else:
            assert r.type in _DOSSIER_CHECKERS or r.status == "draft", r.rule_id
            assert [f.run_ref for f in fs] == [None], r.rule_id


def test_facts_are_deterministic(dossier, ruleset):
    a = run_policy_checks(dossier, ruleset)
    b = run_policy_checks(dossier, ruleset)
    assert [(f.fact_id, f.kind) for f in a] == [(f.fact_id, f.kind) for f in b]


# --- the planted defect, and the rules it must not disturb -----------------

def test_simultaneous_credentials_are_found(facts):
    f, = [f for f in breaches(facts) if f.rule_id == "KYA-LIF-04"]
    assert f.run_ref is None
    assert "CRED-KST-2025-0188" in f.statement and "CRED-KST-2026-0442" in f.statement
    assert len(f.values["overlaps"]) == 1


def test_it_is_the_only_kya_breach_in_the_dossier(facts):
    assert {f.rule_id for f in breaches(facts)} == {"KYA-LIF-04"}


def test_halcyon_has_no_kya_breach(halcyon, ruleset):
    assert breaches(run_policy_checks(halcyon, ruleset)) == []


def test_capability_growth_within_tolerance_is_satisfied_not_creep(facts):
    """One new capability at a renewal is an agent gaining a function, not
    permissions widening quietly. The rule must not punish legitimate growth."""
    f, = by_rule(facts)["KYA-CAP-05"]
    assert f.kind == "satisfied"
    assert len(f.values["reissues"]) == 2
    assert all(len(r["added"]) <= f.values["tolerance"] for r in f.values["reissues"])


def test_a_single_credential_has_no_series_to_compare(halcyon, ruleset):
    d = halcyon.model_copy(update={"dossier": halcyon.dossier.model_copy(
        update={"credential_history": []})})
    grouped = by_rule(run_policy_checks(d, ruleset))
    for rule_id in ("KYA-CAP-05", "KYA-LIF-04"):
        f, = grouped[rule_id]
        assert (f.kind, f.absent_reason) == ("absent", "out_of_scope")
        assert f.values["series_length"] == 1


# --- absence is a fact -----------------------------------------------------

def test_consumer_mandates_put_acc_02_out_of_scope_on_every_run(facts, dossier):
    """The shopper signs their own Intent; the chain ends at the operator's
    officer. Different people by design — see the rule's docstring."""
    fs = by_rule(facts)["KYA-ACC-02"]
    assert len(fs) == len(dossier.runs)
    assert {(f.kind, f.absent_reason) for f in fs} == {("absent", "out_of_scope")}
    assert all(f.values == {"principal_type": "consumer"} for f in fs)


def test_acc_02_is_evaluated_for_a_delegated_officer(dossier, ruleset):
    run = dossier.runs[0]
    officer = run.intent_mandate.principal.model_copy(
        update={"principal_type": "delegated_officer", "principal_id": "PRIN-KST-0002"})
    intent = run.intent_mandate.model_copy(update={"principal": officer})
    corporate = run.model_copy(update={"intent_mandate": intent})
    d = dossier.model_copy(update={"runs": [corporate]})
    f, = by_rule(run_policy_checks(d, ruleset))["KYA-ACC-02"]
    assert f.kind == "satisfied"
    stranger = intent.model_copy(update={"principal": officer.model_copy(
        update={"principal_id": "PRIN-SOMEONE-ELSE"})})
    d = dossier.model_copy(update={"runs": [run.model_copy(update={"intent_mandate": stranger})]})
    f, = by_rule(run_policy_checks(d, ruleset))["KYA-ACC-02"]
    assert f.kind == "breach"


def test_delegation_grants_are_nested_so_acc_06_is_satisfied(facts, dossier):
    """Each level may only hold what the level above granted it."""
    chain = dossier.dossier.kya_credential.delegation_chain
    for child, parent in zip(chain, chain[1:]):
        assert set(child.granted_capabilities) <= set(parent.granted_capabilities)
    f, = by_rule(facts)["KYA-ACC-06"]
    assert f.kind == "satisfied"


def test_acc_06_names_the_missing_grants_when_no_level_records_them(dossier, ruleset):
    """A chain that only lists names has nothing to compare.

    Absence is not compliance — and it is not silence either. The fact says
    which block was missing, which is what the data-gap finding is built from.
    This is the case the Fact migration was for.
    """
    cred = deepcopy(dossier.dossier.kya_credential)
    for entry in cred.delegation_chain:
        entry.granted_capabilities = []
    d = _with_credential(dossier, delegation_chain=cred.delegation_chain)
    f, = by_rule(run_policy_checks(d, ruleset))["KYA-ACC-06"]
    assert (f.kind, f.absent_reason) == ("absent", "missing_block")
    assert f.missing == "kya_credential.delegation_chain[].granted_capabilities"
    assert f.values["levels_without_grants"] == [0, 1, 2]


def test_acc_06_catches_a_middle_party_minting_authority(dossier, ruleset):
    cred = deepcopy(dossier.dossier.kya_credential)
    cred.delegation_chain[0].granted_capabilities.append("treasury:wire")
    d = _with_credential(dossier, delegation_chain=cred.delegation_chain)
    f, = by_rule(run_policy_checks(d, ruleset))["KYA-ACC-06"]
    assert f.kind == "breach" and "treasury:wire" in f.statement


def test_missing_revocation_timestamp_is_a_named_gap(dossier, ruleset):
    d = _with_credential(dossier, revocation_checked_at=None)
    f, = by_rule(run_policy_checks(d, ruleset))["KYA-LIF-05"]
    assert (f.kind, f.absent_reason, f.missing) == (
        "absent", "missing_block", "kya_credential.revocation_checked_at")


def test_an_unregistered_agent_breaches_reg_01_and_absents_the_rest(dossier, ruleset):
    """An agent the register has never heard of transacting IS the failure
    REG-01 exists to catch. Every other register-backed rule cannot be
    evaluated, and says so, naming the entry the regulator lacks."""
    ctx = build_policy_context(dossier, agents={})
    grouped = by_rule(run_policy_checks(dossier, ruleset, ctx=ctx))
    assert {f.kind for f in grouped["KYA-REG-01"]} == {"breach"}
    assert len(grouped["KYA-REG-01"]) == len(dossier.runs)
    for rule_id in ("KYA-ISS-05", "KYA-ACC-07", "KYA-OPF-01", "KYA-OPF-02", "KYA-OPF-03",
                    "KYA-OPF-04", "KYA-REG-02", "KYA-REG-04", "KYA-REG-05", "KYA-TEC-04"):
        assert {(f.kind, f.absent_reason, f.missing) for f in grouped[rule_id]} == {
            ("absent", "no_registry_record", "registry:agents[AGT-KST-SHOP-01]")}, rule_id


def test_an_unknown_issuer_absents_the_issuer_rules(dossier, ruleset):
    """ISS-01 (ingestion) is the finding; ISS-03/04/05 have no record to read."""
    ctx = build_policy_context(dossier, issuers={})
    grouped = by_rule(run_policy_checks(dossier, ruleset, ctx=ctx))
    for rule_id in ("KYA-ISS-03", "KYA-ISS-04", "KYA-ISS-05"):
        f, = grouped[rule_id]
        assert (f.kind, f.absent_reason, f.missing) == (
            "absent", "no_registry_record", "registry:issuers[ISS-002]"), rule_id


# --- time of use is per run ------------------------------------------------

def test_a_credential_expiring_mid_window_breaches_only_the_runs_after_it(dossier, ruleset):
    """Time of use is per run: forty runs fine, ten on an expired credential,
    and the facts say which — a dossier-level answer could not."""
    from datetime import date, timedelta

    from schemas import typed_params

    grace = typed_params(next(r for r in ruleset.rules if r.rule_id == "KYA-LIF-01")).grace_period_days
    cutoff = (date(2026, 7, 15) + timedelta(days=grace)).isoformat()
    d = _with_credential(dossier, expires_at="2026-07-15T00:00:00-05:00")
    fs = by_rule(run_policy_checks(d, ruleset))["KYA-LIF-01"]
    after = {f.run_ref for f in fs if f.kind == "breach"}
    before = {f.run_ref for f in fs if f.kind == "satisfied"}
    assert after and before and not (after & before)
    assert all(r.started_at[:10] > cutoff for r in dossier.runs if r.run_id in after)
    assert all(r.started_at[:10] <= cutoff for r in dossier.runs if r.run_id in before)


def test_registration_after_first_use_breaches_only_the_earlier_runs(dossier, ruleset):
    agents = deepcopy(build_policy_context(dossier).agents)
    agents["AGT-KST-SHOP-01"]["registered_at"] = "2026-07-01"
    ctx = build_policy_context(dossier, agents=agents)
    fs = by_rule(run_policy_checks(dossier, ruleset, ctx=ctx))["KYA-REG-01"]
    early = {f.run_ref for f in fs if f.kind == "breach"}
    assert early and all(r.started_at[:10] < "2026-07-01" for r in dossier.runs if r.run_id in early)


def test_operator_licence_or_sponsorship_either_satisfies(facts, dossier, ruleset):
    """Kestrel is unlicensed and sponsored; a rule reading 'must hold a
    licence' would fail every non-bank operator by construction."""
    f, = by_rule(facts)["KYA-OPF-01"]
    assert f.kind == "satisfied" and f.values["sponsorship_status"] == "active"
    operators = deepcopy(build_policy_context(dossier).operators)
    operators["OPR-002"]["sponsorship"]["status"] = "lapsed"
    ctx = build_policy_context(dossier, operators=operators)
    f, = by_rule(run_policy_checks(dossier, ruleset, ctx=ctx))["KYA-OPF-01"]
    assert f.kind == "breach"
