"""KYA's review: floor, ceiling and narration, on the dossier."""
from __future__ import annotations

import json

import pytest

from agents.kya import KYAAgent
from agents.kya_reasoning import ModelDidNotCallTool, narrate_findings, reason_about_case
from agents.llm import LLMUnavailable, get_model, message_text
from registry.loader import load_kya_ruleset
from tests.fakes import FakeChatModel


async def test_review_returns_floor_assessments_observations_and_narration(kst) -> None:
    fake = FakeChatModel({
        "record_observations": {"observations": [
            {"note": "Issuer name resembles a well-known consortium.", "cited_field": "kya_credential.issuer.issuer_name"}]},
        "write_narration": {"narration": "One credential overlap; nothing else."},
    })
    review = await KYAAgent().review(kst, load_kya_ruleset(), model=fake)
    assert [a.rule_id for a in review.assessments] == ["KYA-LIF-04"]
    (obs,) = review.observations
    assert obs.agent == "kya" and obs.cited_evidence == "kya_credential.issuer.issuer_name"
    assert review.narration == "One credential overlap; nothing else."
    assert fake.call_log == ["record_observations", "write_narration"]


async def test_the_ceiling_sees_the_credential_and_the_floors_outcomes_not_facts(kst) -> None:
    fake = FakeChatModel({"record_observations": {"observations": []}})
    facts = KYAAgent().run(kst, load_kya_ruleset())
    await reason_about_case(kst, facts, model=fake)
    payload = json.loads(message_text(fake.last_messages_for("record_observations")[1]))
    assert payload["credential"]["issuer_id"] == "ISS-002"
    assert payload["already_flagged_by_fixed_rules"] == ["KYA-LIF-04"]
    assert payload["rule_outcomes"]["KYA-LIF-01"] == {"satisfied": 50}
    assert "facts" not in payload
    # REG-03's evidence widening: the activity summary and the register's classification
    assert payload["registered_classification"] == "consumer_shopping"
    assert payload["activity_summary"]["transactions"] == 102 and payload["activity_summary"]["largest_single"] == 867.0


async def test_malformed_observation_is_skipped_not_fatal(kst) -> None:
    fake = FakeChatModel({"record_observations": {"observations": [
        "just a string", {"note": "fine", "cited_field": "capabilities"}]}})
    observations, judged = await reason_about_case(kst, [], model=fake)
    assert [o.note for o in observations] == ["fine"] and judged == []


async def test_model_that_does_not_call_the_tool_is_a_clear_error(kst) -> None:
    with pytest.raises(ModelDidNotCallTool):
        await reason_about_case(kst, [], model=FakeChatModel({}))


async def test_narration_is_grounded_in_assessments_only(kst) -> None:
    fake = FakeChatModel({"write_narration": {"narration": "n"}})
    review_assessments = KYAAgent().assess(KYAAgent().run(kst, load_kya_ruleset()), load_kya_ruleset(), kst)
    await narrate_findings("DOSSIER-KST-2026-001", review_assessments, model=fake)
    payload = json.loads(message_text(fake.last_messages_for("write_narration")[1]))
    assert [f["rule_id"] for f in payload["findings"]] == ["KYA-LIF-04"]
    assert "credential" not in payload  # never raw case data


async def test_review_can_skip_the_model_entirely(kst) -> None:
    review = await KYAAgent().review(kst, load_kya_ruleset(), reason=False, narrate=False)
    assert review.observations == [] and review.narration is None and review.assessments


async def test_reg_03_is_judged_only_when_promoted(kst) -> None:
    """The one judged KYA rule. Draft: the tool does not ask and no verdict
    exists. Active (the sandbox promotes it): the ceiling judges activity
    against the registered classification, citing the floor's measurement."""
    book = load_kya_ruleset()
    facts = KYAAgent().run(kst, book)
    by_kind = {f.kind: f for f in facts if f.rule_id == "KYA-REG-03"}
    assert set(by_kind) == {"absent", "measurement"}  # draft, and the evidence it would judge over
    measurement = by_kind["measurement"]
    assert measurement.values["distinct_counterparties"] == 18

    fake = FakeChatModel({"record_observations": {"observations": []}})
    _, judged = await reason_about_case(kst, facts, model=fake, ruleset=book)
    assert judged == [] and "classification_fit" not in json.dumps(fake.last_bind_kwargs["tools"])

    promoted = book.model_copy(update={"rules": [
        r.model_copy(update={"status": "active"}) if r.rule_id == "KYA-REG-03" else r for r in book.rules]})
    fake = FakeChatModel({"record_observations": {"observations": [], "classification_fit": {
        "consistent": False, "explanation": "Direct-marketing MCC 5964 sits outside a consumer shopping purpose.",
        "cited_evidence": "mccs"}}})
    _, (a,) = await reason_about_case(kst, KYAAgent().run(kst, promoted), model=fake, ruleset=promoted)
    assert (a.rule_id, a.verdict, a.fact_ids) == ("KYA-REG-03", "breach", [measurement.fact_id])
    assert "classification_fit" in json.dumps(fake.last_bind_kwargs["tools"])


def test_get_model_without_a_key_raises_clearly(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMUnavailable):
        get_model()
