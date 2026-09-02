import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from data.loader import iter_corpus_labeled
from registry.loader import active_rules, load_kya_ruleset, rules_by_finding_type
from schemas import Rule, Ruleset, typed_params
from schemas.ruleset import CapabilityVocabularyAllowlistParams

MANIFEST_PATH = Path(__file__).resolve().parent.parent / "data" / "corpus_manifest.json"


def test_kya_ruleset_loads_and_ids_are_unique() -> None:
    rs = load_kya_ruleset()
    assert rs.domain == "kya"
    ids = [r.rule_id for r in rs.rules]
    assert len(ids) == len(set(ids))


def test_ruleset_rejects_duplicate_rule_ids() -> None:
    rs = load_kya_ruleset()
    dupe = rs.model_dump()
    dupe["rules"].append(dupe["rules"][0])
    with pytest.raises(ValidationError):
        Ruleset.model_validate(dupe)


def test_active_vs_draft_split() -> None:
    rs = load_kya_ruleset()
    active = active_rules(rs)
    draft = [r for r in rs.rules if r.status == "draft"]
    # v2026.3 restructure (docs/kya-ruleset.md): 42 rules across eight
    # families. The 18 active ones carry their v2026.1 types, severities and
    # finding_types unchanged, so no case's score moved — re-weighting is
    # dial 11 and belongs in the policy sandbox, not in a restructure.
    assert len(rs.rules) == 42
    assert len(active) == 18
    assert len(draft) == 24
    # every draft rule must explain what blocks it
    assert all(r.notes for r in draft)


def test_core_identity_rules_are_active() -> None:
    rs = load_kya_ruleset()
    active_types = {r.type for r in active_rules(rs)}
    for must_be_active in [
        "issuer_trust_required",
        "issuer_status_active",
        "signature_must_verify",
        "delegation_chain_terminates_in_human",
    ]:
        assert must_be_active in active_types


def test_corpus_kya_ground_truth_traces_to_an_active_rule() -> None:
    """Every KYA finding_type in the labelled corpus must map to a real,
    active rule — this is what actually ties the ruleset to eval ground
    truth (PLAN item 16), not just to the vocabulary in the abstract."""
    rs = load_kya_ruleset()
    by_finding_type = rules_by_finding_type(rs)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    checked = 0
    for case in manifest["cases"]:
        for finding in case["expected_findings"]:
            if finding["agent"] != "kya":
                continue
            assert finding["type"] in by_finding_type, (
                f"{case['case_id']}: expected KYA finding {finding['type']!r} "
                f"has no active rule producing it"
            )
            checked += 1
    assert checked > 0  # sanity: the corpus actually exercises KYA


def test_typed_params_validates_configured_rule() -> None:
    rs = load_kya_ruleset()
    cap_rule = next(r for r in rs.rules if r.rule_id == "KYA-CAP-02")
    params = typed_params(cap_rule)
    assert isinstance(params, CapabilityVocabularyAllowlistParams)
    assert "cart_construction" in params.allowed_exact


def test_capability_allowlist_covers_every_case_in_the_corpus() -> None:
    """The allowlist params were derived from the real corpus (not
    guessed) — confirm every capability string in every case is actually
    covered, so KYA-CAP-02 wouldn't false-positive on the corpus itself."""
    rs = load_kya_ruleset()
    cap_rule = next(r for r in rs.rules if r.rule_id == "KYA-CAP-02")
    params: CapabilityVocabularyAllowlistParams = typed_params(cap_rule)

    def covered(capability: str) -> bool:
        if capability in params.allowed_exact:
            return True
        return any(capability.startswith(p) for p in params.allowed_prefixes)

    for _entry, case in iter_corpus_labeled():
        for capability in case.kya_credential.capabilities:
            assert covered(capability), f"{case.case_id}: {capability!r} not covered by KYA-CAP-02"


def test_new_active_rules_have_no_bite_on_the_current_corpus() -> None:
    """KYA-ISS-04 is documented as 'no bite yet on this corpus' — confirm
    that's actually true rather than just asserted in the description, and
    that KYA-LIF-02's date ordering holds for every case.

    consent_method_allowlist used to be checked here as KYA-CON-01. It moved
    out of KYA entirely in v2026.3: KYA answers identity and standing, and
    whether consent was validly obtained is the Consent & Harm domain's
    question (docs/kya-ruleset.md Part 6)."""
    from datetime import date

    rs = load_kya_ruleset()
    by_id = {r.rule_id: r for r in rs.rules}
    issuers = {
        i["issuer_id"]: i
        for i in json.loads(
            (Path(__file__).resolve().parent.parent / "data" / "registry" / "issuers.json").read_text()
        )["issuers"]
    }

    iss04 = typed_params(by_id["KYA-ISS-04"])
    as_of = date.fromisoformat(rs.as_of)

    for _entry, case in iter_corpus_labeled():
        cred = case.kya_credential
        assert date.fromisoformat(cred.issued_at[:10]) < date.fromisoformat(cred.expires_at[:10])

        issuer = issuers.get(cred.issuer.issuer_id)
        if issuer is None:
            continue  # unlisted issuer (case-004) — KYA-ISS-01's job, not this rule's
        accredited_since = date.fromisoformat(issuer["accredited_since"])
        assert (as_of - accredited_since).days <= iss04.max_reaccreditation_age_days

        consent_method = case.mandate_chain.intent.consent.method


def test_no_params_rule_rejects_unexpected_params() -> None:
    rs = load_kya_ruleset()
    raw = rs.model_dump()
    no_params_rule = next(r for r in raw["rules"] if r["rule_id"] == "KYA-ISS-01")
    no_params_rule["params"] = {"unexpected": True}
    with pytest.raises(ValidationError):
        Rule.model_validate(no_params_rule)
