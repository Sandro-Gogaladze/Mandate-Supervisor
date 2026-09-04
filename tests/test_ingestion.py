"""Intake — a `LoadedDossier` in, an `EvidencePack` out, no model.

The eight cryptographic/chain rules are facts now (Phase 1's contract,
completed in Phase 2); a broken submission comes back as data, never as an
exception; and the whole thing round-trips through the ledger payload.
"""
from __future__ import annotations

import pytest

from agents.facts import breaches, by_rule
from ingestion.normalize import (
    SubmissionInvalid,
    dossier_from_submission,
    normalize_dossier,
    submission_payload,
)
from ingestion.verify import RawSubmissionMissing, chain_facts_with_ruleset, credential_facts_with_ruleset, verify_dossier
from registry.loader import load_kya_ruleset, load_mandate_ruleset
from tests.corpus import with_raw


@pytest.fixture(scope="module")
def pack(kst):
    return normalize_dossier(kst)


# --- the pack ----------------------------------------------------------------

def test_the_pack_describes_the_submission(pack, kst):
    assert pack.run_ids == [r.run_id for r in kst.runs]
    assert pack.runs_by_outcome == {"completed": 47, "abandoned": 1, "blocked": 1, "failed": 1}
    assert (pack.transactions_total, pack.transactions_in_window, pack.transactions_trailing) == (102, 47, 55)
    assert pack.in_window_without_run == []
    assert pack.submission.runs_submitted == pack.submission.runs_filed == 50
    # what the runs observed vs what will be deployed — S3's raw comparison
    assert "kestrel-shop-v2.4.2-hotfix" in pack.submission.observed_release_refs
    assert pack.submission.deployment_prompt_release_ref not in pack.submission.observed_release_refs


def test_blocks_present_are_recorded_per_run(pack):
    assert pack.blocks["agent_card"] and pack.blocks["credential_history"] and pack.blocks["change_log"]
    failed = pack.run_blocks["RUN-2026-0724-0032"]
    assert failed["cart"] is False and failed["payment"] is False and failed["consent_ceremony"] is False
    assert pack.run_blocks["RUN-2026-0810-0042"]["consent_ceremony"] is False  # the F24 run
    assert pack.runs_without("payment") == ["RUN-2026-0624-0010", "RUN-2026-0722-0030", "RUN-2026-0724-0032"]
    assert len(pack.runs_with("sub_merchant")) == 0


def test_registries_resolve_and_signatures_verify(pack):
    r = pack.registries
    assert (r.institution, r.operator, r.agent, r.issuer) == (True, True, True, True)
    assert r.operator_name == "Kestrel Commerce, Inc." and r.agent_classification == "consumer_shopping"
    assert r.unresolved_merchants == []
    i = pack.integrity
    assert i.signatures_checked == 158 and i.signature_failures == []
    assert i.chain_links_checked == 96 and i.chain_links_broken == []


def test_shared_statistics_are_computed_once(pack):
    assert pack.counterparties[0].counterparty_id == "MER-VLT-7789"
    assert pack.counterparties[0].registered is True
    assert abs(sum(c.share for c in pack.counterparties) - 1.0) < 1e-3
    assert pack.amounts.count == 102 and pack.amounts.max == 867.0
    assert pack.drift.sufficient and pack.drift.baseline_count + pack.drift.comparison_count == 102
    assert pack.controls.evaluations == 450 and pack.controls.triggered == 2 and pack.controls.overridden == 1


def test_the_eight_intake_rules_are_facts(pack):
    grouped = by_rule(pack.ingestion_facts)
    dossier_level = {"KYA-IDN-01", "KYA-IDN-02", "KYA-IDN-03", "KYA-ACC-03", "KYA-ISS-01", "KYA-ISS-02"}
    assert {rid for rid in grouped if not grouped[rid][0].run_ref} == dossier_level
    assert all(grouped[rid][0].kind == "satisfied" for rid in dossier_level)
    assert {f.kind for f in grouped["MND-CHN-01"]} == {"satisfied", "absent"}
    assert len(grouped["MND-CHN-01"]) == 50 and len(grouped["MND-CHN-02"]) == 50
    assert sum(1 for f in grouped["MND-CHN-02"] if f.absent_reason == "out_of_scope") == 3


# --- a broken submission comes back as data --------------------------------

def test_a_tampered_credential_signature_is_a_breach_not_a_crash(kst):
    def forge(raw, runs):
        raw["kya_credential"]["signature"]["value"] = "A" * 86 + "=="
    facts = credential_facts_with_ruleset(with_raw(kst, forge), load_kya_ruleset())
    f, = [f for f in facts if f.rule_id == "KYA-IDN-01"]
    assert f.kind == "breach" and "CRED-KST-2026-0442" in f.values["failed"]
    # the payload hash is over the content, not the signature — still recomputes
    assert next(f for f in facts if f.rule_id == "KYA-IDN-03").kind == "satisfied"
    _, integrity = verify_dossier(with_raw(kst, forge))
    assert integrity.signature_failures == ["credential CRED-KST-2026-0442"]


