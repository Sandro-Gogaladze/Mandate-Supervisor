"""Real Ed25519 signing for every mandate and credential in the corpus.

The corpus is now dossiers only — the seven single-cart cases are gone, so this
is a thin entry point over scripts/sign_dossier.py. It survives as a separate
script because signing is one pass over ONE keyring: two dossiers can describe
agents that share a signer_key_id, and signing them in separate runs would have
each mint a fresh keypair for that id, leaving the other's signatures
unverifiable with no error.

One keypair per distinct signer_key_id, public keys to data/registry/
keystore.json, private keys in memory for this run only. Losing them means the
next run mints fresh ones and re-signs everything; nothing downstream depends on
key material being stable across runs.

Usage: python scripts/sign_corpus.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from data.keystore import save_public_keys  # noqa: E402
from sign_dossier import sign_all_dossiers  # noqa: E402


class KeyRing:
    """One keypair per signer_key_id, minted on first use."""

    def __init__(self) -> None:
        self._private: dict[str, Ed25519PrivateKey] = {}

    def private_key_for(self, signer_key_id: str) -> Ed25519PrivateKey:
        if signer_key_id not in self._private:
            self._private[signer_key_id] = Ed25519PrivateKey.generate()
        return self._private[signer_key_id]

    def public_keys(self) -> dict[str, Ed25519PublicKey]:
        return {k: v.public_key() for k, v in self._private.items()}


def main() -> None:
    keyring = KeyRing()
    sign_all_dossiers(keyring)
    keys = keyring.public_keys()
    save_public_keys(keys)
    print(f"Wrote data/registry/keystore.json ({len(keys)} public keys).")


if __name__ == "__main__":
    main()
