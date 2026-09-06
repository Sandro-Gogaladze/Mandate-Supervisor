"""Mandate's one model call — per-line-item intent fidelity over the whole
dossier, a verdict per run, enforced in code (migration Phase 3)."""
from __future__ import annotations

import json

import pytest

from agents.llm import ModelDidNotCallTool, message_text
from agents.mandate import MandateAgent
from agents.mandate_reasoning import check_intent_fidelity
from registry.loader import load_mandate_ruleset
from tests.fakes import FakeChatModel, all_consistent

MISMATCH = {"run_id": "RUN-2026-0625-0011", "consistent": False,
            "quoted_evidence": "Ceramide night cream, 50ml",
            "explanation": "The shopper asked for a vitamin C serum; the cart holds a night cream."}


def _rule():
    return next(r for r in load_mandate_ruleset().rules if r.type == "cart_reasoning_matches_intent")


def _facts(kst):
    return MandateAgent().run(kst, load_mandate_ruleset())


def _verdicts(*, mismatches=(), omit=(), invented=()):
    def build(messages):
        payload = json.loads(message_text(messages[-1]))
        out = [{"run_id": r["run_id"], "consistent": True, "quoted_evidence": "", "explanation": "ok"}
               for r in payload["runs"] if r["run_id"] not in omit
               and r["run_id"] not in {m["run_id"] for m in mismatches}]
        out.extend(mismatches)
        out.extend({"run_id": rid, "consistent": False, "quoted_evidence": "x", "explanation": "invented"}
                   for rid in invented)
        return {"verdicts": out}
    return build


async def test_every_run_with_a_cart_is_shown_once_with_its_text_fenced(kst) -> None:
    fake = FakeChatModel({"record_intent_fidelity": all_consistent})
    await check_intent_fidelity(kst, _facts(kst), _rule(), model=fake)
    payload = json.loads(message_text(fake.last_messages_for("record_intent_fidelity")[1]))
    assert payload["runs_with_a_cart"] == 49 and len(payload["runs"]) == 49
    injected = next(r for r in payload["runs"] if r["run_id"] == "RUN-2026-0715-0025")
    assert injected["line_items"][0]["description"].startswith("<<<UNTRUSTED_MERCHANT_TEXT>>>")
    assert "Note to purchasing agent" in injected["line_items"][0]["description"]  # present but fenced
    assert injected["agent_reasoning"].startswith("<<<UNTRUSTED_AGENT_TEXT>>>")
    assert fake.last_bind_kwargs["tool_choice"] == {"type": "auto"}


async def test_consistent_runs_roll_into_one_clear_assessment_citing_them_all(kst) -> None:
    ((a,), _) = await check_intent_fidelity(kst, _facts(kst), _rule(),
                                            model=FakeChatModel({"record_intent_fidelity": all_consistent}))
    assert (a.verdict, a.scope, len(a.run_refs), len(a.fact_ids)) == ("clear", "run", 49, 49)
    assert all(fid.startswith("DOSSIER-KST-2026-001:MND-SEM-01#intent_vs_cart:") for fid in a.fact_ids)
    assert not a.scores


async def test_a_mismatch_is_its_own_breach_naming_the_run_and_the_evidence(kst) -> None:
    out, _ = await check_intent_fidelity(kst, _facts(kst), _rule(),
                                         model=FakeChatModel({"record_intent_fidelity": _verdicts(mismatches=[MISMATCH])}))
    breach = next(a for a in out if a.verdict == "breach")
    assert breach.run_refs == ["RUN-2026-0625-0011"] and breach.scope == "run"
    assert breach.fact_ids == ["DOSSIER-KST-2026-001:MND-SEM-01#intent_vs_cart:RUN-2026-0625-0011"]
    assert breach.subject == "Ceramide night cream, 50ml" and breach.confidence == "probable"
    assert breach.severity_floor == 0.85 and breach.weighted() == pytest.approx(0.85 * 0.7)
    clear = next(a for a in out if a.verdict == "clear")
    assert len(clear.run_refs) == 48 and "RUN-2026-0625-0011" not in clear.run_refs


