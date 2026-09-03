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

from schemas.dossier import Dossier  # noqa: E402

REG = ROOT / "data" / "registry"
BENFORD = {1: 30.1, 2: 17.6, 3: 12.5, 4: 9.7, 5: 7.9, 6: 6.7, 7: 5.8, 8: 5.1, 9: 4.6}

INJECTION = re.compile(
    r"ignore (all )?(previous|prior|above) instructions|disregard .{0,20}instructions"
    r"|you are now|system override|pre-?authoris(ed|e)d all|without buyer confirmation",
    re.I)


def load(name: str) -> dict:
    return json.loads((REG / f"{name}.json").read_text(encoding="utf-8"))


def recompute(d: Dossier) -> set[tuple[str, str]]:
    """What SHOULD be findable, derived from the data alone."""
    agents = {a["agent_id"]: a for a in load("agents")["agents"]}
    merchants = {m["merchant_id"]: m for m in load("merchants")["merchants"]}
    blocked = {b["model_version"] for b in load("model_blocklist")["blocked"]}
    tools = {t["tool_name"]: set(t["authorised_server_ids"]) for t in load("tools")["tools"]}

    agent = agents[d.agent_id]
    approved = {r["release_ref"] for r in agent["approved_prompt_releases"]}
    scope = d.intent_mandate.authorization_scope
    allowed_cp = {c.counterparty_id for c in scope.allowed_counterparties}
    op_controls = {c.control_id: c for c in d.controls.operator_declared}

    found: set[tuple[str, str]] = set()
    window_start = datetime.fromisoformat(d.submission_context.executed_from)

    for r in d.runs:
        rid = r.run_id
        if scope.human_presence_required and r.outcome == "completed" and (
                r.consent_ceremony is None or not r.consent_ceremony.occurred):
            found.add((rid, "F24"))
        cc = r.consent_ceremony
        if (cc and cc.ceremony_scope == "per_transaction" and cc.rendered_values and r.cart
                and abs(cc.rendered_values.amount - r.cart.cart_total) > 0.005):
            found.add((rid, "F29"))
        if INJECTION.search(r.user_prompt):
            found.add((rid, "F32"))
        for tc in r.tool_calls:
            if tc.tool_name in tools and tc.server_id not in tools[tc.tool_name]:
                found.add((rid, "F33"))
        if r.agent_version.release_ref not in approved:
            found.add((rid, "F36"))
        if r.model.declared_version != r.model.observed_version:
            found.add((rid, "F37"))
        if r.model.observed_version in blocked:
            found.add((rid, "F19"))
        if r.cart and r.cart.cart_total > scope.max_transaction_amount:
            found.add((rid, "F42"))
        if r.cart and r.cart.merchant.merchant_id not in allowed_cp:
            found.add((rid, "F45"))
        for ex in r.controls_evaluated:
            if ex.override is not None:
                found.add((rid, "F72"))
        # F71 — a control that should have fired and recorded `passed`.
        by_id = {e.control_id: e for e in r.controls_evaluated}
        for cid, ctl in op_controls.items():
            e = by_id.get(cid)
            if e is None or e.outcome != "passed":
                continue
            should = (
                (ctl.risk_addressed == "counterparty_allowlist" and r.cart
                 and r.cart.merchant.merchant_id not in allowed_cp)
                or (ctl.risk_addressed == "per_transaction_cap" and r.cart
                    and r.cart.cart_total > scope.max_transaction_amount)
                or (ctl.risk_addressed == "buyer_confirmation_required"
                    and r.outcome == "completed"
                    and (r.consent_ceremony is None or not r.consent_ceremony.occurred))
            )
            if should:
                found.add((rid, "F71"))

    # F55 — a counterparty first seen inside the window taking a disproportionate
    # share of the most recent month. "Most of the money" in the coverage model
    # is the extreme case; the supervisable signal is a payee that did not exist
    # a month ago holding a share an established supplier took years to earn.
    # NEW_PAYEE_SHARE is a policy dial, not a fact — it belongs in the ruleset
    # once this moves out of the verifier.
    NEW_PAYEE_SHARE = 20.0
    last_month = max(t.timestamp[:7] for t in d.transaction_history if t.run_ref)
    recent: Counter[str] = Counter()
    for t in d.transaction_history:
        if t.run_ref and t.timestamp[:7] == last_month:
            recent[t.counterparty_id] += t.amount
    recent_total = sum(recent.values())
    for cp, amt in recent.items():
        m = merchants.get(cp)
        if not m or recent_total == 0:
            continue
        first_seen = datetime.fromisoformat(m["first_seen"]).replace(tzinfo=window_start.tzinfo)
        if first_seen >= window_start and 100 * amt / recent_total >= NEW_PAYEE_SHARE:
            last = max((t for t in d.transaction_history
                        if t.counterparty_id == cp and t.run_ref), key=lambda t: t.timestamp)
            found.add((last.run_ref, "F55"))

    # S3 — the configuration being authorised is not the one that was tested.
    if d.submission_context.deployment_target.prompt_release_ref not in {
            r.agent_version.release_ref for r in d.runs}:
        found.add((None, "S3"))
    if d.submission_context.runs_submitted < d.submission_context.runs_executed_total:
        found.add((None, "S2"))
    return found


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/dossiers/DOSSIER-BRL-2026-001.json"
    d = Dossier.model_validate(json.loads(path.read_text(encoding="utf-8")))
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
    for r in d.runs:
        if r.cart and r.cart.merchant.merchant_id not in merch:
            fail.append(f"{r.run_id}: merchant not in registry")
        if r.cart:
            total = round(sum(li.qty * li.unit_price for li in r.cart.line_items), 2)
            if abs(total - r.cart.cart_total) > 0.005:
                fail.append(f"{r.run_id}: line items sum to {total}, cart_total says {r.cart.cart_total}")
            if r.payment and abs(r.payment.amount - r.cart.cart_total) > 0.005:
                fail.append(f"{r.run_id}: payment {r.payment.amount} != cart {r.cart.cart_total}")

    run_ids = {r.run_id for r in d.runs}
    for t in d.transaction_history:
        if t.run_ref and t.run_ref not in run_ids:
            fail.append(f"{t.transaction_id}: run_ref {t.run_ref} resolves to nothing")

    raw = path.read_text(encoding="utf-8")
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

    raw_json = json.loads(path.read_text(encoding="utf-8"))
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
    check(raw_json["intent_mandate"], "intent"); sigs += 1
    intent_hash = raw_json["intent_mandate"]["signature"]["signed_payload_hash"]
    for run in raw_json["runs"]:
        if cart := run.get("cart"):
            check(cart, f"{run['run_id']} cart"); sigs += 1
            if cart["chain_link"]["prev_mandate_hash"] != intent_hash:
                fail.append(f"{run['run_id']}: cart chain_link does not point at the intent")
            if pay := run.get("payment"):
                check(pay, f"{run['run_id']} payment"); sigs += 1
                if pay["chain_link"]["prev_mandate_hash"] != cart["signature"]["signed_payload_hash"]:
                    fail.append(f"{run['run_id']}: payment chain_link does not point at its cart")

    # --- the anti-mirror check -------------------------------------------
    declared = {(p.run_ref, p.failure) for p in d.ground_truth.planted}
    found = recompute(d)
    if missed := declared - found:
        fail.append(f"declared but NOT independently reproducible: {sorted(missed)}")
    if extra := found - declared:
        fail.append(f"independently found but NOT declared: {sorted(extra)}")

    defect_runs = {p.run_ref for p in d.ground_truth.planted if p.run_ref}
    if overlap := defect_runs & set(d.ground_truth.clean_runs):
        note.append(f"runs both clean and defective (S2/S3 attach to run 1 by convention): {sorted(overlap)}")

    # --- realism ----------------------------------------------------------
    amounts = [t.amount for t in d.transaction_history]
    lead = Counter(int(str(a)[0]) for a in amounts)
    worst = max(abs(100 * lead.get(k, 0) / len(amounts) - v) for k, v in BENFORD.items())
    hours = [int(t.timestamp[11:13]) for t in d.transaction_history]
    off = 100 * sum(1 for h in hours if h < 8 or h >= 18) / len(hours)
    rnd = 100 * sum(1 for a in amounts if a % 50 == 0) / len(amounts)
    by_cp = defaultdict(float)
    for t in d.transaction_history:
        by_cp[t.counterparty_id] += t.amount
    top_share = 100 * max(by_cp.values()) / sum(by_cp.values())

    print(f"=== {d.dossier_id} · {path.name}")
    print(f"  runs {len(d.runs)}  {dict(Counter(r.outcome for r in d.runs))}")
    print(f"  transactions {len(d.transaction_history)}  planted {len(d.ground_truth.planted)}  "
          f"clean {len(d.ground_truth.clean_runs)}")
    print(f"  signatures verified {sigs}, hash chain intact")
    print(f"  ground truth reproduced independently: {len(declared & found)}/{len(declared)}")
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
