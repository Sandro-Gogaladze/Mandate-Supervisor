import pytest

# PARKED — migration-plan.md Phase 2/3.
#
# These cover ingestion, which is real and still wanted. They are parked because
# their FIXTURE is gone: every one built its case from data/cases/*.json, and
# the corpus is now two dossiers with a different shape.
#
# Parked rather than deleted, and loudly rather than quietly: the logic under
# test did not stop mattering, and a silently shrinking suite is how a
# migration loses coverage nobody notices. Each comes back when the pipeline
# consumes a Dossier and a dossier fixture exists to replace the case one.
pytestmark = pytest.mark.skip(reason="fixture removed with the case corpus — migration Phase 2/3")

from copy import deepcopy

from data.loader import CASES_DIR, DATA_DIR, load_raw_case_json
from ingestion.normalize import IngestedCase, normalize_case, normalize_corpus
from ingestion.verify import build_verification_context, verify_case

EXPECTED_FINDINGS = {
    "CASE-2026-001": [],
    "CASE-2026-002": [],
    "CASE-2026-003": [("mandate", "chain_hash_mismatch", "MND-CHN-02")],
    "CASE-2026-004": [("kya", "issuer_not_in_trust_registry", "KYA-ISS-01")],
    "CASE-2026-005": [],
    "CASE-2026-006": [],
    "CASE-2026-007": [],
    "CASE-2026-101": [],
    "CASE-2026-102": [],
    "CASE-2026-103": [],
}


def test_normalize_corpus_produces_exactly_the_expected_ingestion_findings() -> None:
    for ic in normalize_corpus():
        actual = [(f.agent, f.type, f.rule_id) for f in ic.findings]
        assert actual == EXPECTED_FINDINGS[ic.case.case_id], ic.case.case_id


def test_normalize_case_strips_label_and_narrative() -> None:
    ic = normalize_case(CASES_DIR / "case-001-compliant.json")
    assert ic.case.label is None
    assert ic.case.narrative is None
    assert ic.clean


def test_clean_case_has_no_findings_and_is_clean() -> None:
    ic = normalize_case(CASES_DIR / "case-001-compliant.json")
    assert ic.findings == []
    assert ic.clean is True


def test_broken_chain_case_is_not_clean() -> None:
    ic = normalize_case(CASES_DIR / "case-003-broken-chain.json")
    assert ic.clean is False
    assert len(ic.findings) == 1


def test_finding_ids_are_unique_within_a_case() -> None:
    raw = load_raw_case_json(CASES_DIR / "case-004-synthetic-identity.json")
    findings = verify_case(raw)
    ids = [f.finding_id for f in findings]
    assert len(ids) == len(set(ids))
    assert all(f.case_id == "CASE-2026-004" for f in findings)


def test_tampering_a_credential_signature_produces_a_finding_not_a_crash() -> None:
    """The whole point of ingestion's graceful-handling requirement: a
    broken submission must come back as data, never an unhandled exception."""
    raw = load_raw_case_json(CASES_DIR / "case-001-compliant.json")
    tampered = deepcopy(raw)
    tampered["kya_credential"]["signature"]["value"] = "not-a-real-signature=="

    findings = verify_case(tampered)  # must not raise

    types = {f.type for f in findings}
    assert "signature_invalid" in types


def test_tampering_a_chain_link_produces_a_mandate_finding() -> None:
    raw = load_raw_case_json(CASES_DIR / "case-001-compliant.json")
    tampered = deepcopy(raw)
    tampered["mandate_chain"]["payment"]["chain_link"]["prev_mandate_hash"] = "sha256:" + "0" * 64

    findings = verify_case(tampered)

    assert any(f.type == "chain_hash_mismatch" and f.agent == "mandate" for f in findings)


def test_verification_context_is_reusable_across_cases() -> None:
    context = build_verification_context()
    results = [normalize_case(DATA_DIR / "cases" / f"case-00{i}-{name}.json", context)
               for i, name in enumerate(
                   ["compliant", "mandate-breaching", "broken-chain"], start=1)]
    assert [r.case.case_id for r in results] == ["CASE-2026-001", "CASE-2026-002", "CASE-2026-003"]


def test_unknown_signer_key_id_fails_signature_not_raises() -> None:
    raw = load_raw_case_json(CASES_DIR / "case-001-compliant.json")
    tampered = deepcopy(raw)
    tampered["kya_credential"]["signature"]["signer_key_id"] = "did:key:z6MkNoSuchSigner"

    findings = verify_case(tampered)  # must not KeyError

    assert any(f.type == "signature_invalid" for f in findings)
