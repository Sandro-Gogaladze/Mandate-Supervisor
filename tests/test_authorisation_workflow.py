"""Regression gates for the dossier workflow added to the existing console."""
import io
import json
import sqlite3
import zipfile

import httpx
import pytest
from fastapi import FastAPI

from agents.assess import current
from agents.base import scoped
from agents.catalog import AGENTS, PEERS
from agents.mandate import MandateAgent
from api.dossiers import create_router
from data.dossier_loader import load_for_pipeline
from ledger.projection import project_case
from ledger.seed import seed_corpus, submit_dossier, latest_submission
from pipeline.authorisation import POLICY_PATH, recommend
from pipeline.graph import build_triage_graph, build_investigation_graph, build_drafting_graph, run_triage
from pipeline.map import supervision_map
from registry.loader import load_mandate_ruleset
from schemas import Assessment, Fact
from tests.corpus import HAL, KST, seed
from tests.fakes import make_graph_fake
from tests.test_uploads import _zip_of


def api_client(store):
    app = FastAPI()
    app.include_router(create_router(store, model=make_graph_fake()))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')


def test_map_is_the_real_graph_with_the_control_join(store):
    graphs = dict(triage=build_triage_graph(store=store), investigation=build_investigation_graph(store=store),
                  drafting=build_drafting_graph(store=store))
    surface = supervision_map(graphs)
    assert set(AGENTS) <= {n['id'] for n in surface['nodes']}
    assert {n['id'] for n in surface['nodes'] if n['role'] == 'peer'} == set(PEERS)
    edges = {(e['source'], e['target']) for e in surface['edges']}
    assert all((p, 'control_assurance') in edges for p in PEERS)
    assert ('control_assurance', 'findings') in edges
    assert ('synthesizer', 'orchestrator') in edges
    assert ('grounding_check', 'draft_report') in edges


async def test_floor_and_explicit_worker_completion_use_existing_agui_custom_stream(store):
    cid = seed(store, HAL)
    graph = build_triage_graph(store=store)
    phases = []
    async for event in graph.astream_events({'case_id': cid, 'messages': [], 'deterministic_only': True}, version='v2'):
        if event['event'] == 'on_custom_event' and event['name'] == 'specialist_progress':
            data = event['data']
            phases.append((data['agent'], data['status']))
            # counts and a sequence range travel; the facts themselves stay on the ledger
            assert data['fact_counts']['total'] > 0 and 'facts' not in data
            assert data['fact_seq_range'] and data['fact_seq_range'][0] <= data['fact_seq_range'][1]
            assert data['events'] and all(e['run_id'] == data['run_id'] for e in data['events'])
            assert not any(e['event_type'] == 'fact_recorded' for e in data['events'])
    for peer in PEERS:
        assert phases.index((peer, 'reasoning')) < phases.index((peer, 'complete'))
    assert phases[-1] == ('control_assurance', 'complete')
    assert store.events_for(cid)[-1].event_type == 'run_completed'
    assert not store.verify()


def test_focused_mandate_review_keeps_prior_draw_arithmetic_but_not_other_model_context():
    dossier = load_for_pipeline(KST)
    agent, rules = MandateAgent(), load_mandate_ruleset()
    facts = agent.run(dossier, rules)
    breach = next(f for f in facts if f.rule_id == 'MND-USE-01' and f.kind == 'breach')
    selected = scoped(dossier, [breach.run_ref])
    assert len(selected.runs) == 1 and selected.related_runs
    assert all(t.run_ref == breach.run_ref for t in selected.transaction_history)
    expected = {f.rule_id: f for f in facts if f.run_ref == breach.run_ref}
    for fact in agent.run(selected, rules):
        if fact.rule_id in ('MND-USE-01', 'MND-CAP-05'):
            assert fact.kind == expected[fact.rule_id].kind
            assert fact.values == expected[fact.rule_id].values
    assert 'related_runs' not in selected.model_dump()
    assert 'related_transactions' not in selected.model_dump()


def assessment(id='a', runs=None, **kw):
    return Assessment(assessment_id=id, case_id='case', agent='mandate', rule_id='MND-CAP-01',
                      fact_ids=['fact'], run_refs=runs or [], scope='run' if runs else 'case', narrative='A measured cap exceedance.',
                      verdict='breach', severity_floor=.5, severity_assessed=.5, **kw)


def test_focused_reassessment_only_replaces_the_runs_reconsidered():
    old = assessment(runs=['one', 'two'])
    new = assessment('b', ['one'], round=2, review_run_refs=['one'], supersedes='a')
    remaining = current([old, new])
    assert {(a.assessment_id, tuple(a.run_refs)) for a in remaining} == {('a', ('two',)), ('b', ('one',))}


def policy_fixture():
    dossier = load_for_pipeline(HAL)
    facts = [Fact(fact_id=f'fact-{r.run_id}', case_id=dossier.dossier.dossier_id, domain='mandate',
                  rule_id='MND-CAP-01', run_ref=r.run_id, kind='satisfied', statement='Within cap.') for r in dossier.runs]
    policy = json.loads(POLICY_PATH.read_text())
    policy.update(minimum_target_runs=0, minimum_rule_coverage=0, refusal_weight_per_run=100)
    return dossier, facts, policy


