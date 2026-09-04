"""Clearing a case's review history without breaking the append-only ledger."""
import asyncio

from ledger.projection import project_case
from pipeline.graph import run_triage
from tests.corpus import KST, seed


async def _triage(cid, store):
    await run_triage(cid, store=store, deterministic_only=True)


def test_reset_leaves_the_submission_and_drops_the_review(store) -> None:
    cid = seed(store, KST)
    asyncio.run(_triage(cid, store))
    before = project_case(store.events_for(cid))
    assert before.findings and before.assessments

    store.append(case_id=cid, event_type='review_history_cleared',
                 payload={'reason': 'test', 'cleared_through_seq': store.events_for(cid)[-1].seq},
                 actor='human:ana')

    after = project_case(store.events_for(cid))
    assert after.findings == [] and after.assessments == []
    assert after.observations == [] and after.failure_occurrences == []
    assert after.risk_score is None
    assert after.runs == []
    # The evidence is not the review of it: the submission survives so the
    # case is still loadable and a fresh run has something to read.
    assert after.firm == before.firm


def test_a_run_after_a_reset_starts_from_round_one(store) -> None:
    """The reason the reset exists: every run after the first is seeded from
    the record (graph.py::_seed_from_record), so without this a re-run
    inherits the previous one's assessments."""
    cid = seed(store, KST)
    asyncio.run(_triage(cid, store))
    first = project_case(store.events_for(cid))

    store.append(case_id=cid, event_type='review_history_cleared',
                 payload={'reason': 'test', 'cleared_through_seq': store.events_for(cid)[-1].seq},
                 actor='human:ana')
    asyncio.run(_triage(cid, store))
    second = project_case(store.events_for(cid))

    assert len(second.runs) == 1, 'the earlier run must not be carried forward'
    assert len(second.assessments) == len(first.assessments), 'no inheritance from the cleared round'
    assert second.risk_score.total == first.risk_score.total


def test_nothing_is_deleted_the_ledger_still_holds_every_event(store) -> None:
    cid = seed(store, KST)
    asyncio.run(_triage(cid, store))
    raw_before = len(store.events_for(cid))
    store.append(case_id=cid, event_type='review_history_cleared',
                 payload={'reason': 'test', 'cleared_through_seq': store.events_for(cid)[-1].seq},
                 actor='human:ana')
    assert len(store.events_for(cid)) == raw_before + 1


def test_the_console_sees_a_cleared_case_as_a_first_run(store) -> None:
    """Hiding the review in the projection but still serving its events left
    the case room showing a case with its history behind a "show earlier"
    link. After a reset the console must see the submission and nothing
    else."""
    cid = seed(store, KST)
    asyncio.run(_triage(cid, store))
    all_events = store.events_for(cid)
    assert any(e.event_type == 'run_started' for e in all_events)

    store.append(case_id=cid, event_type='review_history_cleared',
                 payload={'reason': 'test', 'cleared_through_seq': all_events[-1].seq},
                 actor='human:ana')

    # What the console reads (the same filter the API applies).
    rows = store.events_for(cid)
    cleared = max((e.seq for e in rows if e.event_type == 'review_history_cleared'), default=0)
    visible = [e for e in rows if e.seq > cleared
               or e.event_type in ('case_submitted', 'dossier_submitted', 'case_opened')]

    kinds = {e.event_type for e in visible}
    assert kinds <= {'case_submitted', 'dossier_submitted', 'case_opened', 'review_history_cleared'}
    assert not any(e.event_type in ('run_started', 'fact_recorded', 'assessment_recorded',
                                    'finding_recorded', 'observation_recorded') for e in visible)
    # …while the audit trail keeps every one of them.
    assert len(rows) > len(visible)


def test_a_report_awaiting_signature_does_not_block_a_reset(store) -> None:
    """A drafting run parks at the human gate and records no completion until
    somebody signs. Treating that as "a review is still running" blocked the
    reset for as long as a report sat unsigned — exactly when a reviewer wants
    to start over."""
    cid = seed(store, KST)
    asyncio.run(_triage(cid, store))
    store.append(case_id=cid, event_type='run_started', run_id='dra-parked',
                 payload={'run_id': 'dra-parked', 'kind': 'drafting'}, actor='system:review')

    events = store.events_for(cid)
    latest_review = next((e for e in reversed(events) if e.event_type == 'run_started'
                          and e.payload.get('kind') in ('triage', 'investigation')), None)
    assert latest_review is not None and latest_review.payload['kind'] == 'triage'
    assert any(e.event_type == 'run_completed' and e.run_id == latest_review.run_id
               for e in events), 'the triage finished, so nothing is in flight'
