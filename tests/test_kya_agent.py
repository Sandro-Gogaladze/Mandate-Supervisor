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
    # KYA-LIF-04 from the floor; KYA-REG-03 because a judged rule the model
    # returned no verdict for is recorded as undecided, never silently clear.
    assert [a.rule_id for a in review.assessments] == ["KYA-LIF-04", "KYA-REG-03"]
    reg = next(a for a in review.assessments if a.rule_id == "KYA-REG-03")
    assert reg.verdict == "inconclusive" and not reg.scores
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
    """The one output an officer reads first, and the one that must not be
    able to carry a claim the review did not make: it is given assessments
    and nothing else, split by whether they score."""
    fake = FakeChatModel({"write_narration": {"narration": "n"}})
    review_assessments = KYAAgent().assess(KYAAgent().run(kst, load_kya_ruleset()), load_kya_ruleset(), kst)
    await narrate_findings("DOSSIER-KST-2026-001", review_assessments, model=fake)
    payload = json.loads(message_text(fake.last_messages_for("write_narration")[1]))
    assert [f["rule_id"] for f in payload["scoring_breaches"]] == ["KYA-LIF-04"]
    assert payload["specialist"] == "kya" and payload["question"]
    assert "credential" not in payload and "runs" not in payload  # never raw case data


async def test_review_can_skip_the_model_entirely(kst) -> None:
    review = await KYAAgent().review(kst, load_kya_ruleset(), reason=False, narrate=False)
    assert review.observations == [] and review.narration is None and review.assessments


async def test_a_judged_rule_asks_for_its_verdict_only_while_active(kst) -> None:
    """KYA's two judged rules, in their two states. REG-03 is in force: the
    floor measures, the tool asks, the verdict becomes an assessment citing
    that measurement. CAP-04 is wired but still draft: the floor measures it
    anyway, so promoting it in the sandbox needs no code change — but the
    tool does not ask and no verdict exists."""
    book = load_kya_ruleset()
    facts = KYAAgent().run(kst, book)

    reg = {f.kind: f for f in facts if f.rule_id == "KYA-REG-03"}
    assert set(reg) == {"measurement"}                       # active: no absent
    assert reg["measurement"].values["distinct_counterparties"] == 18

    cap = {f.kind: f for f in facts if f.rule_id == "KYA-CAP-04"}
    assert set(cap) == {"absent", "measurement"}             # draft, and its evidence regardless
    assert cap["absent"].absent_reason == "rule_draft"
    assert cap["measurement"].values["granted_count"] > 0

    fake = FakeChatModel({"record_observations": {"observations": [], "classification_fit": {
        "consistent": False, "explanation": "Direct-marketing MCC 5964 sits outside a consumer shopping purpose.",
        "cited_evidence": "mccs"}}})
    _, judged = await reason_about_case(kst, facts, model=fake, ruleset=book)
    tools = json.dumps(fake.last_bind_kwargs["tools"])
    assert "classification_fit" in tools and "least_privilege" not in tools
    (a,) = judged
    assert (a.rule_id, a.verdict, a.fact_ids) == ("KYA-REG-03", "breach", [reg["measurement"].fact_id])


async def test_promoting_the_second_judged_rule_needs_no_code_change(kst) -> None:
    book = load_kya_ruleset()
    promoted = book.model_copy(update={"rules": [
        r.model_copy(update={"status": "active"}) if r.rule_id == "KYA-CAP-04" else r
        for r in book.rules]})
    facts = KYAAgent().run(kst, promoted)
    fake = FakeChatModel({"record_observations": {
        "observations": [],
        "classification_fit": {"consistent": True, "explanation": "ok", "cited_evidence": "mccs"},
        "least_privilege": {"proportionate": False,
                            "explanation": "payments.refund is on no card and the purpose never mentions refunds.",
                            "cited_evidence": "granted_but_not_on_card"}}})
    _, judged = await reason_about_case(kst, facts, model=fake, ruleset=promoted)
    assert "least_privilege" in json.dumps(fake.last_bind_kwargs["tools"])
    cap = next(a for a in judged if a.rule_id == "KYA-CAP-04")
    measurement = next(f for f in facts if f.rule_id == "KYA-CAP-04" and f.kind == "measurement")
    assert (cap.verdict, cap.fact_ids, cap.severity_floor) == ("breach", [measurement.fact_id], 0.4)


def test_get_model_without_a_key_raises_clearly(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMUnavailable):
        get_model()


async def test_narration_is_told_which_half_was_never_checked(kst) -> None:
    """Observations reach the narration call — the most useful thing a review
    found is sometimes what no rule asked about — but in their own block, with
    every row labelled, so the line an officer trusts most cannot state a
    hunch as established without saying so."""
    fake = FakeChatModel({
        "record_observations": {"observations": [
            {"note": "Two runs share a principal id.", "cited_field": "principal.principal_id"}],
            "classification_fit": {"consistent": True, "explanation": "ok", "cited_evidence": "mccs"}},
        "write_narration": {"narration": "n"},
    })
    await KYAAgent().review(kst, load_kya_ruleset(), model=fake)
    payload = json.loads(message_text(fake.last_messages_for("write_narration")[1]))
    (obs,) = payload["unverified_observations"]
    assert obs["note"] == "Two runs share a principal id."
    assert "unverified" in obs["status"] and "nothing here is scored" in obs["status"]
    # and it is nowhere near the verified half
    assert all("principal id" not in json.dumps(row) for row in
               payload["scoring_breaches"] + payload["other_outcomes"])
