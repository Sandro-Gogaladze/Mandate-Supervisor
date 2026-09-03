import pytest

# PARKED — migration-plan.md Phase 2/3.
#
# These cover agent behaviour, which is real and still wanted. They are parked because
# their FIXTURE is gone: every one built its case from data/cases/*.json, and
# the corpus is now two dossiers with a different shape.
#
# Parked rather than deleted, and loudly rather than quietly: the logic under
# test did not stop mattering, and a silently shrinking suite is how a
# migration loses coverage nobody notices. Each comes back when the pipeline
# consumes a Dossier and a dossier fixture exists to replace the case one.
pytestmark = pytest.mark.skip(reason="fixture removed with the case corpus — migration Phase 2/3")

from agents.drift import DriftAgent
from agents.kya import KYAAgent
from agents.log import LogAgent
from agents.mandate import MandateAgent
from data.loader import CASES_DIR
from ingestion.normalize import normalize_case
from registry.loader import load_kya_ruleset, load_mandate_ruleset


def test_kya_agent_returns_nothing_without_a_ruleset() -> None:
    case = normalize_case(CASES_DIR / "case-004-synthetic-identity.json")
    assert KYAAgent().run(case, None) == []


def test_kya_agent_catches_untrusted_issuer_given_the_ruleset() -> None:
    case = normalize_case(CASES_DIR / "case-004-synthetic-identity.json")
    findings = KYAAgent().run(case, load_kya_ruleset())
    assert any(f.type == "issuer_not_in_trust_registry" for f in findings)
    assert all(f.agent == "kya" for f in findings)


def test_mandate_agent_returns_nothing_without_a_ruleset() -> None:
    case = normalize_case(CASES_DIR / "case-003-broken-chain.json")
    assert MandateAgent().run(case, None) == []


def test_mandate_agent_catches_broken_chain_given_the_ruleset() -> None:
    case = normalize_case(CASES_DIR / "case-003-broken-chain.json")
    findings = MandateAgent().run(case, load_mandate_ruleset())
    assert any(f.type == "chain_hash_mismatch" for f in findings)
    assert all(f.agent == "mandate" for f in findings)


def test_clean_case_produces_no_findings_from_either_partial_agent() -> None:
    case = normalize_case(CASES_DIR / "case-001-compliant.json")
    assert KYAAgent().run(case, load_kya_ruleset()) == []
    assert MandateAgent().run(case, load_mandate_ruleset()) == []


def test_drift_is_still_a_true_stub() -> None:
    # Log stopped being a stub in Phase 7 (see tests/test_log_agent.py for
    # its real behavior) — Drift remains untouched, PLAN item 8.
    case = normalize_case(CASES_DIR / "case-006-drift.json")
    assert DriftAgent().run(case, None) == []
    # even with a ruleset argument (contract uniformity only — no ruleset
    # file exists for this domain)
    assert DriftAgent().run(case, load_kya_ruleset()) == []


def test_every_agent_exposes_the_common_contract() -> None:
    for agent in (KYAAgent(), MandateAgent(), LogAgent(), DriftAgent()):
        assert isinstance(agent.name, str) and agent.name
        assert callable(agent.run)
