"""Prompts as per-run arguments (architecture-v2 §6, §12).

Every agent's system prompt has a default that lives in registry/prompts/ as
versioned JSON, changed through normal code review — `rules are data, never
hardcoded` extended from thresholds to instructions. A supervisor can see
the default and override it **for a single run**; overrides are never
persisted, so nothing accumulates and nothing drifts.

Each prompt is three parts, and only the middle is editable:

    [FIXED PREAMBLE]   role, what exists, that a floor exists
    [BODY]             the default guidance, or the per-run override
    [FIXED CONTRACT]   "your final response MUST be a call to <tool>"

The preamble and contract are not overridable — a hostile or careless edit
must not be able to stop the model calling its tool, and must not be able to
rewrite the agent's role. The floor itself is enforced in code either way
(recorded on the plan as not_dispatched), so even a prompt that says "skip
KYA" changes nothing about coverage.

The *full effective text* of every prompt used by a run is recorded on that
run's `run_started` event — not a version pointer, since an overridden
prompt has no stable artifact to point at.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "registry" / "prompts"

# Which prompts each run kind uses — this is what gets assembled, recorded
# on run_started, and made overridable per run.
_REVIEW_PROMPTS: tuple[str, ...] = (
    "ORCHESTRATOR",
    "INVESTIGATOR",
    "SYNTHESIZER",
    "SPECIALIST-MANDATE",
    "SPECIALIST-KYA",
    "KYA-NARRATION",
    "SPECIALIST-PROVENANCE",
    "SPECIALIST-INJECTION",
    "SPECIALIST-COUNTERPARTY",
    "SPECIALIST-CONSENT",
    "SPECIALIST-LOG",
    "SPECIALIST-DRIFT",
)

# A first pass and a later question are the same run through the same
# graph with the same orchestrator; the kind names the record, not the code.
PROMPTS_BY_RUN_KIND: dict[str, tuple[str, ...]] = {
    "triage": _REVIEW_PROMPTS,
    "investigation": _REVIEW_PROMPTS,
    "drafting": ("DRAFTING",),
}


class PromptSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_id: str
    version: str
    preamble: str
    body: str
    contract: str
    notes: str | None = None


class PromptAssembly(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_id: str
    effective: str
    override: str | None
    default_version: str


class UnknownPromptError(KeyError):
    pass


@lru_cache(maxsize=None)
def load_prompt(prompt_id: str) -> PromptSpec:
    path = PROMPTS_DIR / f"{prompt_id.lower()}.json"
    if not path.exists():
        raise UnknownPromptError(
            f"no prompt {prompt_id!r} in {PROMPTS_DIR} — prompts are registry data, "
            f"never invented at runtime"
        )
    spec = PromptSpec.model_validate(json.loads(path.read_text(encoding="utf-8")))
    if spec.prompt_id != prompt_id:
        raise UnknownPromptError(f"{path.name} declares prompt_id {spec.prompt_id!r}, expected {prompt_id!r}")
    return spec


def assemble(prompt_id: str, *, override: str | None = None) -> PromptAssembly:
    """preamble + (override or default body) + contract. The bracketing parts
    are immune to the override by construction, not by request."""
    spec = load_prompt(prompt_id)
    body = override if override is not None else spec.body
    effective = "\n\n".join(part for part in (spec.preamble, body, spec.contract) if part)
    return PromptAssembly(
        prompt_id=prompt_id,
        effective=effective,
        override=override,
        default_version=spec.version,
    )


def assemble_run_prompts(
    kind: str, overrides: dict[str, str] | None = None
) -> dict[str, dict]:
    """Everything a run of `kind` will use, assembled once up front — the
    exact structure recorded on run_started and read back by the projection.
    An override naming a prompt this run kind doesn't use is an error, not a
    silent no-op: the officer thinks they changed something."""
    overrides = overrides or {}
    prompt_ids = PROMPTS_BY_RUN_KIND[kind]
    unknown = set(overrides) - set(prompt_ids)
    if unknown:
        raise UnknownPromptError(
            f"override(s) for {sorted(unknown)} — a {kind} run only uses {list(prompt_ids)}"
        )
    return {
        pid: assemble(pid, override=overrides.get(pid)).model_dump(exclude={"prompt_id"})
        for pid in prompt_ids
    }


def effective_text(prompts: dict[str, dict], prompt_id: str) -> str:
    """The system prompt a node should actually send, from an assembled set."""
    return prompts[prompt_id]["effective"]
