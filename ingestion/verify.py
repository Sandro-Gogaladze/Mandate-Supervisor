"""Deterministic verification — PLAN item 3, first two bullets.

Scope, deliberately narrow:

- Credential signature/issuer verification (KYA domain): the credential's
  own signature + payload hash + algorithm, every delegation-chain entry's
  self-attestation signature, and issuer trust/point-in-time-revocation.
  This is "signature verification against issuer registry" read literally
  — general mandate-signature validity and the rest of KYA's ruleset
  (delegation depth/duplicates/terminus, capabilities, consent) stay with
  the future KYA agent (PLAN item 5), which will reuse this module rather
  than re-implement it.
- Chain-link hash verification (Mandate domain, registry/rulesets/mandate.json):
  Cart's declared hash of Intent, Payment's declared hash of Cart.

Never raises on a broken chain or bad signature — every check failure
becomes a Finding (CLAUDE.md cross-cutting rule 2), returned in a list.
Operates on the *raw* case dict (data.loader.load_raw_case_json), not the
QA-note-stripped Pydantic view — the QA notes were part of what was
actually signed (scripts/sign_corpus.py), so recomputing a hash from the
stripped view would produce a false mismatch.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from data.canonical import canonical_bytes, sha256_hex
from data.issuers import load_issuer_registry
from data.keystore import load_public_keys
from registry.loader import active_rules_by_type, load_kya_ruleset, load_mandate_ruleset
from schemas import Finding, FindingAgent, Rule, Ruleset, typed_params


@dataclass
class VerificationContext:
    public_keys: dict[str, Ed25519PublicKey]
    issuers: dict[str, dict]
    kya_rules: dict[str, Rule]
    mandate_rules: dict[str, Rule]


def build_verification_context() -> VerificationContext:
    """Loads keystore/issuers/rulesets once, for reuse across many cases."""
    return VerificationContext(
        public_keys=load_public_keys(),
        issuers=load_issuer_registry(),
        kya_rules=active_rules_by_type(load_kya_ruleset()),
        mandate_rules=active_rules_by_type(load_mandate_ruleset()),
    )


class _FindingIdCounter:
    def __init__(self, case_id: str) -> None:
        self._case_id = case_id
        self._n = 0

    def next(self) -> str:
        self._n += 1
        return f"{self._case_id}-FND-{self._n:03d}"


def _finding(
    counter: _FindingIdCounter,
    case_id: str,
    agent: FindingAgent,
    rule: Rule,
    summary: str,
    details: dict[str, Any] | None = None,
) -> Finding:
    return Finding(
        finding_id=counter.next(),
        case_id=case_id,
        agent=agent,
        type=rule.finding_type,
        rule_id=rule.rule_id,
        severity_weight=rule.severity_weight,
        summary=summary,
        details=details or {},
    )


def _verify_object_signature(obj: dict, public_keys: dict[str, Ed25519PublicKey]) -> tuple[bool, bool]:
    """(signature_verifies, hash_recomputes) for one signed object. A
    missing signer key counts as signature-does-not-verify, not an error —
    an unknown signer is exactly the kind of thing this is meant to catch."""
    message = canonical_bytes(obj)
    pub = public_keys.get(obj["signature"]["signer_key_id"])
    sig_ok = False
    if pub is not None:
        try:
            signature_bytes = base64.b64decode(obj["signature"]["value"], validate=True)
            pub.verify(signature_bytes, message)
            sig_ok = True
        except (InvalidSignature, ValueError, TypeError):
            # ValueError/TypeError: malformed base64, wrong-length signature,
            # or anything else that makes "verify" meaningless rather than
            # false — still a failed verification, not a crash.
            sig_ok = False

    stored_hash = obj["signature"].get("signed_payload_hash")
    hash_ok = stored_hash is None or stored_hash == f"sha256:{sha256_hex(message)}"
    return sig_ok, hash_ok


def verify_credential(
    raw_case: dict, context: VerificationContext, counter: _FindingIdCounter
) -> list[Finding]:
    findings: list[Finding] = []
    case_id = raw_case["case_id"]
    cred = raw_case["kya_credential"]
    rules = context.kya_rules

    if (alg_rule := rules.get("signature_algorithm_allowlist")) is not None:
        allowed = typed_params(alg_rule).allowed_algs
        if cred["signature"]["alg"] not in allowed:
            findings.append(_finding(
                counter, case_id, "kya", alg_rule,
                f"kya_credential {cred['credential_id']} signature alg "
                f"{cred['signature']['alg']!r} is not in the allowed list {allowed}.",
            ))

    sig_ok, hash_ok = _verify_object_signature(cred, context.public_keys)

    if not sig_ok and (sig_rule := rules.get("signature_must_verify")) is not None:
        findings.append(_finding(
            counter, case_id, "kya", sig_rule,
            f"kya_credential {cred['credential_id']}'s signature does not verify "
            f"against signer {cred['signature']['signer_key_id']}.",
        ))

    if not hash_ok and (hash_rule := rules.get("payload_hash_must_recompute")) is not None:
        findings.append(_finding(
            counter, case_id, "kya", hash_rule,
            f"kya_credential {cred['credential_id']}'s signed_payload_hash does not "
            f"match its recomputed canonical hash.",
        ))

    if (del_rule := rules.get("delegation_entry_signatures_must_verify")) is not None:
        for entry in cred["delegation_chain"]:
            entry_sig_ok, _ = _verify_object_signature(entry, context.public_keys)
            if not entry_sig_ok:
                findings.append(_finding(
                    counter, case_id, "kya", del_rule,
                    f"delegation_chain level {entry['level']} ({entry['holder_id']}) "
                    f"signature does not verify.",
                    details={"level": entry["level"], "holder_id": entry["holder_id"]},
                ))

    issuer_id = cred["issuer"]["issuer_id"]
    issuer = context.issuers.get(issuer_id)

    if issuer is None:
        if (trust_rule := rules.get("issuer_trust_required")) is not None:
            findings.append(_finding(
                counter, case_id, "kya", trust_rule,
                f"Issuer {issuer_id} ({cred['issuer']['issuer_name']}) is not present "
                f"in the issuer trust registry.",
                details={"issuer_id": issuer_id},
            ))
    else:
        revoked_at = issuer.get("revoked_at")
        issued_date = cred["issued_at"][:10]
        if issuer["status"] == "revoked" and revoked_at is not None and issued_date >= revoked_at:
            if (status_rule := rules.get("issuer_status_active")) is not None:
                findings.append(_finding(
                    counter, case_id, "kya", status_rule,
                    f"Issuer {issuer_id} was revoked on {revoked_at}; credential "
                    f"{cred['credential_id']} was issued on {issued_date}, on or after revocation.",
                    details={"issuer_id": issuer_id, "revoked_at": revoked_at, "issued_at": cred["issued_at"]},
                ))

    return findings


def verify_chain_links(
    raw_case: dict, context: VerificationContext, counter: _FindingIdCounter
) -> list[Finding]:
    findings: list[Finding] = []
    case_id = raw_case["case_id"]
    intent = raw_case["mandate_chain"]["intent"]
    cart = raw_case["mandate_chain"]["cart"]
    payment = raw_case["mandate_chain"]["payment"]
    rules = context.mandate_rules

    intent_hash = f"sha256:{sha256_hex(canonical_bytes(intent))}"
    declared = cart["chain_link"]["prev_mandate_hash"]
    if declared != intent_hash and (rule := rules.get("cart_chain_link_matches_intent")) is not None:
        findings.append(_finding(
            counter, case_id, "mandate", rule,
            f"Cart {cart['cart_mandate_id']} declares prev_mandate_hash={declared!r} "
            f"but Intent {intent['intent_mandate_id']}'s actual signed_payload_hash is {intent_hash!r}.",
            details={"declared": declared, "actual": intent_hash},
        ))

    cart_hash = f"sha256:{sha256_hex(canonical_bytes(cart))}"
    declared = payment["chain_link"]["prev_mandate_hash"]
    if declared != cart_hash and (rule := rules.get("payment_chain_link_matches_cart")) is not None:
        findings.append(_finding(
            counter, case_id, "mandate", rule,
            f"Payment {payment['payment_mandate_id']} declares prev_mandate_hash={declared!r} "
            f"but Cart {cart['cart_mandate_id']}'s actual signed_payload_hash is {cart_hash!r}.",
            details={"declared": declared, "actual": cart_hash},
        ))

    return findings


def verify_case(raw_case: dict, context: VerificationContext | None = None) -> list[Finding]:
    context = context or build_verification_context()
    counter = _FindingIdCounter(raw_case["case_id"])
    return verify_credential(raw_case, context, counter) + verify_chain_links(raw_case, context, counter)


def verify_credential_with_ruleset(
    raw_case: dict,
    ruleset: Ruleset,
    *,
    public_keys: dict[str, Ed25519PublicKey] | None = None,
    issuers: dict[str, dict] | None = None,
) -> list[Finding]:
    """Credential verification against an arbitrary (e.g. draft) ruleset,
    for agents/kya.py — not just the active ruleset baked into
    build_verification_context(). Public entry point so callers don't need
    the private _FindingIdCounter."""
    context = VerificationContext(
        public_keys=public_keys if public_keys is not None else load_public_keys(),
        issuers=issuers if issuers is not None else load_issuer_registry(),
        kya_rules=active_rules_by_type(ruleset),
        mandate_rules={},
    )
    counter = _FindingIdCounter(raw_case["case_id"])
    return verify_credential(raw_case, context, counter)


def verify_chain_links_with_ruleset(raw_case: dict, ruleset: Ruleset) -> list[Finding]:
    """Chain-link verification against an arbitrary (e.g. draft) Mandate
    ruleset, for agents/mandate.py."""
    context = VerificationContext(
        public_keys={}, issuers={}, kya_rules={}, mandate_rules=active_rules_by_type(ruleset),
    )
    counter = _FindingIdCounter(raw_case["case_id"])
    return verify_chain_links(raw_case, context, counter)
