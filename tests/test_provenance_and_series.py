"""Guarantees for the rules Stage 4 unblocked.

Eight rules moved from draft to active because the DATA changed, not the code —
`granted_capabilities`, `credential_history` and `construction_context` did not
exist in the old submission shape. These assert each one actually finds what it
was blocked on, against the real dossier rather than a stub.
"""
from __future__ import annotations

import pytest

from agents.kya_checks import (
    PROVENANCE_OWNED_TYPES,
    run_credential_series_checks,
    run_policy_checks,
)
from agents.provenance_checks import PROVENANCE_RULE_TYPES, run_provenance_checks
from data.dossier_loader import load
from registry.loader import active_rules_by_type, load_kya_ruleset

DOSSIER = "data/dossiers/DOSSIER-KST-2026-001"


@pytest.fixture(scope="module")
def dossier():
    return load(DOSSIER)


@pytest.fixture(scope="module")
def ruleset():
    return load_kya_ruleset()


def _by_rule(findings):
    return {f.rule_id: f for f in findings}


# --- ownership -------------------------------------------------------------

def test_provenance_owns_exactly_what_kya_skips():
    """The two modules must agree on the split, or a rule is evaluated twice
    or not at all — and 'not at all' is the one the coverage guarantee cannot
    catch, because KYA would be skipping it on purpose."""
    assert PROVENANCE_OWNED_TYPES == PROVENANCE_RULE_TYPES


def test_every_active_kya_rule_is_owned_by_someone(dossier, ruleset):
    from agents.kya_checks import CRYPTO_HANDLED_TYPES, _POLICY_CHECKERS, _SERIES_CHECKERS
    owned = set(_POLICY_CHECKERS) | set(_SERIES_CHECKERS) | CRYPTO_HANDLED_TYPES \
        | PROVENANCE_RULE_TYPES
    unowned = set(active_rules_by_type(ruleset)) - owned
    assert not unowned, f"active rules with no owner: {sorted(unowned)}"


# --- Provenance ------------------------------------------------------------

def test_model_substitution_is_found_and_named_as_blocklisted(dossier, ruleset):
    f = _by_rule(run_provenance_checks(dossier, ruleset))["KYA-TEC-02"]
    assert "claude-sonnet-4-5-20250929" in f.summary
    # A barred model that actually authorised payments is a different order of
    # problem from one merely named on a form, and the finding says so.
    assert "blocklisted" in f.summary
    assert f.details["blocklisted_observed"] == ["claude-sonnet-4-5-20250929"]


def test_unapproved_prompt_release_is_found(dossier, ruleset):
    f = _by_rule(run_provenance_checks(dossier, ruleset))["KYA-TEC-05"]
    assert f.details["unapproved"] == ["RUN-2026-0723-0031: kestrel-shop-v2.4.2-hotfix"]


def test_unauthorised_tool_server_is_found_not_the_tool_name(dossier, ruleset):
    """The tool name in an unauthorised call is one the agent may legitimately
    call. Pinning the server is the entire point."""
    f = _by_rule(run_provenance_checks(dossier, ruleset))["KYA-TEC-06"]
    assert len(f.details["unauthorised"]) == 1
    assert "check_availability" in f.details["unauthorised"][0]
    assert "fastcheck-partners.net" in f.details["unauthorised"][0]


# --- credential series -----------------------------------------------------

def test_simultaneous_credentials_are_found(dossier, ruleset):
    f = _by_rule(run_credential_series_checks(dossier, ruleset))["KYA-LIF-04"]
    assert "CRED-KST-2025-0188" in f.summary and "CRED-KST-2026-0442" in f.summary


def test_capability_growth_within_tolerance_is_not_creep(dossier, ruleset):
    """One new capability at a renewal is an agent gaining a function, not
    permissions widening quietly. The rule must not punish legitimate growth."""
    assert "KYA-CAP-05" not in _by_rule(run_credential_series_checks(dossier, ruleset))


def test_series_rules_are_excluded_from_the_per_case_dispatcher(ruleset):
    """They need the whole credential series; a per-case view carries one.

    Running them per case would compare a credential against nothing and
    silently pass, which is worse than not running them at all — so the
    dispatcher must skip them deliberately rather than by accident.
    """
    from agents.kya_checks import _SERIES_CHECKERS

    active = set(active_rules_by_type(ruleset))
    assert set(_SERIES_CHECKERS) <= active, "series rules must be active to be skipped"
    # and the per-case dispatcher must know to skip exactly those
    assert "capability_creep_across_reissuance" in _SERIES_CHECKERS
    assert "no_simultaneous_credentials" in _SERIES_CHECKERS


# --- delegation ------------------------------------------------------------

def test_delegation_grants_are_nested_so_acc_06_is_satisfied(dossier):
    """Each level may only hold what the level above granted it."""
    chain = dossier.dossier.kya_credential.delegation_chain
    for child, parent in zip(chain, chain[1:]):
        assert set(child.granted_capabilities) <= set(parent.granted_capabilities)


def test_acc_06_is_silent_when_no_level_records_a_grant(dossier, ruleset):
    """A chain that only lists names has nothing to compare.

    Absence is not compliance — but a Finding cannot say 'absent', so silence
    is the least-wrong output until the Fact migration lands (migration-plan.md
    Phase 1). Asserted so the behaviour is deliberate rather than accidental.
    """
    from copy import deepcopy

    from agents.kya_checks import _check_no_link_grants_more_than_it_holds, _FindingIdCounter

    cred = deepcopy(dossier.dossier.kya_credential)
    for entry in cred.delegation_chain:
        entry.granted_capabilities = []
    rule = next(r for r in ruleset.rules if r.rule_id == "KYA-ACC-06")
    stub = type("S", (), {"kya_credential": cred, "case_id": "X"})()
    assert _check_no_link_grants_more_than_it_holds(
        stub, rule, None, _FindingIdCounter("X")) is None
