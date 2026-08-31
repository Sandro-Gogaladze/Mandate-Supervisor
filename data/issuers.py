"""Loader for the KYA issuer trust registry."""
from __future__ import annotations

import json
from pathlib import Path

ISSUERS_PATH = Path(__file__).resolve().parent / "registry" / "issuers.json"


def load_issuer_registry() -> dict[str, dict]:
    """issuer_id -> issuer record."""
    data = json.loads(ISSUERS_PATH.read_text(encoding="utf-8"))
    return {i["issuer_id"]: i for i in data["issuers"]}
