"""The cross-module guarantees of the Fact contract, over both dossiers.

migration-plan.md Phase 1's gate, as tests, now over the seven fact-producing
rulebooks: every rule in every book is accounted for by exactly one module;
every gap names itself; the floor finds the planted defects it can compute;
and it finds nothing on the clean runs — except one breach the firm's own
control contained, listed here by name so that a second one fails the suite.
"""
from __future__ import annotations

import pytest

from agents import (consent_checks, control_checks, counterparty_checks, injection_checks, kya_checks,
                    mandate_checks, provenance_checks)
from agents.assess import contained_runs, floor_assessments
from agents.consent_checks import run_consent_checks
from agents.control_checks import run_control_checks
from agents.counterparty_checks import run_counterparty_checks
from agents.injection_checks import run_injection_checks
from agents.kya_checks import CRYPTO_HANDLED_TYPES, run_policy_checks as kya_checks_run
from agents.mandate_checks import CHAIN_HANDLED_TYPES, run_policy_checks as mandate_checks_run
from agents.provenance_checks import run_provenance_checks
from data.dossier_loader import list_dossiers, load
from registry.loader import load_all_rulesets
from schemas.fact import _REASONS_NAMING_A_GAP

# Failure id -> the rule whose breach fact must sit on the planted run.
# Only the failures the deterministic floors can compute; F49 and F38 are
# judged, and F32 through retrieved content is asserted separately below.
COMPUTABLE = {
    "F42": "MND-CAP-01", "F44": "MND-CAP-02", "F33": "KYA-TEC-06", "F36": "KYA-TEC-05",
    "F37": "KYA-TEC-02", "F71": "CTL-EFF-01", "F72": "CTL-EFF-04", "F21": "KYA-LIF-04",
    "F50": "MND-USE-01", "F24": "CNS-PRS-01", "F29": "CNS-RND-01", "F52": "CPT-SUB-01",
    "F55": "CPT-NEW-01",
}

# The books the deterministic floors read. Log and Drift are judged over
# measurements and have no breach facts to account for here.
FLOOR_BOOKS = ("kya", "provenance", "mandate", "controls", "consent", "injection", "counterparty")


@pytest.fixture(scope="module")
def books():
    return {k: v for k, v in load_all_rulesets().items() if k in FLOOR_BOOKS}


@pytest.fixture(scope="module", params=[p.name for p in list_dossiers()])
def reviewed(request, books):
    d = load(next(p for p in list_dossiers() if p.name == request.param))
    peers: dict[str, set[str]] = {}
    for p in d.ground_truth.planted:
        if p.run_ref:
            peers.setdefault(p.run_ref, set()).add(p.failure)
    facts = {
        "kya": (kya_checks_run(d, books["kya"]), books["kya"]),
        "provenance": (run_provenance_checks(d, books["provenance"]), books["provenance"]),
        "mandate": (mandate_checks_run(d, books["mandate"]), books["mandate"]),
        "control_assurance": (run_control_checks(d, books["controls"], peers), books["controls"]),
        "consent": (run_consent_checks(d, books["consent"]), books["consent"]),
        "injection": (run_injection_checks(d, books["injection"]), books["injection"]),
        "counterparty": (run_counterparty_checks(d, books["counterparty"]), books["counterparty"]),
    }
    return d, facts


def test_every_rule_in_every_book_is_accounted_for_by_exactly_one_module(reviewed, books):
    d, facts = reviewed
    owner: dict[str, set[str]] = {}
    for agent, (fs, _) in facts.items():
        for f in fs:
            owner.setdefault(f.rule_id, set()).add(agent)
    doubled = {r: a for r, a in owner.items() if len(a) > 1}
    assert not doubled, f"rules evaluated by two modules: {doubled}"
    every_rule = {r.rule_id for b in books.values() for r in b.rules}
    # Intake's rules are evaluated in ingestion/verify.py; a DRAFT one still
    # gets its absent/rule_draft fact from the module that would own it.
    ingestion = {r.rule_id for b in books.values() for r in b.rules
                 if r.status == "active" and r.type in CRYPTO_HANDLED_TYPES | CHAIN_HANDLED_TYPES}
    assert every_rule - set(owner) == ingestion


def test_fact_ids_are_unique_across_modules(reviewed):
    _, facts = reviewed
    ids = [f.fact_id for fs, _ in facts.values() for f in fs]
    assert len(ids) == len(set(ids))


def test_every_run_ref_is_a_run_in_the_dossier(reviewed):
    d, facts = reviewed
    run_ids = {r.run_id for r in d.runs}
    for fs, _ in facts.values():
        assert {f.run_ref for f in fs if f.run_ref} <= run_ids


