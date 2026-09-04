"""Cryptographic verification of a dossier — intake's half of the rulebooks.

Eight rules are answered by recomputing hashes and checking Ed25519
signatures against the keystore, and they are answered here rather than in
an agent because they need the submission's canonical bytes, not its typed
view: a signature covers exactly what was signed, and a model dump adds
defaults the file never carried. `LoadedDossier.raw_dossier` / `raw_runs`
hold those bytes' parsed form; a dossier constructed without them cannot be
verified and this module says so rather than verifying a model dump.

    KYA-IDN-01  the credential's signature verifies         ┐
    KYA-IDN-02  its algorithm is on the allowlist            │ dossier-level,
    KYA-IDN-03  its signed_payload_hash recomputes           │ over the whole
    KYA-ACC-03  every delegation-entry signature verifies    │ credential series
    KYA-ISS-01  the issuer is in the trust registry          │
    KYA-ISS-02  the issuer was not revoked at issuance       ┘
    MND-CHN-01  cart.chain_link recomputes to the Intent     ┐ per run
    MND-CHN-02  payment.chain_link recomputes to the Cart    ┘

Every outcome is a `Fact` (migration Phase 1): a signature that does not
verify is a `breach`, one that does is `satisfied`, a run with no cart is
`absent/out_of_scope`. Never raises on a bad signature — a broken submission
comes back as data. A missing signer key counts as signature-does-not-verify,
not an error: an unknown signer is exactly what this is meant to catch.

Separately from the rules, `signature_integrity()` verifies EVERY signed
object in the submission — each run's Intent, Cart and Payment included —
into `EvidencePack.integrity`. The mandate book has no rule for "the mandate
signatures verify" (only for the hash links between them), which is a gap
this phase records rather than papers over; see docs/phases/15.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from data.canonical import canonical_bytes, sha256_hex
from data.issuers import load_issuer_registry
from data.keystore import load_public_keys
from registry.loader import active_rules_by_type, load_kya_ruleset, load_mandate_ruleset
from schemas import EvidenceRef, Fact, FactBuilder, Integrity, Rule, Ruleset, typed_params
from schemas.dossier import LoadedDossier


class RawSubmissionMissing(ValueError):
    """The dossier carries no raw submission to verify against."""


@dataclass
class VerificationContext:
    public_keys: dict[str, Ed25519PublicKey]
    issuers: dict[str, dict]
    kya_rules: dict[str, Rule] = field(default_factory=dict)
    mandate_rules: dict[str, Rule] = field(default_factory=dict)


def build_verification_context(*, kya_ruleset: Ruleset | None = None,
                               mandate_ruleset: Ruleset | None = None,
                               public_keys: dict | None = None,
                               issuers: dict | None = None) -> VerificationContext:
    """Loads keystore, issuers and the active rulebooks once, for reuse."""
    return VerificationContext(
        public_keys=public_keys if public_keys is not None else load_public_keys(),
        issuers=issuers if issuers is not None else load_issuer_registry(),
        kya_rules=active_rules_by_type(kya_ruleset or load_kya_ruleset()),
        mandate_rules=active_rules_by_type(mandate_ruleset or load_mandate_ruleset()),
    )


def _require_raw(d: LoadedDossier) -> None:
    if d.raw_dossier is None:
        raise RawSubmissionMissing(
            f"{d.dossier.dossier_id} carries no raw submission; signatures cover the canonical "
            f"bytes of what was filed, and a model dump is not that")


def verify_signed_object(obj: dict, public_keys: dict[str, Ed25519PublicKey]) -> tuple[bool, bool]:
    """(signature_verifies, hash_recomputes) for one signed object."""
    message = canonical_bytes(obj)
    env = obj.get("signature") or {}
    pub = public_keys.get(env.get("signer_key_id", ""))
    sig_ok = False
    if pub is not None:
        try:
            pub.verify(base64.b64decode(env.get("value", ""), validate=True), message)
            sig_ok = True
        except (InvalidSignature, ValueError, TypeError):
            # malformed base64, wrong-length signature, anything that makes
            # "verify" meaningless rather than false — still a failed
            # verification, not a crash.
            sig_ok = False
    stored = env.get("signed_payload_hash")
    hash_ok = stored is None or stored == f"sha256:{sha256_hex(message)}"
    return sig_ok, hash_ok


def _credential_series(d: LoadedDossier) -> list[dict]:
    raw = d.raw_dossier or {}
    return [raw["kya_credential"], *raw.get("credential_history", [])]


# ---------------------------------------------------------------------------
# the credential — six KYA rules, dossier-level
# ---------------------------------------------------------------------------

def credential_facts(d: LoadedDossier, ctx: VerificationContext, fb: FactBuilder) -> list[Fact]:
    _require_raw(d)
    rules = ctx.kya_rules
    facts: list[Fact] = []
    series = _credential_series(d)
    current = series[0]
    cid = current["credential_id"]
    ref = EvidenceRef(kind="credential_field", ref="kya_credential.signature.signer_key_id",
                      value=current["signature"].get("signer_key_id"))

    if (rule := rules.get("signature_algorithm_allowlist")) is not None:
        allowed = typed_params(rule).allowed_algs
        bad = [c["credential_id"] for c in series if c["signature"].get("alg") not in allowed]
        facts.append(fb.verdict(
            rule, bool(bad),
            f"Credential(s) {', '.join(bad)} use a signature algorithm outside the allowed list "
            f"{allowed}.",
            f"Every credential in the series is signed with an allowed algorithm "
            f"({', '.join(sorted({c['signature'].get('alg', '') for c in series}))}).",
            values={"allowed_algs": allowed, "outside_allowlist": bad}, refs=[ref]))

    results = {c["credential_id"]: verify_signed_object(c, ctx.public_keys) for c in series}
    if (rule := rules.get("signature_must_verify")) is not None:
        bad = [k for k, (sig_ok, _) in results.items() if not sig_ok]
        facts.append(fb.verdict(
            rule, bool(bad),
            f"Credential signature(s) do not verify against the keystore: {', '.join(bad)}.",
            f"Credential {cid}'s signature verifies against signer "
            f"{current['signature'].get('signer_key_id')}"
            + (f", and so do the {len(series) - 1} prior credential(s)." if len(series) > 1 else "."),
            values={"verified": [k for k in results if k not in bad], "failed": bad}, refs=[ref]))
    if (rule := rules.get("payload_hash_must_recompute")) is not None:
        bad = [k for k, (_, hash_ok) in results.items() if not hash_ok]
        facts.append(fb.verdict(
            rule, bool(bad),
            f"Credential signed_payload_hash does not recompute from the canonical content: "
            f"{', '.join(bad)}.",
            "Every credential's signed_payload_hash recomputes from its canonical content.",
            values={"failed": bad}))

    if (rule := rules.get("delegation_entry_signatures_must_verify")) is not None:
        bad = []
        for c in series:
            for entry in c.get("delegation_chain", []):
                sig_ok, _ = verify_signed_object(entry, ctx.public_keys)
                if not sig_ok:
                    bad.append(f"{c['credential_id']} level {entry.get('level')} "
                               f"({entry.get('holder_id')})")
        levels = len(current.get("delegation_chain", []))
        facts.append(fb.verdict(
            rule, bool(bad),
            f"Delegation-chain signature(s) do not verify: {'; '.join(bad)}.",
            f"All {levels} delegation-chain signature(s) on {cid} verify"
            + (" (prior credentials too)." if len(series) > 1 else "."),
            values={"failed": bad, "levels": levels}))

    issuer_id = current["issuer"]["issuer_id"]
    issuer = ctx.issuers.get(issuer_id)
    issuer_ref = EvidenceRef(kind="registry", ref=f"issuers[{issuer_id}]",
                             value=issuer.get("status") if issuer else None)
    if (rule := rules.get("issuer_trust_required")) is not None:
        facts.append(fb.verdict(
            rule, issuer is None,
            f"Issuer {issuer_id} ({current['issuer']['issuer_name']}) is not present in the "
            f"issuer trust registry.",
            f"Issuer {issuer_id} ({current['issuer']['issuer_name']}) is in the trust registry "
            f"(status {issuer['status'] if issuer else ''}).",
            values={"issuer_id": issuer_id, "registered": issuer is not None}, refs=[issuer_ref]))
    if (rule := rules.get("issuer_status_active")) is not None:
        if issuer is None:
            facts.append(fb.absent(
                rule, "no_registry_record",
                f"Issuer {issuer_id} is not in the trust registry (KYA-ISS-01's finding), so its "
                f"revocation status at issuance cannot be read.",
                missing=f"registry:issuers[{issuer_id}]"))
        else:
            revoked_at = issuer.get("revoked_at")
            issued = current["issued_at"][:10]
            revoked_before = (issuer.get("status") == "revoked" and revoked_at is not None
                              and issued >= revoked_at)
            facts.append(fb.verdict(
                rule, revoked_before,
                f"Issuer {issuer_id} was revoked on {revoked_at}; credential {cid} was issued on "
                f"{issued}, on or after revocation.",
                f"Issuer {issuer_id} was {issuer.get('status')} when {cid} was issued on {issued}"
                + (f" (revoked later, on {revoked_at})." if revoked_at else "."),
                values={"issuer_id": issuer_id, "status": issuer.get("status"),
                        "revoked_at": revoked_at, "issued_at": issued}, refs=[issuer_ref]))
    return facts


# ---------------------------------------------------------------------------
# the chain — two Mandate rules, per run
# ---------------------------------------------------------------------------

def chain_link_facts(d: LoadedDossier, ctx: VerificationContext, fb: FactBuilder) -> list[Fact]:
    _require_raw(d)
    rules = ctx.mandate_rules
    cart_rule = rules.get("cart_chain_link_matches_intent")
    pay_rule = rules.get("payment_chain_link_matches_cart")
    sig_rule = rules.get("mandate_signatures_must_verify")
    facts: list[Fact] = []
    for run in d.runs:
        raw = d.raw_runs.get(run.run_id)
        if raw is None:
            raise RawSubmissionMissing(f"{run.run_id}: no raw run file retained")
        intent, cart, payment = raw["intent_mandate"], raw.get("cart"), raw.get("payment")
        if sig_rule is not None:
            bad = []
            for label, obj in (("intent_mandate", intent), ("cart", cart), ("payment", payment)):
                if obj is None:
                    continue
                sig_ok, hash_ok = verify_signed_object(obj, ctx.public_keys)
                if not (sig_ok and hash_ok):
                    bad.append(label)
            facts.append(fb.verdict(
                sig_rule, bool(bad),
                f"{run.run_id}: mandate signature(s) do not verify or recompute: {', '.join(bad)}.",
                f"{run.run_id}: every signed mandate verifies against the keystore.",
                run_ref=run.run_id, values={"failed": bad}))
        if cart_rule is not None:
            if cart is None:
                facts.append(fb.absent(cart_rule, "out_of_scope",
                                       f"{run.run_id} ({run.outcome}) has no cart, so there is "
                                       f"no chain link to the Intent to check.", run_ref=run.run_id))
            else:
                actual = f"sha256:{sha256_hex(canonical_bytes(intent))}"
                declared = cart["chain_link"]["prev_mandate_hash"]
                facts.append(fb.verdict(
                    cart_rule, declared != actual,
                    f"{run.run_id}: cart {cart['cart_mandate_id']} declares prev_mandate_hash "
                    f"{declared[:23]}… but the Intent's canonical hash is {actual[:23]}….",
                    f"{run.run_id}: the cart's chain link recomputes to its Intent.",
                    run_ref=run.run_id, values={"declared": declared, "actual": actual},
                    refs=[EvidenceRef(kind="field", ref="cart.chain_link.prev_mandate_hash",
                                      value=declared)]))
        if pay_rule is not None:
            if payment is None or cart is None:
                facts.append(fb.absent(pay_rule, "out_of_scope",
                                       f"{run.run_id} ({run.outcome}) has no payment, so there is "
                                       f"no chain link to the cart to check.", run_ref=run.run_id))
            else:
                actual = f"sha256:{sha256_hex(canonical_bytes(cart))}"
                declared = payment["chain_link"]["prev_mandate_hash"]
                facts.append(fb.verdict(
                    pay_rule, declared != actual,
                    f"{run.run_id}: payment {payment['payment_mandate_id']} declares "
                    f"prev_mandate_hash {declared[:23]}… but the cart's canonical hash is "
                    f"{actual[:23]}….",
                    f"{run.run_id}: the payment's chain link recomputes to its cart.",
                    run_ref=run.run_id, values={"declared": declared, "actual": actual},
                    refs=[EvidenceRef(kind="field", ref="payment.chain_link.prev_mandate_hash",
                                      value=declared)]))
    return facts


# ---------------------------------------------------------------------------
# every signature in the submission
# ---------------------------------------------------------------------------

def signature_integrity(d: LoadedDossier, ctx: VerificationContext) -> Integrity:
    _require_raw(d)
    checked, failures = 0, []
    for c in _credential_series(d):
        checked += 1
        sig_ok, hash_ok = verify_signed_object(c, ctx.public_keys)
        if not (sig_ok and hash_ok):
            failures.append(f"credential {c['credential_id']}")
        for entry in c.get("delegation_chain", []):
            checked += 1
            if not verify_signed_object(entry, ctx.public_keys)[0]:
                failures.append(f"credential {c['credential_id']} level {entry.get('level')}")
    links_checked, broken = 0, []
    for run in d.runs:
        raw = d.raw_runs[run.run_id]
        for label in ("intent_mandate", "cart", "payment"):
            obj = raw.get(label)
            if obj is None:
                continue
            checked += 1
            sig_ok, hash_ok = verify_signed_object(obj, ctx.public_keys)
            if not (sig_ok and hash_ok):
                failures.append(f"{run.run_id} {label}")
        if raw.get("cart"):
            links_checked += 1
            if raw["cart"]["chain_link"]["prev_mandate_hash"] != \
                    f"sha256:{sha256_hex(canonical_bytes(raw['intent_mandate']))}":
                broken.append(f"{run.run_id} cart->intent")
            if raw.get("payment"):
                links_checked += 1
                if raw["payment"]["chain_link"]["prev_mandate_hash"] != \
                        f"sha256:{sha256_hex(canonical_bytes(raw['cart']))}":
                    broken.append(f"{run.run_id} payment->cart")
    return Integrity(signatures_checked=checked, signature_failures=failures,
                     chain_links_checked=links_checked, chain_links_broken=broken)


def verify_dossier(d: LoadedDossier, context: VerificationContext | None = None
                   ) -> tuple[list[Fact], Integrity]:
    """The eight intake rules as facts, plus the integrity of every signature."""
    ctx = context or build_verification_context()
    facts = [*credential_facts(d, ctx, FactBuilder(d.dossier.dossier_id, "kya")),
             *chain_link_facts(d, ctx, FactBuilder(d.dossier.dossier_id, "mandate"))]
    return facts, signature_integrity(d, ctx)


def credential_facts_with_ruleset(d: LoadedDossier, ruleset: Ruleset, *,
                                  public_keys: dict | None = None,
                                  issuers: dict | None = None) -> list[Fact]:
    """The six credential rules against an arbitrary (e.g. draft) KYA ruleset,
    for agents/kya.py — the specialist re-verifies against whatever book it
    is handed, rather than replaying intake's record."""
    ctx = build_verification_context(kya_ruleset=ruleset, public_keys=public_keys, issuers=issuers)
    return credential_facts(d, ctx, FactBuilder(d.dossier.dossier_id, "kya"))


def chain_facts_with_ruleset(d: LoadedDossier, ruleset: Ruleset, *,
                             public_keys: dict | None = None) -> list[Fact]:
    """The chain-link rules (and the signature rule, once active) against an
    arbitrary Mandate ruleset, for agents/mandate.py."""
    ctx = VerificationContext(
        public_keys=public_keys if public_keys is not None else load_public_keys(),
        issuers={}, mandate_rules=active_rules_by_type(ruleset))
    return chain_link_facts(d, ctx, FactBuilder(d.dossier.dossier_id, "mandate"))
