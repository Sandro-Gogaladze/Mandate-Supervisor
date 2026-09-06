"""Guarantees for the portfolio sweep.

Every test here asserts something that CANNOT be established from one
submission. That is the tier's whole reason to exist, so the negative cases
matter as much as the positive ones: a sweep that reports the entire high
street because popular retailers are popular is worse than no sweep at all.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from agents.systemic import (  # noqa: E402
    model_monoculture,
    shared_attack_content,
    shared_counterparty_concentration,
    sweep,
)
from data.dossier_loader import list_dossiers, load  # noqa: E402


@pytest.fixture(scope="module")
def portfolio():
    return [load(p) for p in list_dossiers()]


def test_a_sweep_needs_a_portfolio(portfolio):
    """One dossier is not a population, and saying nothing would read as
    'nothing found' rather than 'not answerable'."""
    with pytest.raises(ValueError):
        sweep(portfolio[:1])


# --- F57 -------------------------------------------------------------------

def test_new_payee_taking_a_large_share_at_two_operators_is_found(portfolio):
    f = next(f for f in shared_counterparty_concentration(portfolio) if f.failure == "F57")
    assert f.details["counterparty_id"] == "MER-QVC-8801"
    assert len(f.subject_refs) == 2
    assert "beneficial_owner_unresolved" in f.details["watchlist_flags"]


def test_ordinary_popularity_is_not_reported(portfolio):
    """The retailers both agents buy from most are shared BY DEFINITION.

    If mere presence at two operators were enough, this rule would report
    Northsole, Voltic, Pagegrove and Lumen — and a sweep that flags the high
    street teaches a supervisor to ignore it.
    """
    flagged = {f.details["counterparty_id"] for f in shared_counterparty_concentration(portfolio)}
    assert not (flagged & {"MER-NOR-1120", "MER-VLT-7789", "MER-PGE-2201", "MER-LUM-6614"})


def test_recency_is_load_bearing_not_decorative(portfolio):
    """An incumbent that grew into a large share over years looks nothing like
    one that arrived last month. Widen the recency window to cover every
    merchant and the signal should still hold on its other two conditions."""
    wide = shared_counterparty_concentration(portfolio, recent_days=10_000)
    assert {f.details["counterparty_id"] for f in wide} >= {"MER-QVC-8801"}
    # ...but with recency demanded and nothing recent, nothing qualifies.
    assert shared_counterparty_concentration(portfolio, recent_days=0) == []


def test_share_threshold_is_a_dial(portfolio):
    assert shared_counterparty_concentration(portfolio, min_share=99.0) == []


# --- F67 -------------------------------------------------------------------

def test_monoculture_is_reported_as_emergent_not_as_operator_fault(portfolio):
    f = next(f for f in model_monoculture(portfolio) if f.failure == "F67")
    assert f.details["share_pct"] == 100.0
    # The wording matters: no operator did anything wrong, and a finding that
    # implies otherwise would be acted on against the wrong party.
    assert "No operator has done anything wrong" in f.summary


def test_monoculture_respects_its_dial(portfolio):
    assert model_monoculture(portfolio, max_share=101.0) == []


# --- F69 -------------------------------------------------------------------

def test_same_injected_payload_at_two_operators_is_one_campaign(portfolio):
    f = next(f for f in shared_attack_content(portfolio) if f.failure == "F69")
    assert len(f.subject_refs) == 2


def test_result_digest_hashes_content_not_the_run(portfolio):
    """The correlation F69 rests on.

    A digest derived from the run id is unique per run whatever came back,
    which silently destroys the only thing the field is for. Identical content
    must produce an identical digest across operators.
    """
    digests = {}
    for d in portfolio:
        for r in d.runs:
            for tc in r.construction_context.tool_calls:
                if tc.result_excerpt:
                    digests.setdefault(tc.result_excerpt.text, set()).add(tc.result_digest)
    assert all(len(v) == 1 for v in digests.values()), "identical content produced differing digests"


def test_clean_excerpts_are_not_reported_merely_for_being_shared(portfolio):
    """Both operators receive identical benign shipping copy from shared
    merchants. Sharing content is not the signal; sharing POISONED content is.
    """
    reported = {f.details["result_digest"] for f in shared_attack_content(portfolio)}
    assert len(reported) == 1


# --- the whole sweep -------------------------------------------------------

def test_every_portfolio_finding_names_the_dossiers_it_rests_on(portfolio):
    """A portfolio finding that cannot say which submissions it spans is an
    assertion, not evidence — and acting on it means writing to those firms."""
    ids = {d.dossier.dossier_id for d in portfolio}
    for f in sweep(portfolio):
        assert f.subject_refs and set(f.subject_refs) <= ids


def test_correlated_movement_is_a_portfolio_finding_and_the_corpus_is_quiet() -> None:
    """F68 — agents at unrelated firms moving together.

    The corpus must NOT fire: over the span each pair actually shares, daily-
    count correlation runs -0.34 to +0.06 across the four dossiers, and two of
    the six pairs have too little overlap to measure. A dial that called any of
    that suspicious would call every shopping agent suspicious.
    So the sweep stays quiet here, and the test proves it can still speak by
    handing it two agents that genuinely move as one.
    """
    from agents.systemic import behavioural_correlation
    from data.dossier_loader import list_dossiers, load_for_pipeline

    dossiers = [load_for_pipeline(p) for p in sorted(list_dossiers())]
    assert behavioural_correlation(dossiers) == []

    # Two agents on the same rhythm: one dossier's own history, given to a copy
    # of itself, correlates perfectly with it.
    twin = dossiers[0].model_copy(deep=True)
    twin.dossier.dossier_id = "DOSSIER-TWIN-2026-001"
    (found,) = behavioural_correlation([dossiers[0], twin])
    assert found.failure == "F68" and found.details["correlation"] >= 0.7
    assert sorted(found.subject_refs) == sorted([dossiers[0].dossier.dossier_id, "DOSSIER-TWIN-2026-001"])


def test_a_short_overlap_is_not_evidence() -> None:
    """A correlation over a fortnight is arithmetic, not evidence."""
    from agents.systemic import behavioural_correlation
    from data.dossier_loader import list_dossiers, load_for_pipeline

    d = load_for_pipeline(sorted(list_dossiers())[0])
    twin = d.model_copy(deep=True)
    twin.dossier.dossier_id = "DOSSIER-TWIN-2026-001"
    assert behavioural_correlation([d, twin], min_overlap_days=10_000) == []


def test_every_dial_is_data_and_a_retired_rule_stops_sweeping() -> None:
    """The point of giving Systemic a book: its thresholds were Python defaults,
    which made the market-level layer the one thing a regulator could not tune,
    sweep or promote. Now editing the book changes the sweep."""
    from agents.systemic import sweep
    from data.dossier_loader import list_dossiers, load_for_pipeline
    from registry.loader import load_systemic_ruleset

    dossiers = [load_for_pipeline(p) for p in sorted(list_dossiers())]
    book = load_systemic_ruleset()
    assert {f.failure for f in sweep(dossiers, book)} == {"F57", "F67", "F69"}

    def edited(rule_id, **update):
        return book.model_copy(update={"rules": [
            r.model_copy(update=update) if r.rule_id == rule_id else r for r in book.rules]})

    # Retired: the sweep does not run and its failure cannot appear.
    assert "F67" not in {f.failure for f in sweep(dossiers, edited("SYS-MDL-01", status="retired"))}
    # Drafted: same, because a draft is not in force.
    assert "F69" not in {f.failure for f in sweep(dossiers, edited("SYS-PAY-01", status="draft"))}
    # A dial edit changes what the sweep finds, with no code change.
    loose = edited("SYS-CPT-01", params={"min_share": 99.0, "min_operators": 2, "recent_days": 90})
    assert "F57" not in {f.failure for f in sweep(dossiers, loose)}


def test_the_book_covers_exactly_the_failures_systemic_detects() -> None:
    from registry.loader import load_failure_catalogue, load_systemic_ruleset

    book = load_systemic_ruleset()
    declared = {fid for r in book.rules for fid in r.failures}
    assert declared == {"F57", "F67", "F68", "F69"}
    names = {f.failure_id for f in load_failure_catalogue().failures}
    assert declared <= names
    assert all(r.evaluation == "computable" for r in book.rules)  # sweeps are arithmetic