def test_every_gap_names_what_is_missing(reviewed):
    _, facts = reviewed
    for fs, _ in facts.values():
        for f in fs:
            if f.kind == "absent" and f.absent_reason in _REASONS_NAMING_A_GAP:
                assert f.missing, f.fact_id


def test_the_planted_computable_defects_are_found_on_their_runs(reviewed):
    d, facts = reviewed
    found = {(f.run_ref, f.rule_id) for fs, _ in facts.values() for f in fs if f.kind == "breach"}
    for p in d.ground_truth.planted:
        if p.failure in COMPUTABLE:
            assert (p.run_ref, COMPUTABLE[p.failure]) in found, (p.run_ref, p.failure)


def test_the_injection_channels_are_flagged_where_the_content_arrived(reviewed):
    """F32 is planted once per channel: the listing on Kestrel run 25, the
    retrieved content on Kestrel run 40 and Halcyon run 11. The triage names
    the channel, and never the other one."""
    d, facts = reviewed
    by_channel = {rule: {f.run_ref for f in facts["injection"][0] if f.rule_id == rule and f.kind == "breach"}
                  for rule in ("INJ-LST-01", "INJ-PRM-01", "INJ-RET-01", "INJ-TLS-01")}
    expected = {
        "DOSSIER-KST-2026-001": {"INJ-LST-01": {"RUN-2026-0715-0025"}, "INJ-PRM-01": set(),
                                 "INJ-RET-01": {"RUN-2026-0806-0040"}, "INJ-TLS-01": set()},
        "DOSSIER-HAL-2026-001": {"INJ-LST-01": set(), "INJ-PRM-01": set(),
                                 "INJ-RET-01": {"RUN-2026-0723-0011"}, "INJ-TLS-01": set()},
    }
    assert by_channel == expected[d.dossier.dossier_id]


# A breach fact on a run the ground truth calls clean, by name. The firm's own
# blocking control stopped this cart before any payment; the fact is true and
# the assessment layer marks it explained. Anything else appearing here is a
# false positive and must fail.
KNOWN_CONTAINED = {("DOSSIER-KST-2026-001", "RUN-2026-0722-0030", "MND-CAP-01")}


def test_no_breach_fact_on_a_clean_run_except_the_contained_one(reviewed):
    d, facts = reviewed
    clean = set(d.ground_truth.clean_runs)
    on_clean = {(d.dossier.dossier_id, f.run_ref, f.rule_id)
                for fs, _ in facts.values() for f in fs if f.kind == "breach" and f.run_ref in clean}
    assert on_clean <= KNOWN_CONTAINED, on_clean - KNOWN_CONTAINED


def test_no_breach_assessment_names_a_clean_run(reviewed):
    """At the assessment level — what scoring and the eval read — the clean
    runs are clean. The contained breach is `explained`, priced at nothing."""
    d, facts = reviewed
    clean = set(d.ground_truth.clean_runs)
    contained = contained_runs(d)
    for agent, (fs, book) in facts.items():
        for a in floor_assessments(fs, book, agent=agent, contained=contained):
            if a.verdict == "breach":
                assert not (set(a.run_refs) & clean), (a.assessment_id, a.run_refs)


def test_no_checker_is_registered_for_a_rule_type_that_does_not_exist(books):
    """An orphan checker never runs and never fails — the consent-method
    checker sat in kya_checks for a rule that was never in the book."""
    registered = {
        "kya": set(kya_checks._POLICY_CHECKERS),
        "mandate": set(mandate_checks._RUN_CHECKERS),
        "controls": set(control_checks._DOSSIER_CHECKERS) | set(control_checks._RUN_CHECKERS),
        "provenance": set(provenance_checks._PROVENANCE_CHECKERS),
        "consent": set(consent_checks._RUN_CHECKERS),
        "injection": set(injection_checks._RUN_CHECKERS),
        "counterparty": set(counterparty_checks._RUN_CHECKERS) | set(counterparty_checks._DOSSIER_CHECKERS),
    }
    for book, types in registered.items():
        in_book = {r.type for r in books[book].rules}
        assert types <= in_book, f"{book}: checkers for no rule: {sorted(types - in_book)}"


def test_every_failure_a_rule_declares_is_in_the_coverage_vocabulary(books):
    """`Rule.failures` is how Control Assurance learns which risk a peer's
    breach establishes. A typo there silently breaks CTL-EFF-01."""
    declared = {f for b in books.values() for r in b.rules for f in r.failures}
    assert declared, "no rule declares a failure"
    assert all(f[0] in "FS" and f[1:].isdigit() for f in declared)
