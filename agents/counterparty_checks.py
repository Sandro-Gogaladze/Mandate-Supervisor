"""Deterministic checkers for the Counterparty specialist (C1).

Who received this money? We verify the payer exhaustively and, until this
module, the payee not at all. Everything here reads `payment.payee`,
`cart.merchant` and the regulator's merchant register, which holds what the
paying firm cannot supply — ownership, first-seen, watchlist flags.

Per-run rules ask about one payment; dossier-level rules ask about the payee
set — ownership is a property of the payee, and pricing every run that paid
an unresolved owner as a breach would blame the runs for the register.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from data.registries import load_merchants
from schemas import EvidenceRef, Fact, FactBuilder, Rule, Ruleset, typed_params
from schemas.dossier import LoadedDossier, Run

from .facts import evaluate_ruleset
from .log_stats import new_payee_concentration, to_dataframe

DOMAIN = "counterparty"


@dataclass
class CounterpartyContext:
    fb: FactBuilder
    dossier: LoadedDossier
    merchants: dict[str, dict]
    # merchant_id -> runs that paid it, oldest first
    runs_by_payee: dict[str, list[Run]] = field(default_factory=dict)


def build_context(d: LoadedDossier, *, merchants: dict | None = None) -> CounterpartyContext:
    by_payee: dict[str, list[Run]] = defaultdict(list)
    for r in sorted(d.runs, key=lambda r: r.started_at):
        if r.cart is not None and r.payment is not None:
            by_payee[r.cart.merchant.merchant_id].append(r)
    return CounterpartyContext(fb=FactBuilder(d.dossier.dossier_id, DOMAIN), dossier=d,
                               merchants=dict(merchants if merchants is not None else load_merchants()),
                               runs_by_payee=dict(by_payee))


def _no_cart(rule, run, ctx) -> Fact:
    return ctx.fb.absent(rule, "out_of_scope", f"{run.run_id} ({run.outcome}) paid nobody.",
                         run_ref=run.run_id)


def _unregistered(rule, run, ctx, merchant_id: str) -> Fact:
    return ctx.fb.absent(
        rule, "no_registry_record",
        f"{run.run_id}: merchant {merchant_id} is not on the register (CPT-REG-01's finding), so "
        f"{rule.rule_id} has no record to read.", missing=f"registry:merchants[{merchant_id}]",
        run_ref=run.run_id)


def _is_marketplace(record: dict) -> bool:
    return "marketplace" in record.get("watchlist_flags", []) or bool(record.get("parent_platform_id"))


def _norm(name: str | None) -> str:
    return " ".join((name or "").lower().split())


# --- per run -------------------------------------------------------------------

def _reg_01(rule, run, ctx):
    """F51 — nobody knows who was paid."""
    if run.cart is None:
        return _no_cart(rule, run, ctx)
    mid = run.cart.merchant.merchant_id
    record = ctx.merchants.get(mid)
    return ctx.fb.verdict(
        rule, record is None,
        f"{run.run_id}: merchant {mid} ({run.cart.merchant.name}) appears in no register — nobody "
        f"knows who was paid.",
        f"{run.run_id}: merchant {mid} is on the register as {record['legal_name'] if record else ''}.",
        run_ref=run.run_id, values={"merchant_id": mid, "registered": record is not None},
        refs=[EvidenceRef(kind="registry", ref=f"merchants[{mid}]", value=record is not None)])


def _sub_01(rule, run, ctx):
    """F52 — a platform is hiding who actually sold the goods."""
    if run.cart is None:
        return _no_cart(rule, run, ctx)
    mid = run.cart.merchant.merchant_id
    record = ctx.merchants.get(mid)
    if record is None:
        return _unregistered(rule, run, ctx, mid)
    marketplace = _is_marketplace(record)
    disclosed = run.cart.merchant.sub_merchant
    if not marketplace:
        return ctx.fb.satisfied(rule, f"{run.run_id}: {mid} is a direct merchant, not a marketplace.",
                                run_ref=run.run_id, values={"marketplace": False})
    return ctx.fb.verdict(
        rule, disclosed is None,
        f"{run.run_id}: {record['legal_name']} is a marketplace and the cart discloses no sub-merchant "
        f"— every check ran against the platform's identity while the real seller is invisible.",
        f"{run.run_id}: marketplace {record['legal_name']} discloses sub-merchant "
        f"{disclosed.legal_name if disclosed else ''} ({disclosed.relationship if disclosed else ''}).",
        run_ref=run.run_id,
        values={"marketplace": True, "sub_merchant": disclosed.model_dump() if disclosed else None},
        refs=[EvidenceRef(kind="field", ref="cart.merchant.sub_merchant",
                          value=disclosed.id if disclosed else None)])


def _cop_01(rule, run, ctx):
    """Confirmation of Payee — the name on the account is the merchant's."""
    if run.payment is None:
        return _no_cart(rule, run, ctx)
    payee = run.payment.payee
    if payee is None:
        return ctx.fb.absent(rule, "missing_block", f"{run.run_id}: the payment records no payee.",
                             missing="payment.payee", run_ref=run.run_id)
    if not payee.beneficiary_name_on_account:
        return ctx.fb.absent(rule, "missing_block",
                             f"{run.run_id}: the payee carries no beneficiary name to confirm.",
                             missing="payment.payee.beneficiary_name_on_account", run_ref=run.run_id)
    mid = run.cart.merchant.merchant_id
    record = ctx.merchants.get(mid, {})
    accepted = {_norm(run.cart.merchant.name), _norm(record.get("legal_name")),
                _norm(record.get("trading_name"))} - {""}
    matches = _norm(payee.beneficiary_name_on_account) in accepted
    return ctx.fb.verdict(
        rule, not matches,
        f"{run.run_id}: the settlement account is in the name {payee.beneficiary_name_on_account!r}, "
        f"not the merchant's ({run.cart.merchant.name!r}).",
        f"{run.run_id}: the account name {payee.beneficiary_name_on_account!r} is the merchant's.",
        run_ref=run.run_id,
        values={"beneficiary_name_on_account": payee.beneficiary_name_on_account,
                "merchant_name": run.cart.merchant.name, "registered_legal_name": record.get("legal_name")},
        refs=[EvidenceRef(kind="field", ref="payment.payee.beneficiary_name_on_account",
                          value=payee.beneficiary_name_on_account)])


