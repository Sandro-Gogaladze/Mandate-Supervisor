"""The four specialists' common contract on the dossier: facts from run(),
assessments from assess(), a SpecialistReview from review()."""
from __future__ import annotations

from agents.base import SpecialistReview
from agents.drift import DriftAgent
from agents.facts import breaches, by_rule
from agents.kya import KYAAgent
from agents.log import LogAgent
from agents.mandate import MandateAgent
from registry.loader import load_drift_ruleset, load_kya_ruleset, load_log_ruleset, load_mandate_ruleset
from tests.corpus import thin
from tests.fakes import make_graph_fake


def test_every_agent_returns_nothing_without_a_ruleset(kst) -> None:
    for agent in (KYAAgent(), MandateAgent(), LogAgent(), DriftAgent()):
        assert agent.run(kst, None) == []
        assert agent.assess([], None, kst) == []


def test_every_agent_exposes_the_common_contract() -> None:
    for agent in (KYAAgent(), MandateAgent(), LogAgent(), DriftAgent()):
        assert isinstance(agent.name, str) and agent.name
        assert callable(agent.run) and callable(agent.assess) and callable(agent.review)


def test_kya_floor_is_crypto_plus_policy_and_finds_the_overlap(kst) -> None:
    facts = KYAAgent().run(kst, load_kya_ruleset())
    assert {f.domain for f in facts} == {"kya"}
    assert {"KYA-IDN-01", "KYA-ACC-03", "KYA-LIF-01", "KYA-LIF-04"} <= set(by_rule(facts))
    assert [f.rule_id for f in breaches(facts)] == ["KYA-LIF-04"]
    a, = KYAAgent().assess(facts, load_kya_ruleset(), kst)
    assert (a.rule_id, a.verdict, a.scope) == ("KYA-LIF-04", "breach", "case")


def test_mandate_floor_is_chain_plus_policy_and_explains_the_contained_breach(kst) -> None:
    facts = MandateAgent().run(kst, load_mandate_ruleset())
    assert {f.domain for f in facts} == {"mandate"} and "MND-CHN-01" in by_rule(facts)
    verdicts = {(a.rule_id, a.verdict) for a in MandateAgent().assess(facts, load_mandate_ruleset(), kst)}
    assert verdicts == {("MND-CAP-01", "breach"), ("MND-CAP-01", "explained"), ("MND-CAP-02", "breach"),
                        ("MND-CAP-05", "breach"), ("MND-USE-01", "breach")}


def test_log_floor_is_measurements_and_absents_without_history(kst) -> None:
    facts = LogAgent().run(kst, load_log_ruleset())
    assert {f.kind for f in facts} == {"measurement"}
    assert {f.rule_id for f in facts if f.rule_id} == {"LOG-STR-01", "LOG-CON-01", "LOG-VEL-01"}
    assert LogAgent().assess(facts, load_log_ruleset(), kst) == []  # judged: no floor verdicts
    empty = LogAgent().run(thin(kst, 0), load_log_ruleset())
    assert {(f.kind, f.absent_reason, f.missing) for f in empty} == {("absent", "insufficient_history", "transaction_history")}


def test_drift_floor_is_a_measurement_or_an_honest_absence(kst) -> None:
    f, = DriftAgent().run(kst, load_drift_ruleset())
    assert f.kind == "measurement" and f.rule_id == "DRIFT-BHV-01"
    f, = DriftAgent().run(thin(kst, 10), load_drift_ruleset())
    assert (f.kind, f.absent_reason) == ("absent", "insufficient_history") and f.values["transactions"] == 10


async def test_review_returns_a_specialist_review_for_every_agent(kst) -> None:
    fake = make_graph_fake()
    for agent, ruleset in ((KYAAgent(), load_kya_ruleset()), (MandateAgent(), load_mandate_ruleset()),
                           (LogAgent(), load_log_ruleset()), (DriftAgent(), load_drift_ruleset())):
        review = await agent.review(kst, ruleset, model=fake)
        assert isinstance(review, SpecialistReview)
        assert review.facts and all(f.domain == agent.name for f in review.facts)
        assert all(a.agent == agent.name for a in review.assessments)
        cited = {fid for a in review.assessments for fid in a.fact_ids}
        assert cited <= {f.fact_id for f in review.facts}


async def test_drift_declines_below_its_baseline_without_calling_the_model(kst) -> None:
    fake = make_graph_fake()
    review = await DriftAgent().review(thin(kst, 10), load_drift_ruleset(), model=fake)
    assert review.insufficient_baseline is True
    # the thin history is a data gap on the case — a concern, not a verdict
    gap, = review.assessments
    assert gap.verdict == "concern" and gap.rule_id is None and "transaction_history" in gap.narrative
    assert "record_drift_analysis" not in fake.call_log
