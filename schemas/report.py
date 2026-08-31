"""The drafting agent's typed output (PLAN item 12).

A report is not free prose — it's sections whose every claim traces to a
real `Finding` via `cited_finding_ids`. That structure is what makes
grounding *checkable* by a deterministic validator (agents/grounding.py)
instead of an LLM judging another LLM: the validator can verify citations
against state mechanically, which is the only honest version of "every
claim must cite a real finding" (CLAUDE.md guardrails).

Observations never appear inside sections: they're unverified model
hunches (schemas/observation.py), and mixing them into cited prose would
launder them into looking like findings. They get exactly one clearly
labeled slot, `open_observations_note`.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ReportSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    body: str
    cited_finding_ids: list[str] = Field(default_factory=list)


class DraftReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    overall_assessment: str
    sections: list[ReportSection] = Field(default_factory=list)
    # The one place unverified observations may be summarized — labeled as
    # such in the UI, never cited, never scored.
    open_observations_note: str | None = None