def _cty_01(rule, run, ctx):
    if run.payment is None:
        return _no_cart(rule, run, ctx)
    payee = run.payment.payee
    if payee is None:
        return ctx.fb.absent(rule, "missing_block", f"{run.run_id}: the payment records no payee.",
                             missing="payment.payee", run_ref=run.run_id)
    return ctx.fb.verdict(
        rule, payee.country != run.cart.merchant.country,
        f"{run.run_id}: the money settled in {payee.country}; the merchant is in "
        f"{run.cart.merchant.country}.",
        f"{run.run_id}: settled in {payee.country}, the merchant's country.",
        run_ref=run.run_id, values={"payee_country": payee.country,
                                    "merchant_country": run.cart.merchant.country})


def _lst_01(rule, run, ctx):
    """F54 — the recipient is on a list they shouldn't be paid from."""
    if run.cart is None:
        return _no_cart(rule, run, ctx)
    mid = run.cart.merchant.merchant_id
    record = ctx.merchants.get(mid)
    if record is None:
        return _unregistered(rule, run, ctx, mid)
    barring = set(typed_params(rule).barring_flags)
    hits = sorted(barring & set(record.get("watchlist_flags", [])))
    return ctx.fb.verdict(
        rule, bool(hits),
        f"{run.run_id}: merchant {mid} carries barring flag(s) {hits} — a payment a human would have "
        f"had screened.",
        f"{run.run_id}: merchant {mid} carries no barring flag"
        + (f" (informational flags: {', '.join(record.get('watchlist_flags', []))})."
           if record.get("watchlist_flags") else "."),
        run_ref=run.run_id, values={"flags": record.get("watchlist_flags", []), "barring": hits})


# --- the payee set ---------------------------------------------------------------

def _in_window_spend(ctx) -> dict[str, float]:
    spend: dict[str, float] = defaultdict(float)
    for t in ctx.dossier.transaction_history:
        if t.run_ref and t.status == "settled":
            spend[t.counterparty_id] += t.amount
    return dict(spend)


