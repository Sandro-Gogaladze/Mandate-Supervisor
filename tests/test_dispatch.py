import pytest

# PARKED — migration-plan.md Phase 2/3.
#
# These cover dispatch planning, which is real and still wanted. They are parked because
# their FIXTURE is gone: every one built its case from data/cases/*.json, and
# the corpus is now two dossiers with a different shape.
#
# Parked rather than deleted, and loudly rather than quietly: the logic under
# test did not stop mattering, and a silently shrinking suite is how a
# migration loses coverage nobody notices. Each comes back when the pipeline
# consumes a Dossier and a dossier fixture exists to replace the case one.
pytestmark = pytest.mark.skip(reason="fixture removed with the case corpus — migration Phase 2/3")

from data.loader import CASES_DIR
from ingestion.normalize import normalize_case
from pipeline.dispatch import enforce_floor, propose_dispatch_plan
from schemas import DispatchPlan
from tests.fakes import FakeChatModel


async def test_propose_dispatch_plan_parses_fake_response() -> None:
    case = normalize_case(CASES_DIR / "case-001-compliant.json")
    fake = FakeChatModel({"record_dispatch_plan": {
        "run_mandate": True, "run_kya": True, "run_log": True, "run_drift": False,
        "reasoning": "24 transactions, under Drift's 30-tx floor.",
    }})

    plan = await propose_dispatch_plan(case, model=fake)

    assert isinstance(plan, DispatchPlan)
    assert plan.run_drift is False
    assert fake.last_bind_kwargs["tool_choice"] == {"type": "auto"}


def test_floor_forces_mandate_and_kya_even_if_llm_proposes_false() -> None:
    case = normalize_case(CASES_DIR / "case-001-compliant.json")
    plan = DispatchPlan(run_mandate=False, run_kya=False, run_log=False, run_drift=False, reasoning="test")

    enforced = enforce_floor(plan, case)

    assert enforced.run_mandate is True
    assert enforced.run_kya is True


def test_floor_does_not_force_drift_below_its_minimum() -> None:
    # case-001 has 24 transactions — under Drift's default 30-tx floor.
    case = normalize_case(CASES_DIR / "case-001-compliant.json")
    plan = DispatchPlan(run_mandate=True, run_kya=True, run_log=False, run_drift=False, reasoning="test")

    enforced = enforce_floor(plan, case)

    assert enforced.run_drift is False
    assert enforced.run_log is True  # Log's floor is just "non-empty history"


def test_floor_forces_drift_above_its_minimum() -> None:
    # case-006 has 49 transactions — comfortably over the 30-tx floor.
    case = normalize_case(CASES_DIR / "case-006-drift.json")
    plan = DispatchPlan(run_mandate=True, run_kya=True, run_log=False, run_drift=False, reasoning="test")

    enforced = enforce_floor(plan, case)

    assert enforced.run_drift is True


def test_floor_never_removes_something_the_llm_proposed() -> None:
    case = normalize_case(CASES_DIR / "case-007-prompt-injection.json")  # only 7 tx
    plan = DispatchPlan(run_mandate=True, run_kya=True, run_log=True, run_drift=True, reasoning="run everything anyway")

    enforced = enforce_floor(plan, case)

    assert enforced.run_drift is True  # LLM proposed it; floor only ever adds, never removes
