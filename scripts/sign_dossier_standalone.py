"""Sign ONE dossier without re-minting the keys the rest of the corpus uses.

`scripts/sign_corpus.py` signs everything in one pass with a fresh keyring, which
is right for the curated corpus and wrong for a dossier that arrives on its own:
re-minting a `signer_key_id` that other dossiers already use leaves THEIR
signatures unverifiable, and — worse — leaves the copies already filed in the
ledger unverifiable, with nothing on disk to show it happened.

So this mints a keypair only for signer ids the keystore does not already have,
and refuses outright if the dossier would need to re-sign an id that is already
in use. Refusing is the point: there is no way to sign under an existing id
without the private key, which is never persisted, so the only safe answer is
to give the new dossier its own identities.

Usage: python scripts/sign_dossier_standalone.py <dossier-dir>
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from data.keystore import KEYSTORE_PATH  # noqa: E402
from sign_dossier import sign_dossier_dir  # noqa: E402


def signer_ids(directory: Path) -> set[str]:
    """Every signer_key_id anywhere in the dossier, found structurally."""
    found: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            if "signer_key_id" in node:
                found.add(node["signer_key_id"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for path in sorted(directory.rglob("*.json")):
        if path.name != "ground_truth.json":
            walk(json.loads(path.read_text(encoding="utf-8")))
    return found


class AdditiveKeyRing:
    """Mints only what is missing, and will not shadow an id already in use."""

    def __init__(self, existing: set[str]) -> None:
        self._existing = existing
        self._private: dict[str, Ed25519PrivateKey] = {}

    def private_key_for(self, signer_key_id: str) -> Ed25519PrivateKey:
        if signer_key_id in self._existing:
            raise SystemExit(
                f"{signer_key_id} is already in the keystore and its private key was never "
                f"persisted. Signing under it would mint a new keypair and silently break "
                f"every signature the rest of the corpus made with that id. Give this dossier "
                f"its own signer identity instead."
            )
        if signer_key_id not in self._private:
            self._private[signer_key_id] = Ed25519PrivateKey.generate()
        return self._private[signer_key_id]


def ids_used_elsewhere(directory: Path) -> set[str]:
    """Signer ids any OTHER dossier depends on.

    A key already in the keystore is not automatically off limits: re-signing
    this same dossier after an edit is routine, and its own ids are its own to
    re-mint. What must never be re-minted is an id another dossier's signatures
    — or the copy of them already filed in the ledger — still verify against.
    """
    others = set()
    for sibling in sorted(directory.parent.iterdir()):
        if sibling.is_dir() and sibling != directory and (sibling / "dossier.json").exists():
            others |= signer_ids(sibling)
    return others


def main(directory: Path) -> None:
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    store = json.loads(KEYSTORE_PATH.read_text(encoding="utf-8"))
    shared = ids_used_elsewhere(directory)
    if clash := signer_ids(directory) & shared:
        raise SystemExit(
            f"these signer ids are also used by another dossier: {sorted(clash)}. "
            f"Re-minting them would break its signatures. Give this dossier its own.")

    # Its own ids may be reissued; everyone else's are frozen.
    existing = set(store["keys"]) - signer_ids(directory)
    keyring = AdditiveKeyRing(existing)
    carts, payments = sign_dossier_dir(directory, keyring)

    for key_id, private in sorted(keyring._private.items()):
        store["keys"][key_id] = {
            "alg": "Ed25519",
            "public_key": base64.b64encode(
                private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode("ascii"),
        }
    store["keys"] = dict(sorted(store["keys"].items()))
    KEYSTORE_PATH.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")
    print(f"Signed {directory.name}: {carts} carts, {payments} payments, index rebuilt.")
    print(f"Wrote {len(keyring._private)} public keys; {len(existing)} left untouched.")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
