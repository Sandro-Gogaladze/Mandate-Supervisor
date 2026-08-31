"""Common agent contract (PLAN item 4): typed case + ruleset in, Finding[] out.

`ruleset` is `Ruleset | None` — a real, domain-scoped ruleset for agents
that have one (KYA, Mandate), `None` for agents whose domain has no
ruleset file yet (Log, Drift — PLAN items 7/8). Taking a ruleset as an
argument, rather than each agent loading its own active ruleset
internally, is what lets policy sandbox mode (PLAN item 14) later run the
exact same agent against a draft ruleset instead of swapping any agent code.
"""
from __future__ import annotations

from typing import Protocol

from ingestion.normalize import IngestedCase
from schemas import Finding, Ruleset


class SpecialistAgent(Protocol):
    name: str

    def run(self, case: IngestedCase, ruleset: Ruleset | None) -> list[Finding]: ...
