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

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# What a section asserts about the findings it rests on. Prose cannot be
# checked against data, but this can: a section that calls something a breach
# must cite a finding carrying severity, and a section that says an area was
# clear must not cite one. Without it, grounding verified that citations were
# real and complete while saying nothing about whether the section described
# them correctly — forty satisfied checks could be written up as failures and
# every rule would still pass.
SectionCharacter = Literal["adverse", "clear", "mixed"]


class ReportSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    body: str
    cited_finding_ids: list[str] = Field(default_factory=list)
    # Optional in the schema, required by the drafting tool: reports already on
    # the ledger predate the field, and a required one would fail to project.
    # check_grounding() only ever runs on a freshly drafted report, where the
    # tool schema guarantees it is set.
    character: SectionCharacter | None = None


class DraftReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    overall_assessment: str
    sections: list[ReportSection] = Field(default_factory=list)
    # The one place unverified observations may be summarized — labeled as
    # such in the UI, never cited, never scored.
    open_observations_note: str | None = None
