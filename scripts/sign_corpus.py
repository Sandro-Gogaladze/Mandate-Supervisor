"""Real Ed25519 signing for every mandate/credential object in the corpus.

Replaces every placeholder `ed25519-sig-placeholder:<hex>` value with a real
signature and every placeholder `signed_payload_hash` with a real SHA-256 of
the object's canonical content (see data/canonical.py). One Ed25519 keypair
is minted per distinct `signer_key_id`; public keys are written to
data/registry/keystore.json, private keys stay in memory for this run only.

Mechanical, run once (or whenever the corpus content changes) — see
docs/phases/01-synthetic-data.md §5 and PLAN.md item 1.

Usage: uv run python scripts/sign_corpus.py
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from data.canonical import canonical_bytes, sha256_hex  # noqa: E402
from data.keystore import save_public_keys  # noqa: E402
from data.loader import CASES_DIR, load_manifest  # noqa: E402

# The one case deliberately built so its declared chain hash doesn't
# recompute (docs/phases/01-synthetic-data.md §3, case 3). Real signing
# would otherwise make chain_link.prev_mandate_hash correct by construction,
# erasing the finding it exists to test.
BROKEN_CHAIN_FILE = "case-003-broken-chain.json"

import base64  # noqa: E402


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


class KeyRing:
    """Mints one Ed25519 keypair per signer_key_id, on first use."""

    def __init__(self) -> None:
        self._private: dict[str, Ed25519PrivateKey] = {}

    def private_key_for(self, signer_key_id: str) -> Ed25519PrivateKey:
        if signer_key_id not in self._private:
            self._private[signer_key_id] = Ed25519PrivateKey.generate()
        return self._private[signer_key_id]

    def public_keys(self) -> dict[str, Ed25519PublicKey]:
        return {key_id: priv.public_key() for key_id, priv in self._private.items()}


def sign_object(obj: dict, keyring: KeyRing, *, include_hash: bool = True) -> None:
    """Sign `obj` in place: fills signature.value (and signed_payload_hash
    unless the caller says otherwise) from obj's own canonical content."""
    signer_key_id = obj["signature"]["signer_key_id"]
    message = canonical_bytes(obj)
    signature = keyring.private_key_for(signer_key_id).sign(message)
    obj["signature"]["value"] = b64(signature)
    if include_hash:
        obj["signature"]["signed_payload_hash"] = f"sha256:{sha256_hex(message)}"


def sign_case(raw: dict, keyring: KeyRing, *, is_broken_chain: bool) -> dict:
    case = deepcopy(raw)
    credential = case["kya_credential"]
    intent = case["mandate_chain"]["intent"]
    cart = case["mandate_chain"]["cart"]
    payment = case["mandate_chain"]["payment"]

    # Delegation entries: each holder self-attests {level, holder_id,
    # holder_type, name} — no signed_payload_hash/signed_at on these (see
    # schemas/kya.py / docs/phases/01-synthetic-data.md §2.5).
    for entry in credential["delegation_chain"]:
        sign_object(entry, keyring, include_hash=False)

    sign_object(credential, keyring)
    sign_object(intent, keyring)

    cart["chain_link"]["prev_mandate_hash"] = intent["signature"]["signed_payload_hash"]
    sign_object(cart, keyring)

    if is_broken_chain:
        # Deliberately corrupt: hash what the cart *would* have hashed to had
        # its total matched the payment's authorized amount instead of its
        # own — i.e. "the cart was altered after the payment was built
        # against it" (docs/phases/01-synthetic-data.md §3, case 3).
        stale_cart = deepcopy(cart)
        stale_cart["cart_total"] = payment["amount"]
        stale_hash = sha256_hex(canonical_bytes(stale_cart))
        payment["chain_link"]["prev_mandate_hash"] = f"sha256:{stale_hash}"
    else:
        payment["chain_link"]["prev_mandate_hash"] = cart["signature"]["signed_payload_hash"]

    sign_object(payment, keyring)
    return case


