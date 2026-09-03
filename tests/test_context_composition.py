import pytest

# PARKED — migration-plan.md Phase 2/3.
#
# These cover context composition, which is real and still wanted. They are parked because
# their FIXTURE is gone: every one built its case from data/cases/*.json, and
# the corpus is now two dossiers with a different shape.
#
# Parked rather than deleted, and loudly rather than quietly: the logic under
# test did not stop mattering, and a silently shrinking suite is how a
# migration loses coverage nobody notices. Each comes back when the pipeline
# consumes a Dossier and a dossier fixture exists to replace the case one.
pytestmark = pytest.mark.skip(reason="fixture removed with the case corpus — migration Phase 2/3")

"""Stage 4 — context composition invariants (architecture-v2 §9.2–9.4)."""
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
from data.loader import DATA_DIR
from ingestion.normalize import build_verification_context, normalize_case
from registry.loader import load_drift_ruleset, load_kya_ruleset, load_log_ruleset, load_mandate_ruleset
from tests.fakes import FakeChatModel

_CTX = build_verification_context()


def _case(name: str = "case-005-structuring.json"):
    return normalize_case(DATA_DIR / "cases" / name, _CTX)


def test_composed_context_is_a_strict_superset_of_the_canonical_base() -> None:
    """§9.2 — the evidence floor: whatever the orchestrator adds, every key
    of the canonical view survives, values untouched."""
    case = _case()
    base = canonical_context("log.analyze", case, ruleset=load_log_ruleset())
    extras = [ContextBlock(block_id="answer:Q-1", content={"answer": "MER-GIE-001 is new"})]
    composed = compose_context(base, extras)
    for key, value in base.items():
        assert composed[key] == value
    assert composed["supplementary_context"] == [
        {"block_id": "answer:Q-1", "content": {"answer": "MER-GIE-001 is new"}}
    ]


def test_extras_are_verbatim_never_summarized() -> None:
    """§9.3 — a long block goes in whole. The orchestrator names blocks; it
    never authors or truncates their content."""
    case = _case()
    base = canonical_context("mandate.review", case)
    long_content = {"transactions": [{"id": f"TXN-{i}", "amount": 100.0 + i} for i in range(200)]}
    composed = compose_context(base, [ContextBlock(block_id="tx:full", content=long_content)])
    assert composed["supplementary_context"][0]["content"] == long_content


def test_double_composition_is_refused() -> None:
    case = _case()
    base = canonical_context("mandate.review", case)
    once = compose_context(base, [ContextBlock(block_id="b", content="x")])
    with pytest.raises(ContextCompositionError, match="compose once"):
        compose_context(once, [ContextBlock(block_id="c", content="y")])


def test_canonical_context_per_skill_matches_the_reasoning_modules() -> None:
    """One evidence definition: what the dispatcher records must be what the
    reasoning module would have built for itself."""
    from agents import drift_reasoning, kya_reasoning, log_reasoning, mandate_reasoning

    case = _case("case-006-drift.json")
    assert canonical_context("mandate.review", case) == mandate_reasoning.structured_view(case)
    assert canonical_context("kya.review", case, floor_findings=[]) == kya_reasoning.structured_view(case, [])

    log_rule = next(r for r in load_log_ruleset().rules if r.type == "transaction_structuring_detected")
    assert canonical_context("log.analyze", case, ruleset=load_log_ruleset()) == log_reasoning.structured_view(case, log_rule)

    drift_rule = next(r for r in load_drift_ruleset().rules if r.type == "behavioral_drift_detected")
    assert canonical_context("drift.analyze", case, ruleset=load_drift_ruleset()) == drift_reasoning.structured_view(case, drift_rule)


def test_digest_is_stable_and_content_sensitive() -> None:
    case = _case()
    base = canonical_context("mandate.review", case)
    assert context_digest(base) == context_digest(dict(base))
    changed = dict(base)
    changed["cart_total"] = 999999.0
    assert context_digest(changed) != context_digest(base)
    assert context_digest(base).startswith("sha256:")


async def test_recorded_context_byte_matches_what_the_agent_receives() -> None:
    """§9.4 end to end: the composed dict handed to review(context=...) is
    exactly what the model sees in its human message."""
    from agents.log import LogAgent

    case = _case()
    base = canonical_context("log.analyze", case, ruleset=load_log_ruleset())
    composed = compose_context(base, [ContextBlock(block_id="officer_note", content="focus on the 18th")])

    verdict = {"anomalous": False, "explanation": "n", "cited_evidence": "e"}
    fake = FakeChatModel({"record_log_analysis": {
        "structuring": verdict, "concentration": verdict, "velocity": verdict,
        "other_observations": [],
    }})
    await LogAgent().review(case, load_log_ruleset(), model=fake, context=composed)

    sent_human = fake.last_messages_for("record_log_analysis")[1].content
    assert json.loads(sent_human) == composed
    assert sent_human == json.dumps(composed, indent=2)
