"""One test per CTL guarantee, against the real dossier.

The corpus is the fixture: these rules exist to find planted control failures,
so asserting against hand-built stubs would only prove the stubs matched the
code. Where a rule should stay silent, that is asserted too — a control
ruleset that fires on a clean submission is worse than one that fires on
nothing — and under the fact contract "silent" means `satisfied` facts, not
an absence of output.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agents.control_checks import _DOSSIER_CHECKERS, _RUN_CHECKERS, run_control_checks
from agents.facts import breaches, by_rule
from data.dossier_loader import load
from registry.loader import RULESETS_DIR, load_ruleset

ROOT = Path(__file__).resolve().parent.parent
KST = ROOT / "data" / "dossiers" / "DOSSIER-KST-2026-001"
HAL = ROOT / "data" / "dossiers" / "DOSSIER-HAL-2026-001"


@pytest.fixture(scope="module")
def dossier():
    return load(KST)


@pytest.fixture(scope="module")
def halcyon():
    return load(HAL)


@pytest.fixture(scope="module")
def ruleset():
    return load_ruleset(RULESETS_DIR / "ctl.json")


@pytest.fixture(scope="module")
def peers(dossier):
    """What the other specialists found — CTL-EFF-01's only way to know a
    control *should* have triggered."""
    out: dict[str, set[str]] = {}
    for p in dossier.ground_truth.planted:
        if p.run_ref:
            out.setdefault(p.run_ref, set()).add(p.failure)
    return out


@pytest.fixture(scope="module")
def facts(dossier, ruleset, peers):
    return run_control_checks(dossier, ruleset, peers)


def _breach_runs(facts, rule_id) -> set[str]:
    return {f.run_ref for f in breaches(facts) if f.rule_id == rule_id}


def test_every_active_ctl_rule_produces_a_fact(facts, ruleset):
    # run_control_checks raises NotImplementedError on an unregistered type;
    # here every active rule must also have said something.
    active = {r.rule_id for r in ruleset.rules if r.status == "active"}
    assert set(by_rule(facts)) == active


def test_run_level_rules_answer_for_every_run(facts, dossier, ruleset):
    """One fact per run per run-level rule — the run list depends on it."""
    run_ids = {r.run_id for r in dossier.runs}
    run_level = {r.rule_id for r in ruleset.rules if r.type in _RUN_CHECKERS}
    dossier_level = {r.rule_id for r in ruleset.rules if r.type in _DOSSIER_CHECKERS}
    for rule_id, fs in by_rule(facts).items():
        refs = [f.run_ref for f in fs]
        if rule_id in run_level:
            assert set(refs) == run_ids and len(refs) == len(run_ids), rule_id
        else:
            assert rule_id in dossier_level and refs == [None], rule_id


def test_control_that_should_have_triggered_but_passed_is_caught(facts):
    """Three controls recorded `passed` on runs where their own risk breached."""
    assert _breach_runs(facts, "CTL-EFF-01") == {
        "RUN-2026-0805-0039", "RUN-2026-0810-0042", "RUN-2026-0818-0048"}
    silent = {s for f in breaches(facts) if f.rule_id == "CTL-EFF-01"
              for s in f.values["silent_controls"]}
    assert any("category_match" in s for s in silent)
    assert any("shopper_confirmation" in s for s in silent)
    assert any("mandate_single_use" in s for s in silent)


def test_eff_01_awaits_peers_rather_than_pretending(dossier, ruleset):
    """The rule cannot work alone, and must not pretend to.

    Knowing a control should have fired means knowing the risk it addresses
    materialised — someone else's finding. `None` (not supplied) and `{}`
    (supplied, nothing breached) are different answers, and the old contract
    could not tell them apart.
    """
    waiting = by_rule(run_control_checks(dossier, ruleset, None))["CTL-EFF-01"]
    assert {(f.kind, f.absent_reason, f.missing) for f in waiting} == {
        ("absent", "awaiting_peers", "peer findings")}
    clean = by_rule(run_control_checks(dossier, ruleset, {}))["CTL-EFF-01"]
    assert {f.kind for f in clean} == {"satisfied"}


def test_override_rate_is_reported_against_triggered_controls_not_all_evaluations(facts):
    f, = by_rule(facts)["CTL-EFF-03"]
    # 1 of 2 triggered — not 1 of 450 evaluations, which would read as 0%.
    assert f.kind == "breach"
    assert f.values["triggered"] == 2
    assert f.values["overridden"] == 1
    assert f.values["rate"] == 0.5


def test_override_rate_is_out_of_scope_when_no_control_triggered(halcyon, ruleset):
    """Halcyon filed 180 evaluations but no trigger, so no rate exists. The
    rule is inapplicable rather than blocked by missing evidence."""
    f, = by_rule(run_control_checks(halcyon, ruleset, {}))["CTL-EFF-03"]
    assert (f.kind, f.absent_reason, f.missing) == ("absent", "out_of_scope", None)
    assert f.values["triggered"] == 0


def test_blocking_control_overridden_into_settlement_is_caught(facts):
    assert _breach_runs(facts, "CTL-EFF-04") == {"RUN-2026-0811-0043"}
    f, = [f for f in breaches(facts) if f.rule_id == "CTL-EFF-04"]
    assert "ops-analyst-11" in f.statement
    assert f.values["overridden_by"] == ["ops-analyst-11"]


def test_dis_04_and_eff_04_never_report_the_same_run(facts):
    """They partition one shape on whether an override was recorded."""
    assert not (_breach_runs(facts, "CTL-DIS-04") & _breach_runs(facts, "CTL-EFF-04"))


def test_a_control_that_held_is_a_satisfied_fact_not_a_skipped_run(facts):
    """RUN-2026-0722-0030 was blocked by KST-CTL-001. That is the strongest
    evidence a blocking control is real, and the old contract had no way to
    say it — a run with no payment simply produced nothing."""
    f, = [f for f in by_rule(facts)["CTL-DIS-04"] if f.run_ref == "RUN-2026-0722-0030"]
    assert f.kind == "satisfied"
    assert "KST-CTL-001" in f.statement and "held" in f.statement
    assert f.values == {"rejected": ["KST-CTL-001"], "payment": False}


def test_clean_control_families_are_satisfied_not_silent(facts):
    """The repository, disposition and log families are sound in this dossier.

    A control ruleset that fires on a clean submission is worse than one that
    fires on nothing — and under the fact contract their soundness is a set of
    `satisfied` facts, not an absence of output.
    """
    sound = {"CTL-REP-01", "CTL-REP-02", "CTL-REP-03", "CTL-REP-04",
             "CTL-DIS-01", "CTL-DIS-02", "CTL-DIS-03", "CTL-DIS-04",
             "CTL-LOG-01", "CTL-LOG-02", "CTL-LOG-03", "CTL-EFF-02"}
    grouped = by_rule(facts)
    for rule_id in sound:
        kinds = {f.kind for f in grouped[rule_id]}
        assert "breach" not in kinds, rule_id
        assert "satisfied" in kinds, rule_id


def test_log_reconciles_both_ways(facts, dossier):
    """A settled transaction with no run is money outside any recorded episode;
    a completed run with no transaction is an episode the ledger never saw."""
    f, = by_rule(facts)["CTL-LOG-03"]
    assert f.kind == "satisfied"
    in_window = {t.run_ref for t in dossier.transaction_history if t.run_ref}
    completed = {r.run_id for r in dossier.runs if r.outcome == "completed"}
    assert in_window == completed
    assert f.values["completed_runs"] == len(completed)


def test_a_run_with_nothing_to_evaluate_is_out_of_scope_not_satisfied(dossier, ruleset):
    """An abandoned run that never reached a control checkpoint has nothing
    for the disposition rules to inspect. That is `out_of_scope`, and it must
    not be counted as a control working."""
    run = next(r for r in dossier.runs if r.run_id == "RUN-2026-0624-0010")
    bare = run.model_copy(update={"controls_evaluated": []})
    d = dossier.model_copy(update={"runs": [bare if r is run else r for r in dossier.runs]})
    fs = [f for f in run_control_checks(d, ruleset, {}) if f.run_ref == bare.run_id]
    kinds = {f.rule_id: (f.kind, f.absent_reason) for f in fs}
    assert kinds["CTL-DIS-01"] == ("absent", "out_of_scope")   # no payment, no action
    assert kinds["CTL-DIS-02"] == ("absent", "out_of_scope")
    assert kinds["CTL-EFF-02"] == ("absent", "out_of_scope")


def test_a_payment_with_no_control_evaluation_is_the_dis_01_breach(dossier, ruleset):
    run = next(r for r in dossier.runs if r.run_id == "RUN-2026-0811-0043")
    bare = run.model_copy(update={"controls_evaluated": []})
    d = dossier.model_copy(update={"runs": [bare if r is run else r for r in dossier.runs]})
    f, = [f for f in run_control_checks(d, ruleset, {})
          if f.run_ref == bare.run_id and f.rule_id == "CTL-DIS-01"]
    assert f.kind == "breach"
