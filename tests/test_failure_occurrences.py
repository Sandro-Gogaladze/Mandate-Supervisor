"""Stable failure vocabulary and the assessment -> occurrence projection."""
from __future__ import annotations

from agents.assess import project_failure_occurrences
from agents.kya import KYAAgent
from agents.mandate import MandateAgent
from registry.loader import (
    load_all_rulesets,
    load_failure_catalogue,
    load_kya_ruleset,
    load_mandate_ruleset,
)
from schemas import Assessment


def test_the_catalogue_is_contiguous_from_f1() -> None:
    """Ids run from F1 upwards with no gaps, no duplicates and no reordering,
    so a failure id is stable for the life of the catalogue and a new harm can
    only ever be appended. The count is data — asserting it here would make
    adding a harm a code change, which is the thing rules-as-data avoids."""
    catalogue = load_failure_catalogue()
    ids = [f.failure_id for f in catalogue.failures]
    assert ids == [f"F{i}" for i in range(1, len(ids) + 1)]
    assert len(set(ids)) == len(ids)
    # An id keeps its meaning for life: appending a harm must never renumber
    # an existing one, so both ends of the original catalogue are pinned.
    by_id = {f.failure_id: f.name for f in catalogue.failures}
    assert by_id["F1"] == "The organisation that issued the credential was never approved"
    assert by_id["F73"] == "A control fired, held, and the breach happened anyway"


def test_every_declared_f_mapping_resolves_to_the_catalogue() -> None:
    known = {f.failure_id for f in load_failure_catalogue().failures}
    declared = {
        failure
        for ruleset in load_all_rulesets().values()
        for rule in ruleset.rules
        for failure in rule.failures
        if failure.startswith("F")
    }
    assert declared <= known


def test_occurrence_names_exact_failure_and_affected_runs(kst) -> None:
    ruleset = load_mandate_ruleset()
    assessments = MandateAgent().assess(MandateAgent().run(kst, ruleset), ruleset, kst)
    occurrences = project_failure_occurrences(
        assessments, [ruleset], load_failure_catalogue()
    )
    caps = [o for o in occurrences if o.failure_id == "F42"]
    assert {o.failure_name for o in caps} == {"The order is bigger than the person allowed"}
    assert {o.rule_id for o in caps} == {"MND-CAP-01"}
    assert {o.ruleset_version for o in caps} == {ruleset.version}
    assert {(o.status, tuple(o.run_refs)) for o in caps} == {
        ("contained", ("RUN-2026-0722-0030",)),
        ("detected", ("RUN-2026-0811-0043",)),
    }
    assert {fact_id for o in caps for fact_id in o.fact_ids} == {
        f"{kst.dossier.dossier_id}:MND-CAP-01:{run_id}"
        for o in caps for run_id in o.run_refs
    }


def test_dossier_level_kya_failure_keeps_fact_and_assessment_links(kst) -> None:
    ruleset = load_kya_ruleset()
    facts = KYAAgent().run(kst, ruleset)
    assessments = KYAAgent().assess(facts, ruleset, kst)
    occurrences = project_failure_occurrences(
        assessments, [ruleset], load_failure_catalogue()
    )
    overlap = next(o for o in occurrences if o.failure_id == "F21")
    assert overlap.failure_name == "Two credentials for the same agent are valid at once"
    assert overlap.scope == "case"
    assert overlap.run_refs == []
    assert overlap.assessment_id in overlap.occurrence_id
    assert overlap.fact_ids


def test_kya_bundle_exposes_rules_results_attention_and_run_identity(kst) -> None:
    from agents.kya_reasoning import structured_view

    ruleset = load_kya_ruleset()
    facts = KYAAgent().run(kst, ruleset)
    bundle = structured_view(kst, facts, ruleset)
    assert bundle["bundle_type"] == "kya_evidence_bundle"
    assert bundle["review_scope"]["kind"] == "whole_dossier"
    assert len(bundle["review_scope"]["run_refs"]) == len(kst.runs)
    assert len(bundle["rule_inventory"]) == len(ruleset.rules)
    assert {r["rule_id"] for r in bundle["rule_results"]} == {
        f.rule_id for f in facts if f.rule_id and f.kind != "measurement"
    }
    assert all(f["kind"] != "satisfied" for f in bundle["attention_facts"])
    assert any(f["kind"] == "breach" for f in bundle["attention_facts"])
    assert len(bundle["run_identity_evidence"]) == len(kst.runs)
    assert bundle["agent_registry_record"]["agent_id"] == kst.dossier.agent_id


def test_systemic_portfolio_assessments_become_ruleless_failure_occurrences(kst, hal) -> None:
    from agents.systemic import SystemicAgent

    agent = SystemicAgent()
    facts = agent.run(kst, portfolio=[kst, hal])
    assessments = agent.assess(facts, None, kst)
    occurrences = project_failure_occurrences(assessments, [], load_failure_catalogue())
    assert {o.failure_id for o in occurrences} <= {"F57", "F67", "F69"}
    assert occurrences
    assert all(o.scope == "portfolio" and o.rule_id is None for o in occurrences)
    assert all(o.case_refs and o.fact_ids for o in occurrences)
    attack = [o for o in occurrences if o.failure_id == "F69"]
    assert all(o.run_refs for o in attack)
    assert all(set(o.run_refs_by_case) == set(o.case_refs) for o in attack)


def test_judged_multi_failure_rule_projects_only_the_selected_failure() -> None:
    ruleset = load_all_rulesets()["injection"]
    assessment = Assessment(
        assessment_id="CASE:injection:objective", case_id="CASE", scope="run",
        agent="injection", rule_id="INJ-ACT-01", ruleset_version=ruleset.version,
        failure_ids=["F35"], fact_ids=["FACT"], run_refs=["RUN-1", "RUN-2"],
        verdict="breach", severity_floor=0.7, severity_assessed=0.7,
        narrative="The objective stayed redirected on two runs.",
    )
    occurrences = project_failure_occurrences([assessment], [ruleset], load_failure_catalogue())
    assert [(o.failure_id, o.scope, o.run_refs) for o in occurrences] == [
        ("F35", "run_set", ["RUN-1", "RUN-2"])
    ]


def test_broad_judgments_do_not_claim_precise_failures_already_owned_by_specific_rules() -> None:
    books = load_all_rulesets()
    by_id = {r.rule_id: r for b in books.values() for r in b.rules}
    # A BROAD judgment reconciles or re-reads what specific rules already
    # decide, so it must claim no failure of its own: one event named twice is
    # scored twice. PRV-CRD-01 is not broad — card-versus-credential is checked
    # by no other rule in any book — so it carries its own harm.
    assert by_id["CPT-IDN-01"].failures == []
    assert by_id["PRV-REC-01"].failures == []
    assert by_id["PRV-CRD-01"].failures == ["F88"]
    assert by_id["CPT-REG-01"].failures == ["F51"]
    assert by_id["CPT-SUB-01"].failures == ["F52"]
    assert by_id["CPT-BEN-01"].failures == ["F53"]
    assert by_id["KYA-TEC-06"].failures == ["F33"]
    assert by_id["KYA-TEC-05"].failures == ["F36"]
    assert by_id["KYA-TEC-02"].failures == ["F37"]
    assert by_id["INJ-LST-01"].failures == []
    assert by_id["INJ-PRM-01"].failures == []
    assert by_id["INJ-RET-01"].failures == []
    assert by_id["INJ-TLS-01"].failures == []
    assert by_id["INJ-ACT-01"].failures == ["F32", "F35"]
