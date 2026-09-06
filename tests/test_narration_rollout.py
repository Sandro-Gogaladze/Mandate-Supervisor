import json
from agents.control_assurance import ControlAssuranceAgent
from agents.systemic import SystemicAgent
from registry.loader import load_all_rulesets
from tests.fakes import FakeChatModel
from agents.llm import message_text


async def test_control_assurance_narrates_without_judging(kst) -> None:
    books = load_all_rulesets()
    fake = FakeChatModel({"write_narration": {"narration": "Controls held on every run that mattered."}})
    review = await ControlAssuranceAgent().review(kst, books["controls"], model=fake)
    # Exactly one call, and it decides nothing: every posture and verdict was
    # already computed before the model was asked to describe them.
    assert fake.call_log == ["write_narration"]
    assert review.narration == "Controls held on every run that mattered."
    payload = json.loads(message_text(fake.last_messages_for("write_narration")[1]))
    assert payload["specialist"] == "control_assurance" and "controls" in payload["question"]
    assert "credential" not in payload and "runs" not in payload


async def test_systemic_narrates(kst) -> None:
    fake = FakeChatModel({"write_narration": {"narration": "Nothing links these submissions."}})
    review = await SystemicAgent().review(kst, model=fake, portfolio=[kst])
    # One submission is no portfolio: no assessment, so nothing to narrate.
    assert review.assessments == [] and review.narration is None and fake.call_log == []