def _ben_01(rule, ctx):
    """F53 — the money went to a wallet with no identifiable owner."""
    spend = _in_window_spend(ctx)
    total = sum(spend.values()) or 1.0
    unresolved = []
    for mid, runs in ctx.runs_by_payee.items():
        record = ctx.merchants.get(mid)
        if record is None:
            continue  # CPT-REG-01's finding
        if record.get("beneficial_owner") is None or "beneficial_owner_unresolved" in record.get("watchlist_flags", []):
            unresolved.append({"merchant_id": mid, "legal_name": record.get("legal_name"),
                               "share_pct": round(100 * spend.get(mid, 0.0) / total, 1),
                               "runs": [r.run_id for r in runs]})
    return ctx.fb.verdict(
        rule, bool(unresolved),
        f"{len(unresolved)} payee(s) have no identifiable beneficial owner on the register: "
        + "; ".join(f"{u['legal_name']} ({u['share_pct']}% of in-window spend, {len(u['runs'])} run(s))"
                    for u in unresolved) + ".",
        f"Every one of the {len(ctx.runs_by_payee)} payees paid in the window has an identifiable owner.",
        values={"unresolved": unresolved, "payees": len(ctx.runs_by_payee)},
        refs=[EvidenceRef(kind="registry", ref=f"merchants[{u['merchant_id']}].beneficial_owner", value=None)
              for u in unresolved])


def _new_01(rule, ctx):
    """F55 — a brand-new recipient is suddenly getting most of the money.
    One fact per qualifying payee, attached to the latest run that paid it."""
    d = ctx.dossier
    if not d.transaction_history:
        return ctx.fb.absent(rule, "insufficient_history", "No transaction history to profile by month.",
                             missing="transaction_history")
    dial = typed_params(rule).new_payee_min_share_pct
    npc = new_payee_concentration(to_dataframe(d.transaction_history), merchants=ctx.merchants,
                                  window_start=d.dossier.submission_context.executed_from)
    qualifying = [c for c in npc["counterparties"] if c["new_in_window"] and c["share_pct"] >= dial]
    if not qualifying:
        return ctx.fb.satisfied(
            rule, f"No payee first seen inside the window holds {dial}% or more of {npc['latest_month']}'s "
                  f"spend.", values={"latest_month": npc["latest_month"], "dial": dial,
                                     "top": npc["counterparties"][:3]})
    facts = []
    for c in qualifying:
        runs = ctx.runs_by_payee.get(c["counterparty_id"], [])
        latest = runs[-1].run_id if runs else None
        facts.append(ctx.fb.breach(
            rule, f"{c['counterparty_name']} ({c['counterparty_id']}), first seen "
                  f"{c['registry_first_seen']} — inside the review window — took {c['share_pct']}% of "
                  f"{npc['latest_month']}'s spend across {len(runs)} run(s).",
            run_ref=latest,
            values={**c, "latest_month": npc["latest_month"], "dial": dial,
                    "runs": [r.run_id for r in runs]},
            refs=[EvidenceRef(kind="registry", ref=f"merchants[{c['counterparty_id']}].first_seen",
                              value=c["registry_first_seen"]),
                  *[EvidenceRef(kind="run", ref=r.run_id) for r in runs]]))
    return facts


def _spl_01(rule, ctx):
    """F56 — one recipient masquerading as several."""
    by_account: dict[tuple, set[str]] = defaultdict(set)
    by_owner: dict[str, set[str]] = defaultdict(set)
    for mid, runs in ctx.runs_by_payee.items():
        for r in runs:
            p = r.payment.payee
            if p is not None:
                by_account[(_norm(p.beneficiary_name_on_account), p.settlement_account_masked)].add(mid)
        owner = (ctx.merchants.get(mid) or {}).get("beneficial_owner")
        if owner and owner != "platform":
            by_owner[owner].add(mid)
    shared_accounts = [{"account": k[1], "name": k[0], "merchants": sorted(v)}
                       for k, v in by_account.items() if len(v) > 1]
    shared_owners = [{"beneficial_owner": o, "merchants": sorted(v)} for o, v in by_owner.items() if len(v) > 1]
    return ctx.fb.verdict(
        rule, bool(shared_accounts or shared_owners),
        f"Payees that are one recipient under several ids: "
        + "; ".join([*(f"account {s['account']} serves {', '.join(s['merchants'])}" for s in shared_accounts),
                     *(f"{s['beneficial_owner']} owns {', '.join(s['merchants'])}" for s in shared_owners)]) + ".",
        f"No two of the {len(ctx.runs_by_payee)} payees share a settlement account or a beneficial owner.",
        values={"shared_accounts": shared_accounts, "shared_owners": shared_owners})


