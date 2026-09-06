"""Candidate rulebooks, forked rather than edited.

Every edit produces a new draft with its own digest. Nothing a sweep was
measured against can change afterwards, which is the only way a scorecard
still means something a week later.

Drafts live under `registry/drafts/`, which `registry/loader.py` has no
function to read. That is the isolation: a live review cannot load a draft
even by mistake, because there is no code path that would.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from data.canonical import payload_hash
# Keyed by AGENT name (agents/catalog.py), not registry.loader's names: the
# graph resolves a rulebook per dispatched agent, so an override keyed any
# other way would be accepted and then quietly ignored.
from agents.catalog import RULESET_LOADERS
from schemas import Rule, Ruleset, RulesetDraft

DRAFTS_DIR = Path(__file__).resolve().parent.parent / "registry" / "drafts"


class DraftError(ValueError):
    pass


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "draft"


def ruleset_digest(ruleset: Ruleset) -> str:
    return payload_hash(ruleset.model_dump(mode="json"), exclude_keys=())


def active_ruleset(domain: str) -> Ruleset:
    loader = RULESET_LOADERS.get(domain)
    if loader is None:
        raise DraftError(f"unknown domain {domain!r}")
    book = loader()
    if book is None:
        raise DraftError(f"{domain} has no rulebook to fork")
    return book


def describe_edits(base: Ruleset, candidate: Ruleset) -> list[str]:
    """What changed, in the terms a regulator edits in. Computed on write so
    the version graph can render a draft without loading both books."""
    before = {r.rule_id: r for r in base.rules}
    after = {r.rule_id: r for r in candidate.rules}
    out: list[str] = []
    for rule_id in sorted(set(before) | set(after)):
        b, a = before.get(rule_id), after.get(rule_id)
        if b is None:
            out.append(f"{rule_id} added")
            continue
        if a is None:
            out.append(f"{rule_id} removed")
            continue
        if b.status != a.status:
            out.append(f"{rule_id} {b.status} → {a.status}")
        if b.severity_weight != a.severity_weight:
            out.append(f"{rule_id} severity {b.severity_weight} → {a.severity_weight}")
        for key in sorted(set(b.params) | set(a.params)):
            if b.params.get(key) != a.params.get(key):
                out.append(f"{rule_id} {key} {b.params.get(key)} → {a.params.get(key)}")
    return out


def list_drafts(domain: str | None = None) -> list[RulesetDraft]:
    if not DRAFTS_DIR.exists():
        return []
    out = []
    for path in sorted(DRAFTS_DIR.glob("*/*.json")):
        draft = RulesetDraft.model_validate(json.loads(path.read_text(encoding="utf-8")))
        if domain is None or draft.domain == domain:
            out.append(draft)
    return sorted(out, key=lambda d: d.created_at, reverse=True)


def get_draft(draft_id: str) -> RulesetDraft:
    for draft in list_drafts():
        if draft.draft_id == draft_id:
            return draft
    raise DraftError(f"no draft {draft_id!r}")


def create_draft(*, domain: str, label: str, created_by: str,
                 base: Ruleset | None = None, notes: str | None = None) -> RulesetDraft:
    """Fork the in-force book (or `base`) into a new editable candidate."""
    base = base or active_ruleset(domain)
    draft_id = f"{domain}@{base.version}+{_slug(label)}"
    if any(d.draft_id == draft_id for d in list_drafts(domain)):
        raise DraftError(f"a draft called {label!r} already exists for {domain}")
    draft = RulesetDraft(
        draft_id=draft_id, domain=domain, base_version=base.version, label=label,
        ruleset=base.model_copy(deep=True), digest=ruleset_digest(base),
        created_by=created_by, created_at=datetime.now(timezone.utc).isoformat(),
        notes=notes, edits=[],
    )
    _write(draft)
    return draft


def edit_rule(draft_id: str, rule_id: str, *, status: str | None = None,
              severity_weight: float | None = None,
              params: dict | None = None) -> RulesetDraft:
    """Change one rule's policy knobs.

    Status, severity and parameters only. A rule's `description` and the
    `failures` it can establish are what the rule *means*; changing those is a
    code change with a checker behind it, not a tuning, and the sandbox
    refuses to pretend otherwise.
    """
    draft = get_draft(draft_id)
    rules = {r.rule_id: r for r in draft.ruleset.rules}
    if rule_id not in rules:
        raise DraftError(f"{rule_id} is not in {draft.domain}")
    current = rules[rule_id]
    updated = current.model_copy(update={
        **({"status": status} if status is not None else {}),
        **({"severity_weight": severity_weight} if severity_weight is not None else {}),
        **({"params": {**current.params, **params}} if params else {}),
    })
    # Re-validate: typed_params() rejects a parameter the rule type does not
    # take, so a bad edit fails here rather than at sweep time.
    updated = Rule.model_validate(updated.model_dump(mode="json"))
    book = draft.ruleset.model_copy(update={
        "rules": [updated if r.rule_id == rule_id else r for r in draft.ruleset.rules]
    })
    draft = draft.model_copy(update={
        "ruleset": book,
        "digest": ruleset_digest(book),
        "edits": describe_edits(active_ruleset(draft.domain), book),
    })
    _write(draft)
    return draft


def delete_draft(draft_id: str) -> None:
    draft = get_draft(draft_id)
    _path(draft).unlink(missing_ok=True)


def _path(draft: RulesetDraft) -> Path:
    return DRAFTS_DIR / draft.domain / f"{_slug(draft.draft_id)}.json"


def _write(draft: RulesetDraft) -> None:
    path = _path(draft)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(draft.model_dump(mode="json"), indent=2) + "\n",
                    encoding="utf-8")
