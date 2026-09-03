"""Loaders for the regulator-held registries.

These are the policy instrument, not submitted data: a firm sends its dossier,
and the regulator supplies the truth it is checked against. Anything an
operator could shade in its own favour lives here rather than in the
submission — which model versions are barred, which prompt releases were
approved, who really owns a merchant.

`agents.json` does not exist in any jurisdiction. It IS the policy proposal.
"""
from __future__ import annotations

import json
from functools import cache
from pathlib import Path

REGISTRY_DIR = Path(__file__).resolve().parent / "registry"


def _load(name: str, key: str, id_field: str) -> dict[str, dict]:
    data = json.loads((REGISTRY_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return {row[id_field]: row for row in data[key]}


@cache
def load_operators() -> dict[str, dict]:
    return _load("operators", "operators", "operator_id")


@cache
def load_institutions() -> dict[str, dict]:
    return _load("institutions", "institutions", "institution_id")


@cache
def load_agents() -> dict[str, dict]:
    return _load("agents", "agents", "agent_id")


@cache
def load_merchants() -> dict[str, dict]:
    return _load("merchants", "merchants", "merchant_id")


@cache
def load_tools() -> dict[str, dict]:
    return _load("tools", "tools", "tool_name")


@cache
def load_model_blocklist() -> dict[str, dict]:
    return _load("model_blocklist", "blocked", "model_version")