def test_missing_evidence_cannot_turn_into_a_clean_run_and_digest_pins_content():
    dossier, facts, policy = policy_fixture()
    first = recommend(dossier, facts, [], policy=policy)
    facts[0] = facts[0].model_copy(update=dict(kind='absent', absent_reason='missing_block', missing='cart'))
    changed = recommend(dossier, facts, [], policy=policy)
    assert changed.runs[0]['verdict'] == 'unresolved'
    assert changed.clean_runs == first.clean_runs - 1
    assert changed.disposition == 'incomplete-submission'
    assert changed.recommendation_digest != first.recommendation_digest
    portfolio = recommend(dossier, facts, [], policy=policy, portfolio_findings=[{'finding_id': 'portfolio-new'}])
    assert portfolio.recommendation_digest != changed.recommendation_digest


def test_same_event_groups_are_order_independent_and_keep_strongest_weight():
    dossier, facts, policy = policy_fixture()
    rid = dossier.runs[0].run_id
    a = assessment('a', [rid])
    b = assessment('b', [rid]).model_copy(update={'agent': 'counterparty', 'rule_id': 'CPT-PAY-01', 'severity_assessed': .8})
    c = assessment('c', [rid]).model_copy(update={'agent': 'log', 'rule_id': 'LOG-CON-01'})
    links = [{'relationship': 'same_event', 'finding_ids': ['a', 'b']}, {'relationship': 'same_event', 'finding_ids': ['b', 'c']}]
    x = recommend(dossier, facts, [a,b,c], policy=policy, correlations=links)
    y = recommend(dossier, facts, [c,b,a], policy=policy, correlations=list(reversed(links)))
    assert x.weight_per_run == y.weight_per_run
    assert {f['assessment_id']: f['dedup_factor'] for f in x.factors} == {'a': .25, 'b': 1, 'c': .25}


def test_run_artifacts_are_independently_verified(store):
    cid = seed(store, HAL)
    event = store.events_for(cid)[0]
    assert 'runs' not in event.payload and len(event.payload['run_artifacts']) == 20
    assert len(latest_submission(store, cid)['runs']) == 20
    digest = next(iter(event.payload['run_artifacts'].values()))
    with sqlite3.connect(store.path) as conn:
        conn.execute('DROP TRIGGER artifacts_no_delete')
        conn.execute('DELETE FROM artifacts WHERE digest=?', (digest,))
    assert any('Missing run artifact' in problem for problem in store.verify())


async def test_upload_alias_has_same_institution_authentication(store, tmp_path, monkeypatch):
    from data import uploads
    monkeypatch.setattr(uploads, 'UPLOADS_DIR', tmp_path / 'uploads')
    monkeypatch.setenv('MANDATE_INSTITUTION_TOKENS', json.dumps({'test-token': 'INST-001', 'wrong-token': 'INST-999'}))
    archive = _zip_of(HAL)
    async with api_client(store) as client:
        for path in ('/dossiers', '/cases/upload'):
            assert (await client.post(path, files={'file': ('dossier.zip', archive)})).status_code == 401
        mismatch = await client.post('/dossiers', files={'file': ('dossier.zip', archive)}, headers={'Authorization': 'Bearer wrong-token'})
        assert mismatch.status_code == 422 and not store.all_case_ids()
        accepted = await client.post('/dossiers', files={'file': ('dossier.zip', archive)}, headers={'Authorization': 'Bearer test-token'})
        assert accepted.status_code == 200
        assert len((await client.get(f"/dossiers/{accepted.json()['dossier_id']}/runs")).json()) == 20


async def test_zip_export_replays_the_signed_submission_and_decision_requires_current_basis(store, tmp_path):
    cid = seed(store, HAL)
    await run_triage(cid, store=store, deterministic_only=True)
    async with api_client(store) as client:
        details = (await client.get(f'/dossiers/{cid}')).json()
        report = details['recommendation']
        decision = {'reviewer': 'Test supervisor', 'disposition': 'refuse', 'rationale': 'Test-only decision based on the filed evidence.', 'recommendation_digest': 'stale'}
        assert (await client.post(f'/dossiers/{cid}/decision', json=decision)).status_code == 409
        decision['recommendation_digest'] = report['recommendation_digest']
        assert (await client.post(f'/dossiers/{cid}/decision', json=decision)).status_code == 200
        decision['disposition'] = 'authorise'
        assert (await client.post(f'/dossiers/{cid}/decision', json=decision)).status_code == 409
        export = await client.get(f'/dossiers/{cid}/export')
        with zipfile.ZipFile(io.BytesIO(export.content)) as archive:
            archive.extractall(tmp_path / 'export')
        restored = load_for_pipeline(tmp_path / 'export')
        from ingestion.normalize import normalize_dossier
        assert not normalize_dossier(restored).integrity.signature_failures
        assert len(restored.runs) == 20
        rows = [json.loads(line) for line in (tmp_path / 'export/review/ledger.jsonl').read_text().splitlines()]
        from ledger.events import LedgerEvent
        assert len(project_case([LedgerEvent.model_validate(row) for row in rows]).assessments) == len(project_case(store.events_for(cid)).assessments)


async def test_portfolio_is_a_persisted_run_kind(store):
    seed_corpus(store)
    async with api_client(store) as client:
        result = await client.post('/portfolio/sweep')
        assert result.status_code == 200
        assert {f['failure'] for f in result.json()['findings']} == {'F57', 'F67', 'F69'}
        assert (await client.get('/portfolio')).json()['sweep_id'] == result.json()['sweep_id']
    for cid in store.all_case_ids():
        run = project_case(store.events_for(cid)).runs[-1]
        assert run.kind == 'portfolio' and run.completed_at
    assert not store.verify()
