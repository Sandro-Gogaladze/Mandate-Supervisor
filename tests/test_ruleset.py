import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from data.loader import iter_corpus_labeled
from schemas import typed_params
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
    # v2026.4: 42 rules across eight families, 23 active. The 18 that were
    # active at v2026.1 keep their types, severities and finding_types, so no
    # case's score moved — re-weighting is dial 11 and belongs in the policy
    # sandbox, not in a restructure.
    #
    # The thirteen promoted at v2026.4-5 were unblocked by DATA, not by code:
    # five needed a registry field that did not exist (ISS-05, OPF-01, REG-04,
    # REG-05, LIF-05), and eight needed submission blocks the old shape had no
    # room for — granted_capabilities (ACC-06), credential_history (CAP-05,
    # LIF-04) and construction_context (TEC-02..06). That is what a draft rule
    # IS here: one whose evidence the submission cannot yet carry.
    #
    # The 11 still draft need cross-case ledger history (IDN-04/05), judgement
    # the sandbox has to tune (CAP-03/04, REG-03), or data deliberately not
    # required of firms.
    assert len(rs.rules) == 42
    assert len(active) == 37
    assert len(draft) == 5
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


def test_typed_params_validates_configured_rule() -> None:
    rs = load_kya_ruleset()
    cap_rule = next(r for r in rs.rules if r.rule_id == "KYA-CAP-02")
    params = typed_params(cap_rule)
    assert isinstance(params, CapabilityVocabularyAllowlistParams)
    assert "cart_construction" in params.allowed_exact


def test_no_params_rule_rejects_unexpected_params() -> None:
    rs = load_kya_ruleset()
    raw = rs.model_dump()
    no_params_rule = next(r for r in raw["rules"] if r["rule_id"] == "KYA-ISS-01")
    no_params_rule["params"] = {"unexpected": True}
    with pytest.raises(ValidationError):
        Rule.model_validate(no_params_rule)


def test_the_capability_vocabulary_admits_every_capability_the_corpus_uses() -> None:
    """A vocabulary that cannot name a lawful capability is a bad vocabulary.

    Replaces three tests that asserted things about the deleted seven-case
    corpus. It is the same guarantee against the data that now exists: if an
    operator is doing something legitimate the allowlist has no word for, it
    must either mislabel it or breach, and neither is a pressure a supervisor
    should be applying.
    """
    from data.dossier_loader import list_dossiers, load

    rs = load_kya_ruleset()
    rule = next(r for r in rs.rules if r.rule_id == "KYA-CAP-02")
    params = typed_params(rule)
    for path in list_dossiers():
        d = load(path)
        for cred in [d.dossier.kya_credential, *d.dossier.credential_history]:
            for cap in cred.capabilities:
                assert cap in params.allowed_exact or any(
                    cap.startswith(pre) for pre in params.allowed_prefixes), (
                    f"{cred.credential_id} uses capability {cap!r}, which the vocabulary "
                    f"cannot express")
