"""Pin the exact policy and rulebooks used by a review in the audit record."""
import json
from data.canonical import canonical_bytes
from pipeline.authorisation import POLICY_PATH
from registry.loader import load_all_rulesets


def snapshot_basis(store):
    policy = json.loads(POLICY_PATH.read_text())
    books = {name: book.model_dump() for name, book in load_all_rulesets().items()}
    return {'policy_version': policy['version'],
            'policy_artifact': store.put_artifact(canonical_bytes(policy, exclude_keys=())),
            'rulebook_artifacts': {name: store.put_artifact(canonical_bytes(book, exclude_keys=())) for name, book in books.items()}}
