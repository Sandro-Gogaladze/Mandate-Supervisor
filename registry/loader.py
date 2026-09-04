"""Loader for versioned rulesets.

Only loading lives here for now. Diff and human-gated promotion
(draft -> active -> retired) are PLAN item 14 (registry promotion + policy
sandbox) — deliberately not built yet, so don't add them here piecemeal.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from schemas import FailureCatalogue, Rule, Ruleset, ScoringConfig

REGISTRY_DIR = Path(__file__).resolve().parent
RULESETS_DIR = REGISTRY_DIR / "rulesets"
SCORING_PATH = REGISTRY_DIR / "scoring.json"
FAILURE_CATALOGUE_PATH = REGISTRY_DIR / "failures.json"


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


def load_ctl_ruleset() -> Ruleset:
    return load_ruleset(RULESETS_DIR / "ctl.json")


def load_consent_ruleset() -> Ruleset:
    return load_ruleset(RULESETS_DIR / "consent.json")


def load_injection_ruleset() -> Ruleset:
    return load_ruleset(RULESETS_DIR / "injection.json")


def load_counterparty_ruleset() -> Ruleset:
    return load_ruleset(RULESETS_DIR / "counterparty.json")


def load_provenance_ruleset() -> Ruleset:
    return load_ruleset(RULESETS_DIR / "provenance.json")


# One book per agent (HANDOFF §3). Systemic has no book: its three failures are
# properties of the portfolio, not rules against a submission.
RULESET_LOADERS = {
    "kya": load_kya_ruleset, "mandate": load_mandate_ruleset, "log": load_log_ruleset,
    "drift": load_drift_ruleset, "controls": load_ctl_ruleset, "consent": load_consent_ruleset,
    "injection": load_injection_ruleset, "counterparty": load_counterparty_ruleset,
    "provenance": load_provenance_ruleset,
}


def load_all_rulesets() -> dict[str, Ruleset]:
    """domain -> ruleset, every book in the registry."""
    return {domain: load() for domain, load in RULESET_LOADERS.items()}


def failure_map(*rulesets: Ruleset) -> dict[str, set[str]]:
    """rule_id -> the failure ids it detects, from the rules' own declarations."""
    return {r.rule_id: set(r.failures) for rs in rulesets for r in rs.rules if r.failures}


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


def load_failure_catalogue(path: Path | str = FAILURE_CATALOGUE_PATH) -> FailureCatalogue:
    """Load the stable F1--F73 vocabulary used by rules and occurrences."""
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    try:
        catalogue = FailureCatalogue.model_validate(raw)
    except ValidationError as exc:
        raise RulesetLoadError(f"{path.name} failed schema validation:\n{exc}") from exc
    ids = [f.failure_id for f in catalogue.failures]
    expected = [f"F{i}" for i in range(1, 74)]
    if ids != expected:
        raise RulesetLoadError(
            f"{path.name} must contain F1--F73 exactly once and in order; got {ids}"
        )
    return catalogue


def rules_by_finding_type(ruleset: Ruleset) -> dict[str, Rule]:
    """finding_type -> Rule, for active rules only (a finding should always
    be traceable to exactly one live rule)."""
    return {r.finding_type: r for r in active_rules(ruleset)}


def active_rules_by_type(ruleset: Ruleset) -> dict[str, Rule]:
    """rule.type -> Rule, for active rules only. What a checker function
    looks a specific rule up by, as opposed to what a Finding cites."""
    return {r.type: r for r in active_rules(ruleset)}
