"""pipeline/state.py's dedup-aware reducers — born from a live bug: a
LangGraph node retry (confirmed via a raw /agent trace showing the same
node's STARTED/FINISHED events repeat) re-computed a specialist's
deterministic findings from scratch, and plain `operator.add` concatenated
the retry's output onto the first attempt's, producing two `Finding`s with
an identical `finding_id` — which then broke React's list rendering
(duplicate keys) on the frontend."""
from __future__ import annotations

from pipeline.state import _add_findings, _add_observations
from schemas import Finding, Observation


def _finding(finding_id: str) -> Finding:
    return Finding(
        finding_id=finding_id,
        case_id="CASE-TEST",
        agent="kya",
        type="some_check",
        summary="summary",
    )


def test_add_findings_concatenates_new_ids():
    existing = [_finding("CASE-TEST-FND-001")]
    merged = _add_findings(existing, [_finding("CASE-TEST-FND-002")])
    assert [f.finding_id for f in merged] == ["CASE-TEST-FND-001", "CASE-TEST-FND-002"]


def test_add_findings_drops_retry_duplicates():
    # Simulates exactly the live failure: a node retried from scratch
    # recomputes findings with the same deterministic ids.
    existing = [_finding("CASE-TEST-FND-001"), _finding("CASE-TEST-FND-002")]
    retried = [_finding("CASE-TEST-FND-001"), _finding("CASE-TEST-FND-002")]
    merged = _add_findings(existing, retried)
    assert [f.finding_id for f in merged] == ["CASE-TEST-FND-001", "CASE-TEST-FND-002"]


def test_add_findings_keeps_new_ids_alongside_a_partial_retry():
    existing = [_finding("CASE-TEST-FND-001")]
    new_batch = [_finding("CASE-TEST-FND-001"), _finding("CASE-TEST-FND-002")]
    merged = _add_findings(existing, new_batch)
    assert [f.finding_id for f in merged] == ["CASE-TEST-FND-001", "CASE-TEST-FND-002"]


def _observation(note: str) -> Observation:
    return Observation(case_id="CASE-TEST", agent="log", note=note, cited_evidence="evidence")


def test_add_observations_concatenates_distinct_notes():
    existing = [_observation("first")]
    merged = _add_observations(existing, [_observation("second")])
    assert [o.note for o in merged] == ["first", "second"]


def test_add_observations_drops_exact_duplicates():
    # Observation has no id field of its own — identity is the full tuple
    # of fields, same shape a retried node would reproduce exactly.
    existing = [_observation("same note")]
    merged = _add_observations(existing, [_observation("same note")])
    assert len(merged) == 1
