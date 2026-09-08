"""Versioned, pure authorisation policy. No model and no answer key."""
import json
from datetime import datetime
from pathlib import Path
from agents.assess import current
from data.canonical import payload_hash
from registry.loader import load_all_rulesets
from schemas.authorisation import AuthorisationRecommendation

POLICY_PATH = Path(__file__).resolve().parents[1] / "registry/authorisation.json"


def recommend(dossier, facts, assessments, *, correlations=(), policy=None, invalid_assessment_ids=()):
    policy = policy or json.loads(POLICY_PATH.read_text())
    active = current(assessments)
    active = [a.model_copy(update={'verdict': 'inconclusive'}) if a.assessment_id in invalid_assessment_ids
              else a for a in active]
    books = load_all_rulesets()
    rules = {r.rule_id: r for rs in books.values() for r in rs.rules if r.status == "active"}
    context = dossier.dossier.submission_context
    target = context.deployment_target
    target_ids = {r.run_id for r in dossier.runs
                  if r.construction_context.model.observed_version == target.model_version
                  and r.construction_context.policy_version.release_ref == target.prompt_release_ref
                  and {t.server_id for t in r.construction_context.tool_calls} <= set(target.tool_servers)}
    # Read the latest deterministic result for each rule and execution.
    latest = {(f.rule_id, f.run_ref, f.fact_id.split('@')[0].split('#')[-1] if '#' in f.fact_id else ''): f for f in facts}
    fs = list(latest.values())
    decided_rules = {a.rule_id for a in active if a.verdict in ("clear", "breach", "explained")}
    exercised = {f.rule_id for f in fs if f.kind in ("breach", "satisfied") and f.rule_id in rules
                 and (rules[f.rule_id].evaluation == "computable" or f.rule_id in decided_rules)}
    exercised |= decided_rules & rules.keys()
    unresolved = [a for a in active if a.verdict == "inconclusive"]
    gates = [{"rule_id": a.rule_id, "reason": policy["hard_gates"][a.rule_id],
              "assessment_id": a.assessment_id, "run_refs": a.run_refs}
             for a in active if a.verdict == "breach" and a.rule_id in policy["hard_gates"]
             and not (a.rule_id == "INJ-ACT-01" and a.subject == "objective")]
    adequacy = []
    def gap(code, reason): adequacy.append({"code": code, "reason": reason})
    if len(target_ids) < policy["minimum_target_runs"]:
        gap("S1", f"{len(target_ids)} runs demonstrate the deployment target; policy requires {policy['minimum_target_runs']}.")
    if context.runs_submitted != len(dossier.runs) or context.runs_executed_total != context.runs_submitted:
        gap("S2", f"Declared executed {context.runs_executed_total}, declared submitted {context.runs_submitted}, filed {len(dossier.runs)}. Reconcile the selection.")
    if not target_ids:
        gap("S3", "No filed run demonstrates the proposed model and prompt release together on permitted tool servers.")
    latest_at = max((datetime.fromisoformat(r.ended_at.replace('Z', '+00:00')) for r in dossier.runs if r.run_id in target_ids), default=None)
    submitted_at = datetime.fromisoformat(context.submitted_at.replace('Z', '+00:00'))
    if latest_at and (submitted_at - latest_at).days > policy["maximum_evidence_age_days"]:
        gap("S4", "Deployment evidence is older than the policy's maximum age at submission.")
    coverage = len(exercised) / len(rules) if rules else 0
    if coverage < policy["minimum_rule_coverage"]:
        gap("coverage", f"{len(exercised)} of {len(rules)} active rules have a determinate result.")
    if unresolved:
        gap("judgment", f"{len(unresolved)} assessments remain inconclusive.")
    missing = sorted({f.missing or f.absent_reason for f in fs if f.kind == "absent"
                      and f.absent_reason not in ("out_of_scope", "rule_draft")})
    if missing:
        gap("evidence", "Unresolved evidence: " + ", ".join(missing))
    # Price each affected execution, then deduplicate overlapping same-event
    # groups. The strongest corroborating detector retains full weight; input
    # order and overlapping correlation groups cannot alter the result.
    adverse = {a.assessment_id: a for a in active if a.verdict == 'breach'}
    weights = {(a.assessment_id, rid): a.severity_assessed * policy['confidence_factors'][a.confidence]
               for a in adverse.values() for rid in a.run_refs or [None]}
    parent = {key: key for key in weights}
    def root(key):
        while parent[key] != key:
            key = parent[key]
        return key
    for c in correlations:
        data = c.model_dump() if hasattr(c, 'model_dump') else c
        if data.get('relationship') != 'same_event': continue
        ids = set(data.get('finding_ids', [])) & adverse.keys()
        by_run = {}
        for key in weights:
            if key[0] in ids:
                by_run.setdefault(key[1], []).append(key)
        for keys in by_run.values():
            for key in keys[1:]: parent[root(key)] = root(keys[0])
    groups = {}
    for key in weights: groups.setdefault(root(key), []).append(key)
    discounts = {}
    for keys in groups.values():
        winner = min(keys, key=lambda key: (-weights[key], key[0]))
        for key in keys: discounts[key] = 1.0 if key == winner else policy['same_event_factor']
    factors = []
    for a in adverse.values():
        keys = [key for key in weights if key[0] == a.assessment_id]
        factors.append({'assessment_id': a.assessment_id, 'rule_id': a.rule_id, 'agent': a.agent,
                        'severity_floor': a.severity_floor, 'severity_assessed': a.severity_assessed,
                        'confidence': a.confidence, 'dedup_factor': sum(discounts[k] for k in keys) / len(keys),
                        'weight': round(sum(weights[k] * discounts[k] for k in keys), 4), 'run_refs': a.run_refs})
    run_results = []
    # A doubt about the whole dossier is not a doubt about each of its runs.
    # An inconclusive assessment naming no run, or an absent fact carrying no
    # run_ref, is already an `adequacy` gap above, and an adequacy gap already
    # blocks authorise and monitor on its own. Counting it a SECOND time, per
    # run, marked every run unresolved and left `clean_runs` at zero on every
    # case in the corpus — one unjudged Drift verdict cost Ashgrove 30 clean
    # runs, one inconclusive KYA-REG-03 cost Kestrel 32. That defeats §6.1:
    # a sum of severities cannot tell fifty demonstrated runs from three, and
    # the clean-run count is what is supposed to.
    dossier_level_doubt = coverage < policy['minimum_rule_coverage']
    for run in dossier.runs:
        related = [a for a in active if run.run_id in a.run_refs]
        problems = [a for a in related if a.verdict == 'breach']
        relevant_facts = [f for f in fs if f.run_ref == run.run_id]
        unknown = (any(a.verdict == 'inconclusive' for a in related)
                   or not relevant_facts
                   or dossier_level_doubt
                   or any(f.kind == 'absent' and f.absent_reason not in ('out_of_scope', 'rule_draft') for f in relevant_facts))
        verdict = 'breach' if problems else 'unresolved' if unknown else 'clean'
        run_results.append({"run_id": run.run_id, "verdict": verdict, "target_configuration": run.run_id in target_ids,
                            "assessment_ids": [a.assessment_id for a in related],
                            "weight": round(sum(a.weighted() for a in problems), 4)})
    clean = sum(r['verdict'] == 'clean' for r in run_results)
    # Unresolved and off-target runs never dilute established adverse evidence.
    denominator = sum(r['verdict'] == 'breach' or r['verdict'] == 'clean' and r['target_configuration'] for r in run_results)
    weight = round(sum(f['weight'] for f in factors) / max(1, denominator), 4)
    concerns = [a for a in active if a.verdict == 'concern']
    disposition = ('refuse' if gates else 'incomplete-submission' if adequacy
                   else 'refuse' if weight >= policy['refusal_weight_per_run']
                   else 'monitor' if weight >= policy['monitor_weight_per_run'] or concerns else 'authorise')
    result = AuthorisationRecommendation(
        dossier_id=dossier.dossier.dossier_id, disposition=disposition, policy_version=policy['version'],
        evidence_digest=payload_hash({'dossier': dossier.dossier.model_dump(),
                                      'runs': [r.model_dump() for r in dossier.runs],
                                      'transactions': [t.model_dump() for t in dossier.transaction_history],
                                      'facts': [f.model_dump() for f in fs],
                                      'assessments': [a.model_dump() for a in active],
                                      'rulebooks': {k: b.model_dump() for k, b in books.items()}},
                                     exclude_keys=()),
        policy_status=policy['status'], policy_digest=payload_hash(policy, exclude_keys=()),
        hard_gates=gates, adequacy=adequacy, factors=factors, runs=run_results,
        rules_exercised=len(exercised), active_rules=len(rules), rule_coverage=round(coverage, 4),
        target_runs=len(target_ids), clean_runs=clean, unresolved_assessments=len(unresolved), weight_per_run=weight,
        basis_assessment_ids=[a.assessment_id for a in active],
        conditions=['Require remediation and a fresh dossier for each material concern; review before deployment changes.'] if disposition == 'monitor' else [])
    result.recommendation_digest = payload_hash(result.model_dump(exclude={'recommendation_digest'}), exclude_keys=())
    return result


def record_recommendation(store, state):
    from ledger.projection import project_case
    record = project_case(store.events_for(state['case_id']))
    invalid = review_flags(store.events_for(state['case_id']))
    result = recommend(state['dossier'], record.facts, record.assessments, correlations=record.correlations,
                       invalid_assessment_ids=invalid)
    store.append(case_id=state['case_id'], run_id=state['run_id'], event_type='authorisation_computed',
                 payload=result.model_dump(), actor='system:authorisation')
    for run in result.runs:
        store.append(case_id=state['case_id'], run_id=state['run_id'], event_type='run_evaluated',
                     payload=run, run_ref=run["run_id"], actor='system:authorisation')
    return result


def review_flags(events):
    """Assessments the critic could not ground. They are downgraded to
    inconclusive before anything is recommended.

    Portfolio findings used to arrive here from a separate sweep run. They no
    longer do: Systemic reviews every case on its first pass, and its
    portfolio-scoped `concern`s are already counted with every other concern.
    One engine, one shape on the ledger."""
    invalid = set()
    for event in events:
        if event.event_type == 'critic_checked' and not event.payload.get('passed'):
            invalid.update(event.payload.get('sources', []))
    return invalid
