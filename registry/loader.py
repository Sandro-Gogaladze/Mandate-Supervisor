"""Loader for versioned rulesets.

Only loading lives here for now. Diff and human-gated promotion
(draft -> active -> retired) are PLAN item 14 (registry promotion + policy
sandbox) — deliberately not built yet, so don't add them here piecemeal.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from schemas import Rule, Ruleset, ScoringConfig

REGISTRY_DIR = Path(__file__).resolve().parent
RULESETS_DIR = REGISTRY_DIR / "rulesets"
SCORING_PATH = REGISTRY_DIR / "scoring.json"


class RulesetLoadError(RuntimeError):
    """A ruleset file failed to parse or failed schema validation."""


def load_ruleset(path: Path | str) -> Ruleset:
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    try:
        return Ruleset.model_validate(raw)
    except ValidationError as exc:
        raise RulesetLoadError(f"{path.name} failed schema validation:\n{exc}") from exc


def load_kya_ruleset() -> Ruleset:
    return load_ruleset(RULESETS_DIR / "kya.json")


def load_mandate_ruleset() -> Ruleset:
    return load_ruleset(RULESETS_DIR / "mandate.json")


def load_log_ruleset() -> Ruleset:
    return load_ruleset(RULESETS_DIR / "log.json")


def load_drift_ruleset() -> Ruleset:
    return load_ruleset(RULESETS_DIR / "drift.json")


def active_rules(ruleset: Ruleset) -> list[Rule]:
    return [r for r in ruleset.rules if r.status == "active"]


def load_scoring_config(path: Path | str = SCORING_PATH) -> ScoringConfig:
    """Disposition tiers for the risk score (PLAN item 11) — same
    rules-as-data treatment as the rulesets: versioned JSON, sandbox-able
    later (item 14)."""
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    try:
        return ScoringConfig.model_validate(raw)
    except ValidationError as exc:
        raise RulesetLoadError(f"{path.name} failed schema validation:\n{exc}") from exc


def rules_by_finding_type(ruleset: Ruleset) -> dict[str, Rule]:
    """finding_type -> Rule, for active rules only (a finding should always
    be traceable to exactly one live rule)."""
    return {r.finding_type: r for r in active_rules(ruleset)}


def active_rules_by_type(ruleset: Ruleset) -> dict[str, Rule]:
    """rule.type -> Rule, for active rules only. What a checker function
    looks a specific rule up by, as opposed to what a Finding cites."""
    return {r.type: r for r in active_rules(ruleset)}
