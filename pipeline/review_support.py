"""Explicit unjudged results and reference validation at the agent boundary."""
from agents.base import SpecialistReview
from schemas import Assessment


def version_review_facts(review, state):
    """Preserve immutable results when the reviewed scope or policy changes."""
    previous = {f.fact_id.split('@')[0]: f for f in state.get('facts', [])}
    aliases = {}
    for fact in review.facts:
        old = previous.get(fact.fact_id.split('@')[0])
        if old is None:
            continue
        same = fact.model_dump(exclude={'fact_id'}) == old.model_dump(exclude={'fact_id'})
        new_id = old.fact_id if same else fact.fact_id.split('@')[0] + '@' + state['run_id']
        aliases[fact.fact_id] = new_id
        fact.fact_id = new_id
    for a in review.assessments:
        a.fact_ids = [aliases.get(fid, fid) for fid in a.fact_ids]
    return review


def clear_reconsidered_rules(review, state, agent, ruleset):
    """A newly satisfied floor must retire its earlier breach explicitly."""
    if not ruleset:
        return
    previous = {a.rule_id for a in state.get('assessments', []) if a.agent == agent}
    assessed = {a.rule_id for a in review.assessments}
    for rule in ruleset.rules:
        facts = [f for f in review.facts if f.rule_id == rule.rule_id]
        if rule.rule_id not in previous or rule.rule_id in assessed or not facts:
            continue
        if any(f.kind != 'satisfied' and not (f.kind == 'absent' and f.absent_reason == 'out_of_scope') for f in facts):
            continue
        refs = sorted({f.run_ref for f in facts if f.run_ref})
        review.assessments.append(Assessment(
            assessment_id=f"{state['case_id']}:{agent}:{rule.rule_id}:cleared:r{state['review_round']}",
            case_id=state['case_id'], agent=agent, round=state['review_round'],
            scope='run' if refs else 'case', run_refs=refs, rule_id=rule.rule_id,
            ruleset_version=ruleset.version, fact_ids=[f.fact_id for f in facts], verdict='clear',
            narrative='The reconsidered rule is satisfied or inapplicable on the reviewed evidence.'))


def unjudged_review(agent, dossier, ruleset, facts, round):
    assessments = agent.assess(facts, ruleset, dossier, round=round)
    for rule in ruleset.rules if ruleset else []:
        if rule.status != "active" or rule.evaluation != "judged":
            continue
        refs = [f.fact_id for f in facts if f.rule_id == rule.rule_id]
        assessments.append(Assessment(
            assessment_id=f"{dossier.dossier.dossier_id}:{agent.name}:{rule.rule_id}:unjudged:r{round}",
            case_id=dossier.dossier.dossier_id, agent=agent.name, rule_id=rule.rule_id,
            ruleset_version=ruleset.version, round=round, fact_ids=refs,
            verdict="inconclusive", narrative="Model judgment has not completed. Mechanical checks alone do not establish this rule."))
    return SpecialistReview(facts=facts, assessments=assessments)


def validate_review(review, dossier, ruleset):
    facts = {f.fact_id: f for f in review.facts}
    runs = {r.run_id for r in dossier.runs}
    for a in review.assessments:
        problems = []
        if set(a.fact_ids) - facts.keys():
            problems.append("unresolved fact citation")
        if set(a.run_refs) - runs:
            problems.append("run outside the reviewed evidence")
        if a.verdict in ("breach", "clear") and not a.fact_ids:
            problems.append("no fact citation")
        if problems:
            a.verdict = "inconclusive"
            a.narrative = "Reference validation failed: " + ", ".join(problems) + ". Original claim: " + a.narrative
    return review
