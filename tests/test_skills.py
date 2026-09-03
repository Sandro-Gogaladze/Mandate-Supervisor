import pytest

# PARKED — migration-plan.md Phase 2/3.
#
# These cover the skill registry, which is real and still wanted. They are parked because
# their FIXTURE is gone: every one built its case from data/cases/*.json, and
# the corpus is now two dossiers with a different shape.
#
# Parked rather than deleted, and loudly rather than quietly: the logic under
# test did not stop mattering, and a silently shrinking suite is how a
# migration loses coverage nobody notices. Each comes back when the pipeline
# consumes a Dossier and a dossier fixture exists to replace the case one.
pytestmark = pytest.mark.skip(reason="fixture removed with the case corpus — migration Phase 2/3")

"""Stage 4 — skill registry + the add-only floor (architecture-v2 §13)."""
from __future__ import annotations

import pytest

from agents.skills import SKILLS, enforce_skill_floor, skill_catalog
from data.loader import DATA_DIR
from ingestion.normalize import normalize_case, build_verification_context

_CTX = build_verification_context()


def _case(name: str):
    return normalize_case(DATA_DIR / "cases" / name, _CTX)


def test_catalog_is_the_five_skills_in_stable_order() -> None:
    ids = [s.skill_id for s in skill_catalog()]
    assert ids == ["mandate.review", "kya.review", "log.analyze", "drift.analyze", "investigator.lookup"]
    assert SKILLS["investigator.lookup"].produces == "observation"
    assert all(SKILLS[i].produces == "finding" for i in ids[:4])


def test_empty_selection_on_pass_1_still_runs_the_floor() -> None:
    """The hostile case: an orchestrator (or a hostile prompt steering it)
    proposes running nothing. Coverage survives in code."""
    case = _case("case-001-compliant.json")  # 24 tx: log yes, drift no (<30)
    result = enforce_skill_floor([], case, pass_number=1)
    assert result == ["mandate.review", "kya.review", "log.analyze"]


def test_floor_adds_drift_at_its_own_minimum() -> None:
    case = _case("case-006-drift.json")  # 49 tx
    result = enforce_skill_floor([], case, pass_number=1)
    assert result == ["mandate.review", "kya.review", "log.analyze", "drift.analyze"]


def test_floor_never_removes_a_proposed_skill() -> None:
    case = _case("case-007-prompt-injection.json")  # 7 tx — drift below minimum
    result = enforce_skill_floor(["drift.analyze"], case, pass_number=1)
    # drift stays because the orchestrator proposed it; the floor is add-only
    assert "drift.analyze" in result
    assert {"mandate.review", "kya.review", "log.analyze"} <= set(result)


def test_no_floor_on_later_passes() -> None:
    """A directed or investigative pass targets exactly what was named —
    coverage was already guaranteed when the case first arrived."""
    case = _case("case-001-compliant.json")
    assert enforce_skill_floor(["log.analyze"], case, pass_number=2) == ["log.analyze"]
    assert enforce_skill_floor([], case, pass_number=2) == []


def test_unknown_skill_id_raises() -> None:
    case = _case("case-001-compliant.json")
    with pytest.raises(ValueError, match="unknown skill"):
        enforce_skill_floor(["portfolio.sweep"], case, pass_number=1)


def test_skill_floor_agrees_with_the_plan_level_floor() -> None:
    """Two enforcement points, one policy: the DispatchPlan floor
    (pipeline/dispatch.py, kept for the plan the UI displays) and the skill
    floor must never disagree about who runs."""
    from pipeline.dispatch import enforce_floor
    from schemas import DispatchPlan

    nothing = DispatchPlan(run_mandate=False, run_kya=False, run_log=False, run_drift=False, reasoning="")
    for name in ["case-001-compliant.json", "case-005-structuring.json", "case-006-drift.json",
                 "case-007-prompt-injection.json"]:
        case = _case(name)
        plan = enforce_floor(nothing, case)
        skills = set(enforce_skill_floor([], case, pass_number=1))
        assert plan.run_mandate == ("mandate.review" in skills)
        assert plan.run_kya == ("kya.review" in skills)
        assert plan.run_log == ("log.analyze" in skills)
        assert plan.run_drift == ("drift.analyze" in skills)