def test_an_unknown_signer_fails_verification_rather_than_raising(kst):
    def unknown(raw, runs):
        raw["kya_credential"]["signature"]["signer_key_id"] = "did:key:z6MkNoSuchSigner"
    facts = credential_facts_with_ruleset(with_raw(kst, unknown), load_kya_ruleset())
    assert next(f for f in facts if f.rule_id == "KYA-IDN-01").kind == "breach"


def test_a_tampered_chain_link_is_a_breach_on_that_run(kst):
    def cut(raw, runs):
        runs["RUN-2026-0811-0043"]["payment"]["chain_link"]["prev_mandate_hash"] = "sha256:" + "0" * 64
    facts = chain_facts_with_ruleset(with_raw(kst, cut), load_mandate_ruleset())
    bad = breaches(facts)
    assert [(f.rule_id, f.run_ref) for f in bad] == [("MND-CHN-02", "RUN-2026-0811-0043")]
    _, integrity = verify_dossier(with_raw(kst, cut))
    assert integrity.chain_links_broken == ["RUN-2026-0811-0043 payment->cart"]


def test_an_unknown_issuer_breaches_iss_01_and_absents_iss_02(kst):
    def reissue(raw, runs):
        raw["kya_credential"]["issuer"]["issuer_id"] = "ISS-999"
    facts = by_rule(credential_facts_with_ruleset(with_raw(kst, reissue), load_kya_ruleset()))
    assert facts["KYA-ISS-01"][0].kind == "breach"
    f, = facts["KYA-ISS-02"]
    assert (f.kind, f.absent_reason, f.missing) == ("absent", "no_registry_record", "registry:issuers[ISS-999]")


def test_the_draft_signature_rule_runs_the_moment_it_is_promoted(kst):
    """MND-SIG-01 exists because intake verified every signature and no rule
    turned a failure into a fact. Draft → nothing from intake; active → one
    fact per run, and a forged cart is a breach."""
    book = load_mandate_ruleset()
    assert not [f for f in chain_facts_with_ruleset(kst, book) if f.rule_id == "MND-SIG-01"]
    promoted = book.model_copy(update={"rules": [
        r.model_copy(update={"status": "active"}) if r.rule_id == "MND-SIG-01" else r
        for r in book.rules]})
    facts = [f for f in chain_facts_with_ruleset(kst, promoted) if f.rule_id == "MND-SIG-01"]
    assert len(facts) == 50 and {f.kind for f in facts} == {"satisfied"}

    def forge(raw, runs):
        runs["RUN-2026-0811-0043"]["cart"]["signature"]["value"] = "A" * 86 + "=="
    forged = [f for f in chain_facts_with_ruleset(with_raw(kst, forge), promoted)
              if f.rule_id == "MND-SIG-01" and f.kind == "breach"]
    assert [(f.run_ref, f.values["failed"]) for f in forged] == [("RUN-2026-0811-0043", ["cart"])]


def test_a_dossier_without_its_raw_submission_cannot_be_verified(kst):
    bare = kst.model_copy(update={"raw_dossier": None, "raw_runs": {}})
    with pytest.raises(RawSubmissionMissing):
        verify_dossier(bare)


# --- the ledger shape ----------------------------------------------------------

def test_a_submission_round_trips_through_its_ledger_payload(kst, pack):
    payload = submission_payload(kst)
    assert payload["case_id"] == "DOSSIER-KST-2026-001"
    assert payload["firm"]["name"] == "Kestrel Commerce, Inc."
    assert "ground_truth" not in payload and len(payload["runs"]) == 50
    rebuilt = dossier_from_submission(payload)
    assert rebuilt.ground_truth is None
    assert [r.run_id for r in rebuilt.runs] == [r.run_id for r in kst.runs]
    again = normalize_dossier(rebuilt)
    assert [(f.fact_id, f.kind) for f in again.ingestion_facts] == \
        [(f.fact_id, f.kind) for f in pack.ingestion_facts]
    assert again.integrity == pack.integrity


def test_a_payload_that_is_not_a_dossier_is_refused_loudly():
    with pytest.raises(SubmissionInvalid):
        dossier_from_submission({"case_id": "X", "dossier": {"not": "a dossier"}})


def test_halcyon_is_clean_at_intake(hal):
    pack = normalize_dossier(hal)
    assert pack.integrity.signature_failures == [] and pack.integrity.signatures_checked == 68
    assert not breaches(pack.ingestion_facts)
    assert pack.runs_by_outcome == {"completed": 20}