def verify_object(obj: dict, public_keys: dict[str, Ed25519PublicKey], *, expect_hash: bool = True) -> list[str]:
    problems = []
    signer_key_id = obj["signature"]["signer_key_id"]
    message = canonical_bytes(obj)
    pub = public_keys[signer_key_id]
    try:
        pub.verify(base64.b64decode(obj["signature"]["value"]), message)
    except InvalidSignature:
        problems.append(f"signature does not verify for signer {signer_key_id}")
    if expect_hash:
        actual = f"sha256:{sha256_hex(message)}"
        if obj["signature"]["signed_payload_hash"] != actual:
            problems.append(
                f"signed_payload_hash stale for signer {signer_key_id} "
                f"(stored={obj['signature']['signed_payload_hash']!r}, actual={actual!r})"
            )
    return problems


def verify_case(case: dict, public_keys: dict[str, Ed25519PublicKey], *, is_broken_chain: bool) -> list[str]:
    problems = []
    credential = case["kya_credential"]
    intent = case["mandate_chain"]["intent"]
    cart = case["mandate_chain"]["cart"]
    payment = case["mandate_chain"]["payment"]

    for entry in credential["delegation_chain"]:
        problems += [f"{case['case_id']} delegation[{entry['level']}]: {p}" for p in verify_object(entry, public_keys, expect_hash=False)]
    problems += [f"{case['case_id']} kya_credential: {p}" for p in verify_object(credential, public_keys)]
    problems += [f"{case['case_id']} intent: {p}" for p in verify_object(intent, public_keys)]
    problems += [f"{case['case_id']} cart: {p}" for p in verify_object(cart, public_keys)]
    problems += [f"{case['case_id']} payment: {p}" for p in verify_object(payment, public_keys)]

    chain_matches = cart["chain_link"]["prev_mandate_hash"] == intent["signature"]["signed_payload_hash"]
    if not chain_matches:
        problems.append(f"{case['case_id']} cart->intent chain_link does not match (unexpected)")

    payment_matches_cart = payment["chain_link"]["prev_mandate_hash"] == cart["signature"]["signed_payload_hash"]
    if is_broken_chain and payment_matches_cart:
        problems.append(f"{case['case_id']} payment->cart chain_link matches, but this case should be broken")
    if not is_broken_chain and not payment_matches_cart:
        problems.append(f"{case['case_id']} payment->cart chain_link mismatch (unexpected)")

    return problems


def main() -> None:
    keyring = KeyRing()
    manifest = load_manifest()
    signed_cases: list[tuple[Path, dict]] = []

    for entry in manifest:
        path = CASES_DIR.parent / entry["file"]
        raw = json.loads(path.read_text(encoding="utf-8"))
        is_broken_chain = path.name == BROKEN_CHAIN_FILE
        signed = sign_case(raw, keyring, is_broken_chain=is_broken_chain)
        signed_cases.append((path, signed))

    for path, signed in signed_cases:
        path.write_text(json.dumps(signed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Dossiers share this keyring — see scripts/sign_dossier.py for why they
    # cannot be signed in a separate pass.
    from sign_dossier import sign_all_dossiers  # noqa: E402
    sign_all_dossiers(keyring)

    save_public_keys(keyring.public_keys())

    public_keys = keyring.public_keys()
    all_problems = []
    for entry, (path, signed) in zip(manifest, signed_cases):
        is_broken_chain = path.name == BROKEN_CHAIN_FILE
        all_problems += verify_case(signed, public_keys, is_broken_chain=is_broken_chain)

    print(f"Signed {len(signed_cases)} cases, {len(public_keys)} signer keys.")
    print(f"Wrote data/registry/keystore.json ({len(public_keys)} public keys).")
    if all_problems:
        print(f"\n{len(all_problems)} problem(s) found on self-verify:")
        for p in all_problems:
            print(f"  - {p}")
        sys.exit(1)
    print("Self-verify passed: every signature checks out, chain links match "
          "(except case-003, deliberately broken as designed).")


if __name__ == "__main__":
    main()
