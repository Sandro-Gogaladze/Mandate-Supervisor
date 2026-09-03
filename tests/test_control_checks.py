"""One test per CTL guarantee, against the real dossier.

The corpus is the fixture: these rules exist to find planted control failures,
so asserting against hand-built stubs would only prove the stubs matched the
code. Where a rule should stay silent, that is asserted too — a control
ruleset that fires on a clean submission is worse than one that fires on
nothing.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.control_checks import run_control_checks
from data.dossier_loader import load
from schemas import Ruleset

ROOT = Path(__file__).resolve().parent.parent
DOSSIER = ROOT / "data" / "dossiers" / "DOSSIER-KST-2026-001"


@pytest.fixture(scope="module")
def dossier():
    return load(DOSSIER)


@pytest.fixture(scope="module")
def ruleset():
    return Ruleset.model_validate(json.loads((ROOT / "registry/rulesets/ctl.json").read_text()))


@pytest.fixture(scope="module")
def peers(dossier):
    """What the other specialists found — CTL-EFF-01's only way to know a
    control *should* have triggered."""
    out: dict[str, set[str]] = {}
    for p in dossier.ground_truth.planted:
        if p.run_ref:
            out.setdefault(p.run_ref, set()).add(p.failure)
    return out


def _by_rule(findings):
    return {f.rule_id: f for f in findings}


def test_every_active_ctl_rule_has_a_checker(dossier, ruleset, peers):
    # run_control_checks raises NotImplementedError on an unregistered type.
    run_control_checks(dossier, ruleset, peers)


def test_control_that_should_have_triggered_but_passed_is_caught(dossier, ruleset, peers):
    f = _by_rule(run_control_checks(dossier, ruleset, peers))["CTL-EFF-01"]
    # Three controls recorded `passed` on runs where their own risk breached.
    assert len(f.details["evaluations"]) == 3
    assert any("category_match" in e for e in f.details["evaluations"])
    assert any("shopper_confirmation" in e for e in f.details["evaluations"])
    assert any("mandate_single_use" in e for e in f.details["evaluations"])


def test_eff_01_says_nothing_without_peer_findings(dossier, ruleset):
    """The rule cannot work alone, and must not pretend to.

    Knowing a control should have fired means knowing the risk it addresses
    materialised — someone else's finding. With no peers it has no grounds, and
    silence is the honest output.
    """
    assert "CTL-EFF-01" not in _by_rule(run_control_checks(dossier, ruleset, {}))


def test_override_rate_is_reported_against_triggered_controls_not_all_evaluations(
        dossier, ruleset, peers):
    f = _by_rule(run_control_checks(dossier, ruleset, peers))["CTL-EFF-03"]
    # 1 of 2 triggered — not 1 of 450 evaluations, which would read as 0%.
    assert f.details["triggered"] == 2
    assert f.details["overridden"] == 1
    assert f.details["rate"] == 0.5


def test_blocking_control_overridden_into_settlement_is_caught(dossier, ruleset, peers):
    f = _by_rule(run_control_checks(dossier, ruleset, peers))["CTL-EFF-04"]
    assert "ops-analyst-11" in f.summary


def test_dis_04_and_eff_04_never_report_the_same_transaction(dossier, ruleset, peers):
    """They partition one shape on whether an override was recorded."""
    found = _by_rule(run_control_checks(dossier, ruleset, peers))
    dis = {e.split(":")[0] for e in found.get("CTL-DIS-04", type("x", (), {"details": {"evaluations": []}})).details["evaluations"]} \
        if "CTL-DIS-04" in found else set()
    eff = {e.split(":")[0] for e in found["CTL-EFF-04"].details["evaluations"]}
    assert not (dis & eff)


def test_clean_control_families_stay_silent(dossier, ruleset, peers):
    """The repository, disposition and log families are sound in this dossier.

    A control ruleset that fires on a clean submission is worse than one that
    fires on nothing, so their silence is a guarantee, not an omission.
    """
    fired = set(_by_rule(run_control_checks(dossier, ruleset, peers)))
    assert not (fired & {"CTL-REP-01", "CTL-REP-02", "CTL-REP-03", "CTL-REP-04",
                         "CTL-DIS-01", "CTL-DIS-02", "CTL-DIS-03", "CTL-DIS-04",
                         "CTL-LOG-01", "CTL-LOG-02", "CTL-LOG-03"})


def test_log_reconciles_both_ways(dossier, ruleset, peers):
    """A settled transaction with no run is money outside any recorded episode;
    a completed run with no transaction is an episode the ledger never saw."""
    assert "CTL-LOG-03" not in _by_rule(run_control_checks(dossier, ruleset, peers))
    in_window = {t.run_ref for t in dossier.transaction_history if t.run_ref}
    completed = {r.run_id for r in dossier.runs if r.outcome == "completed"}
    assert in_window == completed
