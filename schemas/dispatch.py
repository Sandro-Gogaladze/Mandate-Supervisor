"""The Orchestrator's propose-enforce dispatch plan (PLAN item 9).

CLAUDE.md: "Propose–enforce: LLM proposes a DispatchPlan, a deterministic
validator enforces a mandatory floor (Mandate+KYA always run; Log+Drift
run when history >= 30 tx)." `DispatchPlan` is the LLM's proposal;
`pipeline/dispatch.py::enforce_floor()` is the deterministic validator —
it can only ever turn a `False` into `True` (add a specialist the LLM
didn't propose but the floor requires), never the reverse. The LLM cannot
skip a mandatory specialist by proposing not to run it.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DispatchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_mandate: bool
    run_kya: bool
    run_log: bool
    run_drift: bool
    reasoning: str
