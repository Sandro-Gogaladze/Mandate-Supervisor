"""Every specialist receives the same rule/fact envelope around its own data."""
from __future__ import annotations

import json

from agents.catalog import AGENTS, RULESET_LOADERS
from agents.context import canonical_context
from agents.control_assurance import peers_from_facts
from agents.skills import SPECIALIST_SKILLS_BY_AGENT
from ingestion.normalize import normalize_dossier
from registry.loader import load_failure_catalogue, load_all_rulesets


def _assert_contract(context: dict, *, agent: str, ruleset, facts) -> None:
    contract = context["evidence_contract"]
    assert contract["specialist"] == agent
    assert contract["review_scope"]["run_refs"]
    assert contract["failure_catalogue_version"] == load_failure_catalogue().version
    assert len(contract["rule_inventory"]) == len(ruleset.rules)
    assert contract["ruleset"]["version"] == ruleset.version
    assert {r["rule_id"] for r in contract["rule_results"]} == {
        f.rule_id for f in facts if f.rule_id
    }
    assert all(f["kind"] != "satisfied" for f in contract["attention_facts"])
    # Evaluation labels are never part of a production briefing.
    assert "ground_truth" not in json.dumps(context)


def test_every_model_specialist_has_common_contract_around_domain_evidence(kst) -> None:
    evidence = normalize_dossier(kst)
    for agent_name in (
        "mandate", "provenance", "injection", "counterparty", "consent", "log", "drift"
    ):
        agent = AGENTS[agent_name]()
        ruleset = RULESET_LOADERS[agent_name]()
        facts = agent.run(kst, ruleset, evidence=evidence)
        context = canonical_context(
            SPECIALIST_SKILLS_BY_AGENT[agent_name], kst,
            evidence=evidence, ruleset=ruleset, floor_facts=facts,
        )
        _assert_contract(context, agent=agent_name, ruleset=ruleset, facts=facts)
        if agent_name == "mandate":
            semantic = next(
                f for f in context["evidence_contract"]["attention_facts"]
                if f["rule_id"] == "MND-SEM-01" and f["kind"] == "measurement"
            )
            assert semantic["statement"].startswith("<<<UNTRUSTED_FACT_STATEMENT>>>")
            assert semantic["values"]["natural_language_intent"].startswith(
                "<<<UNTRUSTED_EVIDENCE_TEXT>>>"
            )
            assert semantic["values"]["line_items"][0]["description"].startswith(
                "<<<UNTRUSTED_EVIDENCE_TEXT>>>"
            )
        if agent_name == "consent":
            assert {r["run_id"] for r in context["consent_evidence_by_run"]} == {
                r.run_id for r in kst.runs
            }
            assert all("consent_ceremony" in r and "signed_cart" in r
                       for r in context["consent_evidence_by_run"])
        if agent_name == "provenance":
            assert {r["run_id"] for r in context["provenance_evidence_by_run"]} == {
                r.run_id for r in kst.runs
            }
        if agent_name in {"log", "drift"}:
            assert {t["transaction_id"] for t in context["transaction_index"]} == {
                t.transaction_id for t in kst.transaction_history
            }


def test_deterministic_specialists_record_the_inputs_their_checks_consumed(kst, hal) -> None:
    evidence = normalize_dossier(kst)
    books = load_all_rulesets()

    mandate = AGENTS["mandate"]()
    mandate_facts = mandate.run(kst, books["mandate"], evidence=evidence)
    control = AGENTS["control_assurance"]()
    control_rules = RULESET_LOADERS["control_assurance"]()
    peer_facts = mandate_facts
    control_facts = control.run(
        kst, control_rules, evidence=evidence,
        peers=peers_from_facts(peer_facts, books),
    )
    control_context = canonical_context(
        "control_assurance.review", kst, evidence=evidence, ruleset=control_rules,
        floor_facts=control_facts, peer_facts=peer_facts, peer_assessments=[],
    )
    _assert_contract(control_context, agent="control_assurance",
                     ruleset=control_rules, facts=control_facts)
    assert control_context["declared_controls"]
    assert control_context["control_executions"]
    assert control_context["peer_breach_facts"]
    assert control_context["peer_breach_assessments"] == []

    systemic = AGENTS["systemic"]()
    systemic_facts = systemic.run(kst, portfolio=[kst, hal])
    systemic_context = canonical_context(
        "systemic.review", kst, floor_facts=systemic_facts, portfolio=[kst, hal]
    )
    assert len(systemic_context["portfolio"]) == 2
    assert systemic_context["evidence_contract"]["ruleset"] is None

