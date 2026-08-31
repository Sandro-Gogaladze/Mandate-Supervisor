"""Canonical serialization + hashing for signed mandate/credential objects.

Shared by scripts/sign_corpus.py (signs with this) and, later, ingestion/
(verifies with this) — both sides must agree byte-for-byte on what "the
content of this object" means, or a legitimate object would fail to verify.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_bytes(obj: dict[str, Any], *, exclude_keys: tuple[str, ...] = ("signature",)) -> bytes:
    """Deterministic byte representation of `obj` minus its own signature block.

    Sorted keys + compact separators, so the same logical content always
    produces the same bytes regardless of how it was constructed.
    """
    content = {k: v for k, v in obj.items() if k not in exclude_keys}
    return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def payload_hash(obj: dict[str, Any], *, exclude_keys: tuple[str, ...] = ("signature",)) -> str:
    """The `sha256:<hex>` value that belongs in signed_payload_hash / chain_link."""
    return f"sha256:{sha256_hex(canonical_bytes(obj, exclude_keys=exclude_keys))}"