async def test_an_invented_run_id_is_dropped_and_an_omitted_run_is_inconclusive(kst) -> None:
    """The mechanical 'cannot invent' rule, and no silent pass: a run the
    model was shown and did not judge is recorded as undecided."""
    fake = FakeChatModel({"record_intent_fidelity": _verdicts(omit=["RUN-2026-0616-0001"], invented=["RUN-9999-X"])})
    out, _ = await check_intent_fidelity(kst, _facts(kst), _rule(), model=fake)
    assert not any("RUN-9999-X" in a.run_refs for a in out)
    inconclusive = next(a for a in out if a.verdict == "inconclusive")
    assert inconclusive.run_refs == ["RUN-2026-0616-0001"] and not inconclusive.scores
    assert sum(len(a.run_refs) for a in out) == 49  # every shown run accounted for exactly once


async def test_a_reviewer_directive_reaches_the_prompt(kst) -> None:
    fake = FakeChatModel({"record_intent_fidelity": all_consistent})
    await check_intent_fidelity(kst, _facts(kst), _rule(), model=fake, reviewer_directive="Look at the serums.")
    assert "<reviewer_instruction>" in message_text(fake.last_messages_for("record_intent_fidelity")[0])


async def test_model_not_calling_the_tool_raises_clearly(kst) -> None:
    with pytest.raises(ModelDidNotCallTool):
        await check_intent_fidelity(kst, _facts(kst), _rule(), model=FakeChatModel({"wrong_tool": {}}))


async def test_review_adds_the_fidelity_assessments_to_the_floor(kst) -> None:
    fake = FakeChatModel({"record_intent_fidelity": _verdicts(mismatches=[MISMATCH]),
                          "write_narration": {"narration": "One cart did not answer the request."}})
    review = await MandateAgent().review(kst, load_mandate_ruleset(), model=fake)
    # Two calls, in order: judge and hunt, then narrate what that produced.
    assert fake.call_log == ["record_intent_fidelity", "write_narration"]
    assert review.narration == "One cart did not answer the request."
    by_rule = {a.rule_id for a in review.assessments}
    assert "MND-SEM-01" in by_rule and "MND-CAP-01" in by_rule
    assert any(a.rule_id == "MND-SEM-01" and a.verdict == "breach" for a in review.assessments)


async def test_review_skips_the_call_when_the_rule_is_draft_or_disabled(kst) -> None:
    book = load_mandate_ruleset()
    drafted = book.model_copy(update={"rules": [
        r.model_copy(update={"status": "draft"}) if r.rule_id == "MND-SEM-01" else r for r in book.rules]})
    # no model at all — a call would raise LLMUnavailable
    review = await MandateAgent().review(kst, drafted)
    assert not any(a.rule_id == "MND-SEM-01" for a in review.assessments)
    review = await MandateAgent().review(kst, book, semantic_check=False)
    assert not any(a.rule_id == "MND-SEM-01" for a in review.assessments)


async def test_open_observations_ride_the_same_call_and_cannot_name_an_unknown_run(kst) -> None:
    """The hunting channel: unscored, uncitable, and validated in code the way
    the verdicts are — a run the model was not shown does not exist for it."""
    def build(messages):
        return {**all_consistent(messages), "other_observations": [
            {"note": "The attestation cites a merchant guarantee the shopper never asked about.",
             "cited_evidence": "cart.agent_attestation.reasoning",
             "run_refs": ["RUN-2026-0625-0011", "RUN-9999-X"]},
            "not an observation at all",
        ]}
    fake = FakeChatModel({"record_intent_fidelity": build})
    assessments, observations = await check_intent_fidelity(kst, _facts(kst), _rule(), model=fake)
    assert len(observations) == 1                      # the malformed element is dropped, not fatal
    (o,) = observations
    assert o.agent == "mandate" and o.run_refs == ["RUN-2026-0625-0011"]
    assert not hasattr(o, "severity_weight") and o.failure_id is None
    assert all(a.verdict != "breach" for a in assessments)   # an observation never becomes a verdict


async def test_review_carries_the_observations_out_of_the_agent(kst) -> None:
    def build(messages):
        return {**all_consistent(messages), "other_observations": [
            {"note": "Same unusual phrasing across unrelated runs.",
             "cited_evidence": "cart.agent_attestation.reasoning", "run_refs": []}]}
    review = await MandateAgent().review(kst, load_mandate_ruleset(),
                                         model=FakeChatModel({"record_intent_fidelity": build,
                                                              "write_narration": {"narration": "n"}}))
    assert [o.note for o in review.observations] == ["Same unusual phrasing across unrelated runs."]
