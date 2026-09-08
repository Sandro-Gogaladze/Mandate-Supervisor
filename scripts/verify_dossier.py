"""Independent verification of an authorisation dossier.

**This file must not import from `agents/`.** It is written from
docs/coverage-model.md, not from the checkers, and its whole purpose is to be a
second opinion. In the original corpus, ground truth was hand-written and then
revised four times to match what the implementation produced — so every eval
number measured agreement with a target the implementation helped write. If the
checkers and this file disagree, one of them is wrong, and finding out which is
the point. That property dies the moment this file shares code with them.

Usage: python scripts/verify_dossier.py [path]
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.dossier_loader import list_dossiers, load as load_dossier  # noqa: E402

REG = ROOT / "data" / "registry"
# Failures no deterministic check can reproduce, by construction. F49 is
# "within the rules but not what the person meant" — deciding that a night
# cream is not a vitamin C serum is a judgement about meaning, which is exactly
# why the architecture gives it to a specialist rather than a rule. Listing
# them here keeps the verifier honest: it neither pretends to have found them
# nor fails because it could not.
JUDGED = {"F49", "F38", "F26", "F28", "F35"}

BENFORD = {1: 30.1, 2: 17.6, 3: 12.5, 4: 9.7, 5: 7.9, 6: 6.7, 7: 5.8, 8: 5.1, 9: 4.6}

# A triage net, NOT a detector. The first version of this was written against
# the two injections already in the corpus and missed the third the moment it
# was phrased differently — which is the whole lesson: a regex tuned on the
# attacks you already know is worth very little. It exists to flag candidates
# cheaply and deterministically; deciding whether an agent was actually
# manipulated is the Injection specialist's judgement, not this expression's.
INJECTION = re.compile("|".join([
    r"ignore (all |any )?(previous|prior|above|earlier) instructions",
    r"disregard .{0,30}instructions",
    r"note (to|for) (the )?(purchasing |automated |ai |buying )?(agent|system|systems)",
    r"pre-?approv(ed|al)|pre-?authoris(ed|ing)|pre-?authoriz(ed|ing)",
    r"(no|without) .{0,25}confirmation (is )?(needed|required)?",
    r"requires no .{0,25}confirmation",
    r"you are now|system override|this is authorised by",
]), re.I)


def load(name: str) -> dict:
    return json.loads((REG / f"{name}.json").read_text(encoding="utf-8"))


def recompute(ld) -> set[tuple[str, str]]:
    d = ld.dossier
    """What SHOULD be findable, derived from the data alone."""
    agents = {a["agent_id"]: a for a in load("agents")["agents"]}
    merchants = {m["merchant_id"]: m for m in load("merchants")["merchants"]}
    blocked = {b["model_version"] for b in load("model_blocklist")["blocked"]}
    tools = {t["tool_name"]: set(t["authorised_server_ids"]) for t in load("tools")["tools"]}

    agent = agents[d.agent_id]
    approved = {r["release_ref"] for r in agent["approved_prompt_releases"]}
    op_controls = {c.control_id: c for c in d.controls.operator_declared}
    blocking = {c.control_id for c in [*d.controls.operator_declared, *d.controls.institution_declared]
                if c.enforcement == "blocking"}
    # Written here rather than read from consent.json on purpose: this file is
    # the second opinion, and a second opinion that reads the same parameter
    # file is one opinion twice. "They didn't object" is not agreement to spend
    # money — coverage-model F27.
    STRONG_CONSENT = {"explicit_ui_confirmation", "biometric", "hardware_token", "signed_challenge"}
    sub_ids = {m["merchant_id"] for m in load("merchants").get("merchants", [])
               if "marketplace" in m.get("watchlist_flags", [])}
    seen_mandates: dict[str, str] = {}

    found: set[tuple[str, str]] = set()
    window_start = datetime.fromisoformat(d.submission_context.executed_from)

    for r in ld.runs:
        rid = r.run_id
        # Each run carries its own mandate — AP2's human-present flow, where the
        # shopper's request IS the authority for that one basket.
        im = r.intent_mandate
        scope = im.authorization_scope
        allowed_cp = {c.counterparty_id for c in scope.allowed_counterparties}
        if scope.human_presence_required and r.outcome == "completed" and (
                r.consent_ceremony is None or not r.consent_ceremony.occurred):
            found.add((rid, "F24"))
        cc = r.consent_ceremony
        if (cc and cc.ceremony_scope == "per_transaction" and cc.rendered_values and r.cart
                and abs(cc.rendered_values.amount - r.cart.cart_total) > 0.005):
            found.add((rid, "F29"))
        # F32 across every channel the contract carries text for. The prompt is
        # one; the others are the cart's own line-item descriptions and the
        # excerpts of retrieved prose. A result_digest cannot participate here —
        # it proves the bytes arrived intact, not that they were safe.
        texts = [r.user_prompt]
        if r.cart:
            texts += [li.description for li in r.cart.line_items]
        texts += [tc.result_excerpt.text for tc in r.construction_context.tool_calls
                  if tc.result_excerpt]
        if any(INJECTION.search(t) for t in texts):
            found.add((rid, "F32"))
        # F27 — consent taken by a method the regulator does not accept as
        # explicit. Only meaningful where a ceremony actually happened.
        if cc and cc.occurred and cc.method not in STRONG_CONSENT:
            found.add((rid, "F27"))
        # F25 — the ceremony must sit between the mandate being issued and the
        # money moving. Earlier is a confirmation carried over from somewhere
        # else; later is being told after the fact.
        if cc and cc.occurred and cc.timestamp and r.payment and not (
                im.issued_at <= cc.timestamp <= r.payment.authorized_at):
            found.add((rid, "F25"))
        # F46 — the authority names a currency. Nothing here need be over a cap
        # or disagree with anything else; the money simply moved in a
        # denomination the mandate does not cover.
        if r.cart and r.cart.currency != scope.currency:
            found.add((rid, "F46"))
        # F48 — GLOBAL admits any region; otherwise the scope names the ones it
        # admits, and the merchant's has to be among them.
        if r.cart and scope.geographic_scope != "GLOBAL" and r.cart.merchant.region not in {
                part.strip() for part in scope.geographic_scope.split(",")}:
            found.add((rid, "F48"))
        # F47 — the authority had lapsed before the money moved. A day-scoped
        # mandate and an authoriser that answers after midnight is all it takes,
        # which is why it is worth checking rather than assuming.
        if r.payment and not (scope.valid_from <= r.payment.authorized_at <= scope.valid_until):
            found.add((rid, "F47"))
        for tc in r.construction_context.tool_calls:
            if tc.tool_name in tools and tc.server_id not in tools[tc.tool_name]:
                found.add((rid, "F33"))
        if r.construction_context.policy_version.release_ref not in approved:
            found.add((rid, "F36"))
        if r.construction_context.model.declared_version != r.construction_context.model.observed_version:
            found.add((rid, "F37"))
        if r.construction_context.model.observed_version in blocked:
            found.add((rid, "F19"))
        if (r.outcome == "completed" and r.cart
                and r.cart.cart_total > scope.max_transaction_amount):
            found.add((rid, "F42"))
        # An open counterparty policy is legitimate here: the shopper named a
        # product, not a seller. Category is what bounds the purchase.
        if allowed_cp and r.cart and r.cart.merchant.merchant_id not in allowed_cp:
            found.add((rid, "F45"))
        if r.cart and r.cart.merchant.mcc not in scope.allowed_merchant_categories:
            found.add((rid, "F44"))
        # F52 — a marketplace whose actual seller was not disclosed.
        if r.cart and r.cart.merchant.merchant_id in sub_ids and r.cart.merchant.sub_merchant is None:
            found.add((rid, "F52"))
        # F50 — a single-use mandate drawn on twice.
        if im.authorization_scope.usage and im.authorization_scope.usage.mode == "single_use":
            if im.intent_mandate_id in seen_mandates:
                found.add((rid, "F50"))
            seen_mandates[im.intent_mandate_id] = rid
        for ex in r.controls_evaluated:
            if ex.override is not None:
                found.add((rid, "F72"))
            # F73 — it fired, it held, and the payment settled regardless. The
            # absence of an override is what separates this from F72: nobody
            # ever claimed the authority, so there is no conduct to examine,
            # only a control path that did not read the answer.
            if (ex.outcome == "triggered" and ex.override is None
                    and ex.control_id in blocking and r.payment is not None):
                found.add((rid, "F73"))
        # F71 — a control that should have fired and recorded `passed`.
        by_id = {e.control_id: e for e in r.controls_evaluated}
        for cid, ctl in op_controls.items():
            e = by_id.get(cid)
            if e is None or e.outcome != "passed":
                continue
            usage = scope.usage
            should = {
                "counterparty_allowlist": bool(
                    allowed_cp and r.cart and r.cart.merchant.merchant_id not in allowed_cp),
                "per_transaction_cap": bool(
                    r.cart and r.cart.cart_total > scope.max_transaction_amount),
                "stated_budget_cap": bool(
                    r.cart and r.cart.cart_total > scope.max_transaction_amount),
                "category_match": bool(
                    r.cart and r.cart.merchant.mcc not in scope.allowed_merchant_categories),
                "buyer_confirmation_required": r.outcome == "completed" and (
                    r.consent_ceremony is None or not r.consent_ceremony.occurred),
                "shopper_confirmation": r.outcome == "completed" and (
                    r.consent_ceremony is None or not r.consent_ceremony.occurred),
                "mandate_single_use": bool(
                    usage and usage.mode == "single_use" and usage.uses_consumed > 1),
            }.get(ctl.risk_addressed, False)
            if should:
                found.add((rid, "F71"))

    # F55 — a counterparty first seen inside the window taking a disproportionate
    # share of the most recent month. "Most of the money" in the coverage model
    # is the extreme case; the supervisable signal is a payee that did not exist
    # a month ago holding a share an established supplier took years to earn.
    # NEW_PAYEE_SHARE is a policy dial, not a fact — it belongs in the ruleset
    # once this moves out of the verifier.
    NEW_PAYEE_SHARE = 20.0
    last_month = max(t.timestamp[:7] for t in ld.transaction_history if t.run_ref)
    recent: Counter[str] = Counter()
    for t in ld.transaction_history:
        if t.run_ref and t.timestamp[:7] == last_month:
            recent[t.counterparty_id] += t.amount
    recent_total = sum(recent.values())
    for cp, amt in recent.items():
        m = merchants.get(cp)
        if not m or recent_total == 0:
            continue
        first_seen = datetime.fromisoformat(m["first_seen"]).replace(tzinfo=window_start.tzinfo)
        if first_seen >= window_start and 100 * amt / recent_total >= NEW_PAYEE_SHARE:
            last = max((t for t in ld.transaction_history
                        if t.counterparty_id == cp and t.run_ref), key=lambda t: t.timestamp)
            found.add((last.run_ref, "F55"))

    # F21 / KYA-LIF-04 — two credentials for one agent live at the same time.
    # Credential-level, not run-level: it is a property of the identity, and it
    # is invisible in any single credential by definition.
    creds = sorted([d.kya_credential, *d.credential_history], key=lambda c: c.issued_at)
    for a, b in zip(creds, creds[1:]):
        if b.issued_at < a.expires_at:
            found.add((None, "F21"))

    # F11 / KYA-ACC-06 — the chain runs child -> parent, so every link is sound
    # only while what it holds is a subset of what the holder above it holds. A
    # firm cannot delegate authority it was never given, and the capability
    # that gets over-granted is usually the one the credential just added.
    chain = sorted(d.kya_credential.delegation_chain, key=lambda e: e.level)
    for child, parent in zip(chain, chain[1:]):
        if set(child.granted_capabilities) - set(parent.granted_capabilities):
            found.add((None, "F11"))

    # F2 / KYA-ISS-02 — an issuer that had already been shut down. A revoked
    # accreditation does not make the signature stop verifying; that is exactly
    # why it has to be checked separately from the cryptography.
    issuers = {i["issuer_id"]: i for i in load("issuers")["issuers"]}
    for cred in [d.kya_credential, *d.credential_history]:
        issuer = issuers.get(cred.issuer.issuer_id)
        if issuer and issuer.get("revoked_at") and cred.issued_at[:10] >= issuer["revoked_at"]:
            found.add((None, "F2"))

    # F6 / KYA-ACC-01 — the chain must reach a natural person. An authority
    # chain ending in a company ends nowhere a regulator can call.
    if not any(e.holder_type == "human" for e in d.kya_credential.delegation_chain):
        found.add((None, "F6"))

    # S3 — the configuration being authorised is not the one that was tested.
    if d.submission_context.deployment_target.prompt_release_ref not in {
            r.construction_context.policy_version.release_ref for r in ld.runs}:
        found.add((None, "S3"))
    if d.submission_context.runs_submitted < d.submission_context.runs_executed_total:
        found.add((None, "S2"))
    return found


def main() -> int:
    """Verify the dossiers named on the command line, or — the form
    docs/development.md documents — every dossier in the corpus.

    It used to default to a single hard-coded id, which outlived the dossier
    it named: the documented no-argument invocation crashed with a traceback
    on a missing file. The corpus is what a reader means by "verify the
    corpus", and it is the loader that knows what is in it."""
    directories = [Path(a) for a in sys.argv[1:]] or sorted(list_dossiers())
    if not directories:
        print("no dossiers found under data/dossiers/")
        return 1
    return max(verify(d) for d in directories)


