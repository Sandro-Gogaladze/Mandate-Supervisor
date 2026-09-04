"""Context composition invariants: the evidence floor, verbatim extras, and
the recorded context being what the model actually receives."""
from __future__ import annotations

import json

import pytest

from agents.context import (
    ContextBlock,
    ContextCompositionError,
    canonical_context,
    compose_context,
    context_digest,
)
from registry.loader import load_drift_ruleset, load_kya_ruleset, load_log_ruleset, load_mandate_ruleset
from tests.fakes import FakeChatModel
from agents.llm import message_text


def test_composed_context_is_a_strict_superset_of_the_canonical_base(kst) -> None:
    base = canonical_context("log.analyze", kst, ruleset=load_log_ruleset())
    extras = [ContextBlock(block_id="answer:Q-1", content={"answer": "MER-QVC-8801 is new"})]
    composed = compose_context(base, extras)
    for key, value in base.items():
        assert composed[key] == value
    assert composed["supplementary_context"] == [
        {"block_id": "answer:Q-1", "content": {"answer": "MER-QVC-8801 is new"}}]


def test_extras_are_verbatim_never_summarized(kst) -> None:
    base = canonical_context("kya.review", kst)
    long_content = {"transactions": [{"id": f"TXN-{i}", "amount": 100.0 + i} for i in range(200)]}
    composed = compose_context(base, [ContextBlock(block_id="tx:full", content=long_content)])
    assert composed["supplementary_context"][0]["content"] == long_content


def test_double_composition_is_refused(kst) -> None:
    once = compose_context(canonical_context("kya.review", kst), [ContextBlock(block_id="b", content="x")])
    with pytest.raises(ContextCompositionError, match="compose once"):
        compose_context(once, [ContextBlock(block_id="c", content="y")])


def test_canonical_context_per_skill_matches_the_reasoning_modules(kst) -> None:
    """The common contract is additive; each legacy domain view stays exact."""
    from agents import drift_reasoning, kya_reasoning, log_reasoning, mandate_reasoning
    from agents.kya import KYAAgent
    from agents.mandate import MandateAgent

    kya_floor = KYAAgent().run(kst, load_kya_ruleset())
    assert canonical_context("kya.review", kst, floor_facts=kya_floor) == kya_reasoning.structured_view(kst, kya_floor)
    mnd_floor = MandateAgent().run(kst, load_mandate_ruleset())
    mandate_view = canonical_context("mandate.review", kst, ruleset=load_mandate_ruleset(), floor_facts=mnd_floor)
    assert {k: v for k, v in mandate_view.items() if k != "evidence_contract"} == mandate_reasoning.structured_view(kst, mnd_floor)
    log_rule = next(r for r in load_log_ruleset().rules if r.type == "transaction_structuring_detected")
    con_rule = next(r for r in load_log_ruleset().rules if r.type == "counterparty_concentration_anomaly")
    log_view = canonical_context("log.analyze", kst, ruleset=load_log_ruleset())
    assert {k: v for k, v in log_view.items() if k != "evidence_contract"} == log_reasoning.structured_view(kst, log_rule, con_rule)
    drift_rule = next(r for r in load_drift_ruleset().rules if r.type == "behavioral_drift_detected")
    drift_view = canonical_context("drift.analyze", kst, ruleset=load_drift_ruleset())
    assert {k: v for k, v in drift_view.items() if k != "evidence_contract"} == drift_reasoning.structured_view(kst, drift_rule)
    for specialist, view in (("mandate", mandate_view), ("log", log_view), ("drift", drift_view)):
        assert view["evidence_contract"]["specialist"] == specialist
        assert view["evidence_contract"]["failure_catalogue_version"] == "2026.1"


def test_the_floor_is_summarised_by_rule_not_dumped(kst) -> None:
    """Fifty runs' worth of facts, not fifty JSON files (HANDOFF §5.1)."""
    from agents.mandate import MandateAgent

    view = canonical_context("mandate.review", kst, floor_facts=MandateAgent().run(kst, load_mandate_ruleset()))
    assert view["runs_with_a_cart"] == 49 and len(view["runs"]) == 49
    assert view["rule_outcomes"]["MND-CAP-01"] == {"satisfied": 47, "breach": 2, "absent": 1}
    assert {b["run_id"] for b in view["floor_breaches"] if b["rule_id"] == "MND-CAP-01"} == {
        "RUN-2026-0722-0030", "RUN-2026-0811-0043"}
    # the shopper's sentence against the cart, merchant text fenced
    run = next(r for r in view["runs"] if r["run_id"] == "RUN-2026-0715-0025")
    assert run["shopper_request"] and run["line_items"][0]["description"].startswith("<<<UNTRUSTED_MERCHANT_TEXT>>>")
    assert run["agent_reasoning"].startswith("<<<UNTRUSTED_AGENT_TEXT>>>")


def test_digest_is_stable_and_content_sensitive(kst) -> None:
    base = canonical_context("kya.review", kst)
    assert context_digest(base) == context_digest(dict(base))
    changed = {**base, "runs": 999}
    assert context_digest(changed) != context_digest(base)
    assert context_digest(base).startswith("sha256:")


async def test_recorded_context_byte_matches_what_the_agent_receives(kst) -> None:
    from agents.log import LogAgent

    base = canonical_context("log.analyze", kst, ruleset=load_log_ruleset())
    composed = compose_context(base, [ContextBlock(block_id="officer_note", content="focus on August")])
    verdict = {"anomalous": False, "explanation": "n", "cited_evidence": "e"}
    fake = FakeChatModel({"record_log_analysis": {
        "structuring": verdict, "concentration": verdict, "velocity": verdict, "other_observations": []}})
    await LogAgent().review(kst, load_log_ruleset(), model=fake, context=composed)
    sent_human = message_text(fake.last_messages_for("record_log_analysis")[1])
    assert json.loads(sent_human) == composed
    assert sent_human == json.dumps(composed, indent=2)
