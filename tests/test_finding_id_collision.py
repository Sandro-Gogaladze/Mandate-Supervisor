import pytest

# PARKED — migration-plan.md Phase 2/3.
#
# These cover finding id uniqueness, which is real and still wanted. They are parked because
# their FIXTURE is gone: every one built its case from data/cases/*.json, and
# the corpus is now two dossiers with a different shape.
#
# Parked rather than deleted, and loudly rather than quietly: the logic under
# test did not stop mattering, and a silently shrinking suite is how a
# migration loses coverage nobody notices. Each comes back when the pipeline
# consumes a Dossier and a dossier fixture exists to replace the case one.
pytestmark = pytest.mark.skip(reason="fixture removed with the case corpus — migration Phase 2/3")

"""Stage 0 regression test (docs/architecture-v2.md §Stage 0).

The credential and chain verifiers each mint finding_ids from their own
counter. Before the prefix split, both produced `<case_id>-FND-001`, so a
case with BOTH a bad credential and a broken chain yielded two findings
under one id — and pipeline/state.py's dedup reducer, keyed on finding_id,
silently dropped one. The corpus never triggers it (case-003 has no crypto
defect, case-004 has no chain break), which is why nothing caught it.
"""
from __future__ import annotations

import json

from agents.kya import KYAAgent
from agents.mandate import MandateAgent
from data.loader import DATA_DIR
from ingestion.normalize import build_verification_context, normalize_case
from pipeline.state import _add_findings
from registry.loader import load_kya_ruleset, load_mandate_ruleset


def test_both_defect_classes_survive_the_dedup_reducer(tmp_path) -> None:
    # case-003 already has the broken chain; corrupt the credential signature
    # too so both verifiers produce their first finding for the same case.
    raw = json.loads((DATA_DIR / "cases" / "case-003-broken-chain.json").read_text())
    raw["kya_credential"]["signature"]["value"] = "A" * 86 + "=="
    case_file = tmp_path / "case-both-defects.json"
    case_file.write_text(json.dumps(raw))

    case = normalize_case(case_file, build_verification_context())
    mandate_findings = MandateAgent().run(case, load_mandate_ruleset())
    kya_findings = KYAAgent().run(case, load_kya_ruleset())

    chain = [f for f in mandate_findings if f.type == "chain_hash_mismatch"]
    sig = [f for f in kya_findings if f.type == "signature_invalid"]
    assert chain and sig, "both defect classes must be detected at all"

    ids = [f.finding_id for f in mandate_findings + kya_findings]
    assert len(ids) == len(set(ids)), f"finding_id collision: {ids}"

    merged = _add_findings(_add_findings([], mandate_findings), kya_findings)
    merged_types = {f.type for f in merged}
    assert "chain_hash_mismatch" in merged_types
    assert "signature_invalid" in merged_types, (
        "the dedup reducer dropped the credential finding — id collision is back"
    )