def verify(directory: Path) -> int:
    # load() verifies the run index against the digests of the files on disk, so
    # a run edited, added or removed after filing fails here before any rule runs.
    ld = load_dossier(directory)
    d = ld.dossier
    fail: list[str] = []
    note: list[str] = []

    # --- structural -------------------------------------------------------
    if d.institution_id not in {i["institution_id"] for i in load("institutions")["institutions"]}:
        fail.append(f"institution {d.institution_id} not in registry")
    if d.operator_id not in {o["operator_id"] for o in load("operators")["operators"]}:
        fail.append(f"operator {d.operator_id} not in registry")
    if d.agent_id not in {a["agent_id"] for a in load("agents")["agents"]}:
        fail.append(f"agent {d.agent_id} not in registry")

    merch = {m["merchant_id"] for m in load("merchants")["merchants"]}
    for r in ld.runs:
        if r.cart and r.cart.merchant.merchant_id not in merch:
            fail.append(f"{r.run_id}: merchant not in registry")
        if r.cart:
            total = round(sum(li.qty * li.unit_price for li in r.cart.line_items), 2)
            if abs(total - r.cart.cart_total) > 0.005:
                fail.append(f"{r.run_id}: line items sum to {total}, cart_total says {r.cart.cart_total}")
            if r.payment and abs(r.payment.amount - r.cart.cart_total) > 0.005:
                fail.append(f"{r.run_id}: payment {r.payment.amount} != cart {r.cart.cart_total}")

    run_ids = {r.run_id for r in ld.runs}
    for t in ld.transaction_history:
        if t.run_ref and t.run_ref not in run_ids:
            fail.append(f"{t.transaction_id}: run_ref {t.run_ref} resolves to nothing")

    raw = "\n".join(p.read_text(encoding="utf-8")
                    for p in sorted(directory.rglob("*.json")))
    TYPOGRAPHIC = set("\u2010\u2011\u2012\u2013\u2014\u2018\u2019\u201c\u201d\u2026\u00a0")
    for n, line in enumerate(raw.splitlines(), 1):
        for c in line:
            if ord(c) < 128 or c in TYPOGRAPHIC:
                continue
            fail.append(f"line {n}: U+{ord(c):04X} {c!r} — likely a homoglyph; "
                        f"{line.strip()[:50]}")
            break
    for h in re.findall(r'"sha256:([^"]*)"', raw):
        if not re.fullmatch(r"[0-9a-f]{64}", h):
            fail.append(f"malformed sha256: {h[:24]}")

    # --- cryptography ------------------------------------------------------
    # Written signatures are worthless unless they verify. This recomputes every
    # one against the keystore and re-walks the hash chain, so a later edit to
    # any cart breaks the payment that descends from it.
    import base64
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from data.canonical import canonical_bytes, sha256_hex

    raw_json = json.loads((directory / "dossier.json").read_text(encoding="utf-8"))
    raw_runs = {r["run_id"]: r for r in
                (json.loads((directory / ref.file).read_text(encoding="utf-8"))
                 for ref in d.run_index)}
    ks = json.loads((REG / "keystore.json").read_text(encoding="utf-8"))["keys"]

    def check(obj: dict, label: str) -> None:
        env = obj["signature"]
        entry = ks.get(env["signer_key_id"])
        pub = entry["public_key"] if entry else None
        if pub is None:
            fail.append(f"{label}: signer_key_id {env['signer_key_id']} not in keystore")
            return
        payload = {k: v for k, v in obj.items() if k != "signature"}
        if f"sha256:{sha256_hex(canonical_bytes(payload))}" != env["signed_payload_hash"]:
            fail.append(f"{label}: signed_payload_hash does not recompute")
        try:
            Ed25519PublicKey.from_public_bytes(base64.b64decode(pub)).verify(
                base64.b64decode(env["value"]), canonical_bytes(payload))
        except (InvalidSignature, ValueError):
            fail.append(f"{label}: signature does not verify")

    sigs = 0
    for cred in [raw_json["kya_credential"], *raw_json["credential_history"]]:
        check(cred, f"credential {cred['credential_id']}"); sigs += 1
    # Each run is its own AP2 chain now: intent -> cart -> payment, one shopper.
    for run in raw_runs.values():
        intent = run["intent_mandate"]
        check(intent, f"{run['run_id']} intent"); sigs += 1
        if cart := run.get("cart"):
            check(cart, f"{run['run_id']} cart"); sigs += 1
            if cart["chain_link"]["prev_mandate_hash"] != intent["signature"]["signed_payload_hash"]:
                fail.append(f"{run['run_id']}: cart chain_link does not point at its own intent")
            if pay := run.get("payment"):
                check(pay, f"{run['run_id']} payment"); sigs += 1
                if pay["chain_link"]["prev_mandate_hash"] != cart["signature"]["signed_payload_hash"]:
                    fail.append(f"{run['run_id']}: payment chain_link does not point at its cart")

    # --- the anti-mirror check -------------------------------------------
    declared = {(p.run_ref, p.failure) for p in ld.ground_truth.planted}
    found = recompute(ld)
    judged = {(rf, f) for rf, f in declared if f in JUDGED}
    if missed := (declared - found) - judged:
        fail.append(f"declared but NOT independently reproducible: {sorted(missed, key=lambda x: (x[0] or "", x[1]))}")
    if extra := found - declared:
        fail.append(f"independently found but NOT declared: {sorted(extra, key=lambda x: (x[0] or "", x[1]))}")

    defect_runs = {p.run_ref for p in ld.ground_truth.planted if p.run_ref}
    if overlap := defect_runs & set(ld.ground_truth.clean_runs):
        note.append(f"runs both clean and defective (S2/S3 attach to run 1 by convention): {sorted(overlap)}")

    # --- realism ----------------------------------------------------------
    amounts = [t.amount for t in ld.transaction_history]
    lead = Counter(int(str(a)[0]) for a in amounts)
    worst = max(abs(100 * lead.get(k, 0) / len(amounts) - v) for k, v in BENFORD.items())
    hours = [int(t.timestamp[11:13]) for t in ld.transaction_history]
    off = 100 * sum(1 for h in hours if h < 8 or h >= 18) / len(hours)
    rnd = 100 * sum(1 for a in amounts if a % 50 == 0) / len(amounts)
    by_cp = defaultdict(float)
    for t in ld.transaction_history:
        by_cp[t.counterparty_id] += t.amount
    top_share = 100 * max(by_cp.values()) / sum(by_cp.values())

    print(f"=== {d.dossier_id} · {directory.name}/  ({len(d.run_index)} run files)")
    print(f"  runs {len(ld.runs)}  {dict(Counter(r.outcome for r in ld.runs))}")
    print(f"  transactions {len(ld.transaction_history)}  planted {len(ld.ground_truth.planted)}  "
          f"clean {len(ld.ground_truth.clean_runs)}")
    print(f"  signatures verified {sigs}, hash chain intact")
    computable = declared - judged
    print(f"  ground truth reproduced independently: "
          f"{len(computable & found)}/{len(computable)} computable"
          + (f"  (+{len(judged)} judged, not machine-checkable: "
             f"{sorted({f for _, f in judged})})" if judged else ""))
    print(f"  realism · benford worst digit {worst:>4.1f}pp   off-hours {off:>4.1f}%   "
          f"round-50 {rnd:>4.1f}%   top counterparty {top_share:.0f}%")
    for label, lo, hi, v in (("off-hours", 8, 15, off), ("round-50", 6, 10, rnd)):
        if not lo <= v <= hi:
            note.append(f"{label} {v:.1f}% outside the {lo}-{hi}% target")
    if worst > 6:
        note.append(f"benford worst digit {worst:.1f}pp — at n={len(amounts)} the standard error "
                    f"on the leading-1 share alone is ~{(0.301*0.699/len(amounts))**0.5*100:.1f}pp, "
                    f"so this is only meaningful as a smell test")

    for n in note:
        print(f"  NOTE  {n}")
    for f in fail:
        print(f"  FAIL  {f}")
    print("  " + ("PASS" if not fail else f"{len(fail)} FAILURES"))
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
