"""Escalation routing (PLAN item 9): which agent should re-examine an
unresolved Observation on the one extra round.

Default: the observation's own agent re-examines its own ambiguity. But if
the note explicitly names a different agent — the concrete motivating case
from Phase 8's live run, Drift noting "this new counterparty... warrants a
specific KYA/counterparty verification check" — that's a real, actionable
cross-agent signal already sitting in the text; route it to KYA instead of
asking Drift the same question twice. Deliberately a plain keyword match,
not another LLM call: the signal ("does this note name a different
specialist") is simple and mechanical enough that adding an LLM classifier
would just be another point of failure for no real benefit, and it keeps
the loop's behavior bounded and predictable — which is the same reason the
loop itself is capped at one round rather than open-ended.
"""
from __future__ import annotations

import re

from schemas import FindingAgent, Observation

_AGENT_NAMES: tuple[FindingAgent, ...] = ("kya", "mandate", "log", "drift")

# Mandate's semantic subcheck never produces Observations (it's a scoped,
# required rule, not open exploration — see agents/mandate_reasoning.py's
# module docstring) so there's nothing to route *to* it for; re-dispatching
# it on escalation would just redundantly re-run the same deterministic
# work with no new question to answer.
ESCALATABLE_AGENTS: frozenset[str] = frozenset({"kya", "log", "drift"})


def target_agent_for(observation: Observation) -> str:
    note_lower = observation.note.lower()
    for name in _AGENT_NAMES:
        if name == observation.agent:
            continue
        if re.search(rf"\b{name}\b", note_lower):
            return name
    return observation.agent


def escalation_targets(observations: list[Observation]) -> list[str]:
    """Distinct agents worth re-dispatching, sorted for deterministic
    ordering. Never includes an agent with nothing routed to it."""
    targets = {target_agent_for(o) for o in observations}
    return sorted(t for t in targets if t in ESCALATABLE_AGENTS)


def observations_for(agent: str, observations: list[Observation]) -> list[Observation]:
    return [o for o in observations if target_agent_for(o) == agent]
