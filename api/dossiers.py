"""Dossier-native API. The ledger remains the only review record."""
import asyncio
import io
import json
import os
import secrets
import uuid
import zipfile
from dataclasses import asdict
from datetime import datetime, timezone

# A specialist call is capped at 900 s (pipeline/graph.py), so a run that
# started longer ago than this and never completed is not running — it was
# abandoned, and a reset is how the case room recovers from that.
_ABANDONED_AFTER_S = 20 * 60
from fastapi import APIRouter, Header, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from agents.assess import current
from agents.catalog import AGENTS, PEERS
from agents.systemic import sweep
from data.uploads import DossierUploadError, save_uploaded_dossier
from ingestion.normalize import dossier_from_submission, normalize_dossier
from ledger.projection import project_case, visible_events
from ledger.seed import latest_submission, submit_dossier
from pipeline.authorisation import recommend, review_flags
from pipeline.graph import build_triage_graph, run_triage, run_investigation
from schemas.authorisation import AuthorisationDecision
from schemas.review_gate import ReviewerDirective


class ReviewRequest(BaseModel):
    deterministic_only: bool = False
    instruction: str = ""
    agents: list[str] = Field(default_factory=list)
    run_scope: list[str] = Field(default_factory=list)
    officer: str = "Supervision officer"


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=10000)
    officer: str = Field(min_length=2)


