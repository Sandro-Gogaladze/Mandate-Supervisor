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
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.canonical import canonical_bytes, sha256_hex  # noqa: E402

DOSSIERS_DIR = ROOT / "data" / "dossiers"


def strip_sig(obj: dict) -> dict:
    return {k: v for k, v in obj.items() if k != "signature"}


def sign_envelope(obj: dict, payload: dict, keyring) -> None:
    """Sign `payload` into the SignatureEnvelope already sitting on `obj`."""
    env = obj["signature"]
    env["signed_payload_hash"] = f"sha256:{sha256_hex(canonical_bytes(payload))}"
    env["value"] = base64.b64encode(
        keyring.private_key_for(env["signer_key_id"]).sign(canonical_bytes(payload))).decode()


def sign_dossier_dir(directory: Path, keyring) -> tuple[int, int]:
    """Sign a dossier directory in place, then rebuild its run index.

    Order matters. Signing rewrites every run file, which changes its bytes,
    which invalidates the digest the index attests to. So the index is rebuilt
    last, from what is actually on disk — otherwise the loader would reject the
    very dossier this just produced.
    """
    dossier_path = directory / "dossier.json"
    d = json.loads(dossier_path.read_text(encoding="utf-8"))

    for cred in [d["kya_credential"], *d["credential_history"]]:
        for link in cred["delegation_chain"]:
            link["signature"]["value"] = base64.b64encode(
                keyring.private_key_for(link["signature"]["signer_key_id"]).sign(
                    canonical_bytes(strip_sig(link)))).decode()
        sign_envelope(cred, strip_sig(cred), keyring)

    carts = payments = 0
    for ref in d["run_index"]:
        path = directory / ref["file"]
        run = json.loads(path.read_text(encoding="utf-8"))
        # One chain per run: the shopper's own intent, their cart, their payment.
        intent = run["intent_mandate"]
        sign_envelope(intent, strip_sig(intent), keyring)
        if cart := run.get("cart"):
            # Each link names the hash of what it descends from, so editing a
            # cart after the fact breaks the payment that points at it.
            cart["chain_link"]["prev_mandate_id"] = intent["intent_mandate_id"]
            cart["chain_link"]["prev_mandate_hash"] = intent["signature"]["signed_payload_hash"]
            sign_envelope(cart, strip_sig(cart), keyring)
            carts += 1
            if pay := run.get("payment"):
                pay["chain_link"]["prev_mandate_id"] = cart["cart_mandate_id"]
                pay["chain_link"]["prev_mandate_hash"] = cart["signature"]["signed_payload_hash"]
                sign_envelope(pay, strip_sig(pay), keyring)
                payments += 1
        path.write_text(json.dumps(run, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        ref["sha256"] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    dossier_path.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return carts, payments


def sign_all_dossiers(keyring) -> None:
    for directory in sorted(DOSSIERS_DIR.iterdir()) if DOSSIERS_DIR.exists() else []:
        if not (directory / "dossier.json").exists():
            continue
        carts, payments = sign_dossier_dir(directory, keyring)
        print(f"Signed {directory.name}: {carts} carts, {payments} payments, index rebuilt.")
