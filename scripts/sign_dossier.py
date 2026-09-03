"""Real Ed25519 signatures for every mandate and credential in a dossier.

Signed by scripts/sign_corpus.py in the same pass as the case corpus, sharing
one KeyRing. That sharing is not incidental: a dossier and a case can describe
the same real agent and therefore carry the same `signer_key_id`. Two separate
signing runs each mint a fresh keypair for that id, so whichever ran last left
the other's signatures unverifiable — with no error, because each run
self-verified only its own half.

Usage: python scripts/sign_corpus.py  (signs cases and dossiers together)
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.canonical import canonical_bytes, sha256_hex  # noqa: E402

DOSSIERS_DIR = ROOT / "data" / "dossiers"


def sign_envelope(obj: dict, payload: dict, keyring) -> None:
    """Sign `payload` into the SignatureEnvelope already sitting on `obj`."""
    env = obj["signature"]
    digest = sha256_hex(canonical_bytes(payload))
    env["signed_payload_hash"] = f"sha256:{digest}"
    env["value"] = base64.b64encode(
        keyring.private_key_for(env["signer_key_id"]).sign(canonical_bytes(payload))).decode()


def strip_sig(obj: dict) -> dict:
    return {k: v for k, v in obj.items() if k != "signature"}


def sign_dossier_file(path: Path, keyring) -> tuple[int, int]:
    d = json.loads(path.read_text(encoding="utf-8"))

    for cred in [d["kya_credential"], *d["credential_history"]]:
        for link in cred["delegation_chain"]:
            link["signature"]["value"] = base64.b64encode(
                keyring.private_key_for(link["signature"]["signer_key_id"]).sign(
                    canonical_bytes(strip_sig(link)))).decode()
        sign_envelope(cred, strip_sig(cred), keyring)

    intent = d["intent_mandate"]
    sign_envelope(intent, strip_sig(intent), keyring)
    intent_hash = intent["signature"]["signed_payload_hash"]

    carts = payments = 0
    for run in d["runs"]:
        if cart := run.get("cart"):
            # The chain is what makes tampering detectable: each link names the
            # hash of the artifact it descends from, so editing a cart after
            # the fact breaks the payment that points at it.
            cart["chain_link"]["prev_mandate_id"] = intent["intent_mandate_id"]
            cart["chain_link"]["prev_mandate_hash"] = intent_hash
            sign_envelope(cart, strip_sig(cart), keyring)
            carts += 1
            if pay := run.get("payment"):
                pay["chain_link"]["prev_mandate_id"] = cart["cart_mandate_id"]
                pay["chain_link"]["prev_mandate_hash"] = cart["signature"]["signed_payload_hash"]
                sign_envelope(pay, strip_sig(pay), keyring)
                payments += 1

    path.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return carts, payments


def sign_all_dossiers(keyring) -> None:
    for path in sorted(DOSSIERS_DIR.glob("*.json")) if DOSSIERS_DIR.exists() else []:
        carts, payments = sign_dossier_file(path, keyring)
        print(f"Signed {path.name}: {carts} carts, {payments} payments.")