def _dcl_01(rule, ctx):
    """F58's evidence: declines and reversals per counterparty, in order."""
    txns = sorted(ctx.dossier.transaction_history, key=lambda t: t.timestamp)
    if not txns:
        return ctx.fb.absent(rule, "insufficient_history", "No transaction history.", missing="transaction_history")
    by_cp: dict[str, list] = defaultdict(list)
    for t in txns:
        by_cp[t.counterparty_id].append((t.timestamp, t.status, t.amount, t.transaction_id))
    profiles = []
    for cp, rows in by_cp.items():
        failures = [r for r in rows if r[1] != "settled"]
        if not failures:
            continue
        # a failure streak followed by a success is the shape worth judging
        streaks = 0
        run_len = 0
        for _, status, _, _ in rows:
            if status != "settled":
                run_len += 1
            else:
                if run_len:
                    streaks += 1
                run_len = 0
        profiles.append({"counterparty_id": cp, "transactions": len(rows), "failures": len(failures),
                         "failure_then_success_streaks": streaks,
                         "sequence": [{"at": a, "status": s, "amount": m, "id": i} for a, s, m, i in rows]})
    total_failures = sum(1 for t in txns if t.status != "settled")
    return ctx.fb.measurement(
        "decline_timeline",
        f"{total_failures} declined/reversed transaction(s) across {len(profiles)} counterpart(ies).",
        rule=rule, values={"total_failures": total_failures, "counterparties": profiles})


def _idn_01(rule, ctx):
    """CPT-IDN-01's evidence: one profile per payee, the four things that
    should agree — registered name, account name, ownership, geography."""
    spend = _in_window_spend(ctx)
    total = sum(spend.values()) or 1.0
    profiles = []
    for mid, runs in ctx.runs_by_payee.items():
        record = ctx.merchants.get(mid) or {}
        payees = [r.payment.payee for r in runs if r.payment and r.payment.payee]
        profiles.append({
            "merchant_id": mid, "registered": bool(record),
            "legal_name": record.get("legal_name"), "cart_names": sorted({r.cart.merchant.name for r in runs}),
            "account_names": sorted({p.beneficiary_name_on_account for p in payees if p.beneficiary_name_on_account}),
            "settlement_accounts": sorted({p.settlement_account_masked for p in payees}),
            "beneficial_owner": record.get("beneficial_owner"), "first_seen": record.get("first_seen"),
            "watchlist_flags": record.get("watchlist_flags", []),
            "merchant_country": sorted({r.cart.merchant.country for r in runs}),
            "payee_countries": sorted({p.country for p in payees}),
            "sub_merchants": sorted({r.cart.merchant.sub_merchant.legal_name for r in runs if r.cart.merchant.sub_merchant}),
            "share_pct": round(100 * spend.get(mid, 0.0) / total, 1), "runs": [r.run_id for r in runs],
        })
    profiles.sort(key=lambda p: -p["share_pct"])
    return ctx.fb.measurement(
        "payee_profiles", f"{len(profiles)} payee(s) paid in the window, profiled against the register.",
        rule=rule, values={"payees": profiles})


_RUN_CHECKERS = {
    "payee_in_merchant_register": _reg_01,
    "marketplace_discloses_sub_merchant": _sub_01,
    "beneficiary_name_matches_merchant": _cop_01,
    "payee_country_matches_merchant": _cty_01,
    "payee_not_on_a_barring_list": _lst_01,
}

_DOSSIER_CHECKERS = {
    "payees_have_identifiable_owners": _ben_01,
    "new_payee_concentration": _new_01,
    "payees_not_split_identities": _spl_01,
    "declines_not_clustered": _dcl_01,
    "payee_is_what_it_appears": _idn_01,
}


def run_counterparty_checks(dossier: LoadedDossier, ruleset: Ruleset, *,
                            ctx: CounterpartyContext | None = None) -> list[Fact]:
    ctx = ctx or build_context(dossier)
    return evaluate_ruleset(ruleset, builder=ctx.fb, ctx=ctx, runs=dossier.runs,
                            dossier_checkers=_DOSSIER_CHECKERS, run_checkers=_RUN_CHECKERS,
                            module="agents/counterparty_checks.py")
