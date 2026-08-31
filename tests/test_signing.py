import base64
import json
from copy import deepcopy

import pytest
from cryptography.exceptions import InvalidSignature

from data.canonical import canonical_bytes, sha256_hex
from data.keystore import load_public_keys
from data.loader import CASES_DIR, DATA_DIR, load_manifest
from scripts.sign_corpus import BROKEN_CHAIN_FILE, verify_case


def _load_signed(name: str) -> dict:
    return json.loads((CASES_DIR / name).read_text(encoding="utf-8"))


def test_every_signature_in_the_corpus_verifies() -> None:
    public_keys = load_public_keys()
    problems = []
    for entry in load_manifest():
        path = DATA_DIR / entry["file"]
        case = json.loads(path.read_text(encoding="utf-8"))
        problems += verify_case(case, public_keys, is_broken_chain=path.name == BROKEN_CHAIN_FILE)
    assert problems == []


def test_broken_chain_case_genuinely_fails_hash_recomputation() -> None:
    case = _load_signed(BROKEN_CHAIN_FILE)
    cart = case["mandate_chain"]["cart"]
    payment = case["mandate_chain"]["payment"]
    assert payment["chain_link"]["prev_mandate_hash"] != cart["signature"]["signed_payload_hash"]
    # but the cart's own signature is still perfectly valid on its own
    public_keys = load_public_keys()
    pub = public_keys[cart["signature"]["signer_key_id"]]
    pub.verify(base64.b64decode(cart["signature"]["value"]), canonical_bytes(cart))


def test_tampering_with_signed_content_breaks_verification() -> None:
    """This is the whole point: it must be possible to make a real signature
    fail, not just compare two placeholder strings."""
    case = _load_signed("case-001-compliant.json")
    intent = deepcopy(case["mandate_chain"]["intent"])
    public_keys = load_public_keys()
    pub = public_keys[intent["signature"]["signer_key_id"]]

    # untampered: verifies fine
    pub.verify(base64.b64decode(intent["signature"]["value"]), canonical_bytes(intent))

    # tamper with a scope field after the fact
    intent["authorization_scope"]["max_transaction_amount"] = 999999.0
    with pytest.raises(InvalidSignature):
        pub.verify(base64.b64decode(intent["signature"]["value"]), canonical_bytes(intent))

    # and the hash no longer matches either
    assert intent["signature"]["signed_payload_hash"] != f"sha256:{sha256_hex(canonical_bytes(intent))}"