def create_router(store, *, model=None):
    router = APIRouter()
    locks = {}

    def lock(cid): return locks.setdefault(cid, asyncio.Lock())

    def loaded(cid):
        try: return dossier_from_submission(latest_submission(store, cid))
        except ValueError as exc: raise HTTPException(404, str(exc)) from exc

    def detail(cid):
        dossier = loaded(cid)
        events = store.events_for(cid)
        record = project_case(events)
        invalid, portfolio = review_flags(events)
        recommendation = recommend(dossier, record.facts, record.assessments, correlations=record.correlations,
                                   invalid_assessment_ids=invalid, portfolio_findings=portfolio) if record.facts else None
        return dict(dossier=dossier.dossier.model_dump(), firm=record.firm,
                    integrity=normalize_dossier(dossier).integrity.model_dump(),
                    assessments=[a.model_dump() for a in current(record.assessments)],
                    facts=[f.model_dump() for f in record.facts],
                    review_rounds=[r.model_dump(exclude={'facts', 'assessments', 'findings', 'prompts'}) for r in record.runs],
                    recommendation=recommendation.model_dump() if recommendation else None,
                    decisions=[e.payload for e in events if e.event_type == 'authorisation_decided'],
                    control_postures=[e.payload for e in events if e.event_type == 'control_posture_recorded'],
                    correlations=[c.model_dump() for c in record.correlations],
                    portfolio=[e.payload for e in events if e.event_type == 'portfolio_finding_recorded'],
                    failures=[e.payload for e in events if e.event_type == 'specialist_failed'],
                    last_seq=events[-1].seq)

    @router.get('/dossiers')
    async def dossiers():
        out = []
        for cid in store.all_case_ids():
            d = loaded(cid); record = project_case(store.events_for(cid))
            invalid, portfolio = review_flags(store.events_for(cid))
            recommendation = recommend(d, record.facts, record.assessments, correlations=record.correlations,
                                       invalid_assessment_ids=invalid, portfolio_findings=portfolio) if record.facts else None
            out.append(dict(dossier_id=cid, institution_id=d.dossier.institution_id,
                            agent_id=d.dossier.agent_id, operator_id=d.dossier.operator_id, firm=record.firm,
                            runs=len(d.runs), submitted_at=d.dossier.submission_context.submitted_at,
                            disposition=recommendation.disposition if recommendation else 'awaiting-review',
                            clean_runs=recommendation.clean_runs if recommendation else 0,
                            reviewed=bool(record.facts)))
        return out

    @router.get('/dossiers/{cid}')
    async def dossier_detail(cid: str): return detail(cid)

    @router.get('/dossiers/{cid}/runs')
    async def runs(cid: str):
        d = loaded(cid); report = detail(cid)['recommendation']
        results = {r['run_id']: r for r in report['runs']} if report else {}
        return [dict(run_id=r.run_id, started_at=r.started_at, request=r.intent_mandate.natural_language_intent,
                     merchant=r.cart.merchant.name if r.cart else None, amount=r.cart.cart_total if r.cart else None,
                     currency=r.cart.currency if r.cart else None, outcome=r.outcome,
                     review=results.get(r.run_id)) for r in d.runs]

    @router.get('/dossiers/{cid}/runs/{rid}')
    async def run_detail(cid: str, rid: str):
        d = loaded(cid)
        run = next((r for r in d.runs if r.run_id == rid), None)
        if not run: raise HTTPException(404, 'Execution run not found')
        return dict(run=run.model_dump(), transactions=[t.model_dump() for t in d.transaction_history if t.run_ref == rid])

    @router.get('/dossiers/{cid}/events')
    async def events(cid: str, after: int = 0, run_ref: str | None = None,
                     include_cleared: bool = False):
        """The case's events as the console reads them.

        A reset is honoured here, not just in the projection: after one, the
        console must show a case with no review on it — not a case with its
        review hidden behind a "show earlier" link. Rows are never deleted
        (the hash chain is global, so removing any event would break every
        event recorded after it, in every case), so `include_cleared=true`
        still returns the whole history for the timeline and the verifier.
        """
        loaded(cid)
        rows = store.events_for(cid)
        if not include_cleared:
            rows = visible_events(rows)
        return [e.model_dump() for e in rows if e.seq > after and (not run_ref or e.run_ref == run_ref)]

    @router.post('/cases/upload')
    @router.post('/dossiers')
    async def upload(file: UploadFile, authorization: str | None = Header(default=None)):
        tokens = json.loads(os.environ.get('MANDATE_INSTITUTION_TOKENS', '{}'))
        token = (authorization or '').removeprefix('Bearer ')
        institution = next((v for k, v in tokens.items() if secrets.compare_digest(k, token)), None)
        if not institution: raise HTTPException(401, 'A configured institution submission token is required.')
        content = await file.read(16 * 1024 * 1024 + 1)
        if len(content) > 16 * 1024 * 1024: raise HTTPException(413, 'Compressed dossier exceeds 16 MB.')
        try:
            d = save_uploaded_dossier(content, existing_ids=store.all_case_ids(), institution_id=institution)
            cid = submit_dossier(store, d, actor=f'human:institution:{institution}')
        except DossierUploadError as exc: raise HTTPException(422, str(exc)) from exc
        return {'dossier_id': cid, 'verified': True}

    @router.post('/dossiers/{cid}/review')
    async def review(cid: str, body: ReviewRequest):
        d = loaded(cid)
        if set(body.agents) - AGENTS.keys(): raise HTTPException(422, 'Unknown specialist')
        if set(body.run_scope) - {r.run_id for r in d.runs}: raise HTTPException(422, 'Unknown execution run')
        if body.run_scope and not body.agents: raise HTTPException(422, 'A focused review must name its specialists')
        if lock(cid).locked(): raise HTTPException(409, 'A review is already running')
        async def stream():
            async with lock(cid):
                after = store.events_for(cid)[-1].seq
                directive = ReviewerDirective(instructions=body.instruction or 'Re-examine the selected evidence.',
                                              target_agents=body.agents, run_scope=body.run_scope) if body.agents else None
                task = asyncio.create_task(run_triage(cid, store=store, model=model, directive=directive,
                                                     deterministic_only=body.deterministic_only))
                yield 'data: ' + json.dumps({'type': 'RUN_STARTED', 'threadId': cid, 'runId': f'view-{after}'}) + '\n\n'
                try:
                    while True:
                        for event in store.events_for(cid):
                            if event.seq <= after: continue
                            after = event.seq
                            yield 'data: ' + json.dumps({'type': 'CUSTOM', 'name': 'ledger_event', 'value': event.model_dump()}) + '\n\n'
                        if task.done(): break
                        await asyncio.sleep(0.15)
                    await task
                    yield 'data: ' + json.dumps({'type': 'RUN_FINISHED', 'threadId': cid, 'runId': f'view-{after}'}) + '\n\n'
                except asyncio.CancelledError:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                    raise
                except Exception as exc:
                    yield 'data: ' + json.dumps({'type': 'RUN_ERROR', 'message': str(exc)}) + '\n\n'
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    @router.post('/dossiers/{cid}/question')
    async def question(cid: str, body: QuestionRequest):
        loaded(cid)
        async with lock(cid):
            record, reply = await run_investigation(cid, body.question, officer=body.officer, model=model, store=store)
        return {'reply': reply, 'dossier_id': cid, 'answers': [a.model_dump() for a in record.answers]}

    @router.post('/dossiers/{cid}/reset')
    async def reset_review_history(cid: str, officer: str = 'officer'):
        """Set the review history aside so the next run starts from the
        submission alone.

        Every run after the first is seeded from the case record
        (pipeline/graph.py::_seed_from_record), so without this a second run
        inherits the first one's assessments and the score accumulates. This
        does not delete anything — the ledger's append-only triggers would
        refuse, and the audit trail is the point — it appends a marker the
        projection reads as "carry nothing recorded before here".
        """
        loaded(cid)
        async with lock(cid):
            events = store.events_for(cid)
            # Only a run that could still be WRITING blocks a reset. A drafting
            # run parks at the human gate and never records a completion until
            # somebody signs, so counting it as in-flight blocked the reset for
            # as long as a report sat unsigned — precisely when a reviewer wants
            # to start over.
            latest = next((e for e in reversed(events) if e.event_type == 'run_started'
                           and e.payload.get('kind') in ('triage', 'investigation')), None)
            unfinished = latest and not any(
                e.event_type == 'run_completed' and e.run_id == latest.run_id for e in events)
            # Only a run that could still be live blocks a reset. A run that
            # started an hour ago and never completed was abandoned — a browser
            # closed mid-stream, a server restarted — and wedging the case
            # forever would break the one action that recovers from it.
            if unfinished:
                age = (datetime.now(timezone.utc)
                       - datetime.fromisoformat(latest.recorded_at)).total_seconds()
                if age < _ABANDONED_AFTER_S:
                    raise HTTPException(409, 'A review is still running. Wait for it to finish.')
            store.append(case_id=cid, event_type='review_history_cleared',
                         payload={'reason': 'reviewer reset the case room',
                                  'cleared_through_seq': events[-1].seq},
                         actor=f'human:{officer}')
        return detail(cid)

    @router.post('/dossiers/{cid}/decision')
    async def decide(cid: str, decision: AuthorisationDecision):
        async with lock(cid):
            events = store.events_for(cid)
            latest_review = next((e for e in reversed(events) if e.event_type == 'run_started'
                                  and e.payload.get('kind') in ('triage', 'investigation')), None)
            if latest_review and not any(e.event_type == 'run_completed' and e.run_id == latest_review.run_id for e in events):
                raise HTTPException(409, 'The latest review is unfinished. Complete a review before signing.')
            report = detail(cid)['recommendation']
            if not report: raise HTTPException(409, 'Complete a review before recording a decision.')
            if report['recommendation_digest'] != decision.recommendation_digest:
                raise HTTPException(409, 'The evidence or policy changed. Review the current recommendation.')
            if decision.disposition in ('authorise', 'monitor') and (report['hard_gates'] or report['adequacy']):
                raise HTTPException(409, 'Resolve refusal gates and evidence gaps before authorisation.')
            if decision.disposition == 'monitor' and not decision.conditions:
                raise HTTPException(422, 'Authorisation with monitoring requires specific conditions.')
            payload = {**decision.model_dump(), 'decided_at': datetime.now(timezone.utc).isoformat(),
                       'policy_version': report['policy_version'], 'basis': report}
            event = store.append(case_id=cid, event_type='authorisation_decided', payload=payload,
                                 actor=f'human:{decision.reviewer}')
            if decision.disposition == 'monitor':
                store.append(case_id=cid, event_type='case_watched', payload={'decision_seq': event.seq}, actor=f'human:{decision.reviewer}')
            return payload

    @router.get('/portfolio')
    async def portfolio():
        completed = [e for e in store.all_events() if e.event_type == 'portfolio_sweep_completed']
        if not completed: return {'sweep_id': None, 'findings': []}
        return completed[-1].payload

    @router.post('/portfolio/sweep')
    async def portfolio_sweep():
        ds = [loaded(cid) for cid in store.all_case_ids()]
        if not ds: raise HTTPException(409, 'No submitted dossiers')
        sweep_id = 'portfolio-' + uuid.uuid4().hex[:12]
        findings = [asdict(f) for f in sweep(ds)] if len(ds) > 1 else []
        payload = {'sweep_id': sweep_id, 'dossiers': [d.dossier.dossier_id for d in ds],
                   'findings': findings, 'completed_at': datetime.now(timezone.utc).isoformat()}
        for d in ds:
            cid = d.dossier.dossier_id
            store.append(case_id=cid, run_id=sweep_id, event_type='run_started',
                         payload={'run_id': sweep_id, 'kind': 'portfolio', 'prompts': {}}, actor='agent:systemic')
            store.append(case_id=cid, run_id=sweep_id, event_type='portfolio_sweep_started', payload={'sweep_id': sweep_id}, actor='agent:systemic')
            for finding in findings:
                if cid in finding['subject_refs']:
                    store.append(case_id=cid, run_id=sweep_id, event_type='portfolio_finding_recorded', payload=finding, actor='agent:systemic')
            store.append(case_id=cid, run_id=sweep_id, event_type='portfolio_sweep_completed', payload=payload, actor='agent:systemic')
            store.append(case_id=cid, run_id=sweep_id, event_type='run_completed',
                         payload={'run_id': sweep_id, 'kind': 'portfolio'}, actor='agent:systemic')
        return payload

    @router.get('/dossiers/{cid}/export')
    async def export(cid: str):
        payload = latest_submission(store, cid); d = loaded(cid)
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('dossier.json', json.dumps(payload['dossier'], indent=2))
            archive.writestr('transactions.json', json.dumps({'transaction_history': payload['transaction_history']}))
            for ref in d.dossier.run_index:
                digest = payload.get('run_artifacts', {}).get(ref.run_id)
                if digest: content = store.artifact(digest)
                else: content = json.dumps(next(r for r in payload['runs'] if r['run_id'] == ref.run_id), indent=2).encode() + b'\n'
                archive.writestr(ref.file, content)
            for event in store.events_for(cid):
                basis = event.payload.get('review_basis', {})
                for digest in [*basis.get('rulebook_artifacts', {}).values(), *([basis['policy_artifact']] if basis.get('policy_artifact') else [])]:
                    name = 'review/artifacts/' + digest.removeprefix('sha256:') + '.json'
                    if name not in archive.namelist(): archive.writestr(name, store.artifact(digest))
            archive.writestr('review/ledger.jsonl', '\n'.join(store.export_jsonl(cid)))
            archive.writestr('review/decision.json', json.dumps(detail(cid)['recommendation'], indent=2))
        return Response(output.getvalue(), media_type='application/zip', headers={'Content-Disposition': f'attachment; filename="{cid}.zip"'})

    @router.get('/review-graph')
    async def review_graph():
        graph = build_triage_graph(store=store).get_graph()
        return {'nodes': [{'id': name, 'label': name.replace('_', ' ').title(),
                           'kind': 'peer' if name in PEERS else 'support'} for name in graph.nodes if not name.startswith('__')],
                'edges': [{'source': e.source, 'target': e.target, 'conditional': e.conditional} for e in graph.edges
                          if not e.source.startswith('__') and not e.target.startswith('__')]}

    @router.get('/rulebooks')
    async def rulebooks():
        from registry.loader import load_all_rulesets
        from pipeline.authorisation import POLICY_PATH
        return {'rulebooks': [rs.model_dump() for rs in load_all_rulesets().values()],
                'authorisation_policy': json.loads(POLICY_PATH.read_text()),
                'model_available': bool(model or os.environ.get('ANTHROPIC_API_KEY'))}

    return router
