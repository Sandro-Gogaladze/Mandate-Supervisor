"""The skill registry and the first-pass set."""
from __future__ import annotations

from agents.catalog import AGENTS, PEERS
from agents.skills import REVIEW_SKILLS, SKILLS, SPECIALIST_SKILLS_BY_AGENT, skill_catalog


def test_catalog_is_every_agent_plus_the_investigator_in_stable_order() -> None:
    ids = [s.skill_id for s in skill_catalog()]
    assert len(ids) == 12 and {s.agent for s in skill_catalog()} == {*AGENTS, "investigator"}
    assert SKILLS["investigator.lookup"].produces == "observation"
    assert ids[-1] == "investigator.lookup"


def test_a_first_pass_covers_the_eight_peers_and_nothing_that_runs_after_or_on_request() -> None:
    assert {SKILLS[s].agent for s in REVIEW_SKILLS} == set(PEERS)
    assert "control_assurance.review" not in REVIEW_SKILLS  # runs after the peers by topology
    assert "systemic.review" not in REVIEW_SKILLS and "red_team.review" not in REVIEW_SKILLS  # on request
    assert "investigator.lookup" not in REVIEW_SKILLS


def test_every_finding_agent_has_exactly_one_skill() -> None:
    assert set(SPECIALIST_SKILLS_BY_AGENT) == set(AGENTS)
    assert all(SKILLS[s].agent == a for a, s in SPECIALIST_SKILLS_BY_AGENT.items())
