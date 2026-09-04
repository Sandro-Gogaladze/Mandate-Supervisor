"""Mandate's deterministic floor: was each run within what its shopper signed?

Every rule here is run-level. In AP2's human-present flow the shopper's
request IS the Intent Mandate for that one shopping task, so the mandate
lives on the run and each run is a complete chain — intent, cart, payment —
checked against itself. One fact per rule per run; fifty runs give fifty
answers to "was the cart within the cap", which is what lets a clean run be
provably clean rather than unmentioned.

Together with the 2 chain-integrity rules ingestion evaluates, this is the
full deterministic floor. The one LLM-judged rule (`MND-SEM-01`, prompt
playback against the shopper's own sentence) is not decided here; `check()`
records the pair the judgement rests on as a `measurement`, so the reasoning
pass's assessment has a fact to cite and the critic has something to check
it against.

Unlike agents/kya_checks.py, most rules carry no ruleset-level params: the
threshold being checked against (max_transaction_amount, allowed merchant
categories, ...) is the run's own Intent, not a regulator policy constant.

A run that never reached a cart (abandoned early, failed) has nothing for
the cart rules to check; those emit `absent/out_of_scope`, not `satisfied` —
a purchase that did not happen did not stay within the cap, it did not
happen. Rules about the mandate itself (`MND-USE-01`, was it drawn on
twice) apply to every run.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from schemas import EvidenceRef, Fact, Rule, Ruleset, typed_params
from schemas.dossier import LoadedDossier, Run

from .facts import FactBuilder, evaluate_ruleset

DOMAIN = "mandate"

# The 2 rule types ingestion/verify.py evaluates (chain-link hash integrity)
# — listed so the dispatcher skips them deliberately rather than by accident.
CHAIN_HANDLED_TYPES = frozenset({
    "cart_chain_link_matches_intent",
    "payment_chain_link_matches_cart",
    "mandate_signatures_must_verify",
})

# Phrase patterns characteristic of an instruction embedded in
# merchant-authored product text, aimed at whoever/whatever processes the
# cart. Deliberately independent of the LLM semantic check (module
# docstring) — kept generic (direct address, false-authorization claims,
# no-confirmation-needed urgency, instruction-override language) rather
# than fitted to any one planted example, so it isn't just a lookup table
# for the attacks already in the corpus.

@dataclass
class MandateContext:
    fb: FactBuilder
    # Settled spend per run, from the institution's ledger — what actually
    # moved, which is what a cumulative cap bounds.
    settled_by_run: dict[str, float] = field(default_factory=dict)
    # Every run drawn on each Intent Mandate, oldest first. In the human-present
    # flow this is one run per intent; a second is F50.
    runs_by_intent: dict[str, list[Run]] = field(default_factory=dict)


def build_policy_context(d: LoadedDossier) -> MandateContext:
    settled: dict[str, float] = defaultdict(float)
    for t in [*d.transaction_history, *d.related_transactions]:
        if t.run_ref and t.status == "settled":
            settled[t.run_ref] += t.amount
    by_intent: dict[str, list[Run]] = defaultdict(list)
    for r in sorted([*d.runs, *d.related_runs], key=lambda r: r.started_at):
        by_intent[r.intent_mandate.intent_mandate_id].append(r)
    return MandateContext(fb=FactBuilder(d.dossier.dossier_id, DOMAIN),
                          settled_by_run=dict(settled), runs_by_intent=dict(by_intent))


def _no_cart(rule: Rule, run: Run, ctx: MandateContext) -> Fact:
    return ctx.fb.absent(
        rule, "out_of_scope",
        f"{run.run_id} ({run.outcome}) never reached a cart, so there is nothing to check "
        f"against the Intent.", run_ref=run.run_id)


def _no_payment(rule: Rule, run: Run, ctx: MandateContext) -> Fact:
    return ctx.fb.absent(
        rule, "out_of_scope",
        f"{run.run_id} ({run.outcome}) authorised no payment, so there is nothing to check "
        f"against the cart or the Intent.", run_ref=run.run_id)


def _cart_ref(run: Run, name: str, value) -> EvidenceRef:
    return EvidenceRef(kind="field", ref=f"cart.{name}", value=value)


def _scope_ref(name: str, value) -> EvidenceRef:
    return EvidenceRef(kind="field", ref=f"intent_mandate.authorization_scope.{name}", value=value)


# ---------------------------------------------------------------------------
# CAP — scope and caps
# ---------------------------------------------------------------------------

def _cap_01(rule, run, ctx):
    if run.cart is None:
        return _no_cart(rule, run, ctx)
    cap = run.intent_mandate.authorization_scope.max_transaction_amount
    total = run.cart.cart_total
    return ctx.fb.verdict(
        rule, total > cap,
        f"{run.run_id}: cart total {total} exceeds the per-transaction cap of {cap} in the "
        f"shopper's Intent by {round(total - cap, 2)}.",
        f"{run.run_id}: cart total {total} is within the per-transaction cap of {cap}.",
        run_ref=run.run_id, values={"cart_total": total, "max_transaction_amount": cap},
        refs=[_cart_ref(run, "cart_total", total), _scope_ref("max_transaction_amount", cap)])


def _cap_02(rule, run, ctx):
    if run.cart is None:
        return _no_cart(rule, run, ctx)
    mcc = run.cart.merchant.mcc
    allowed = run.intent_mandate.authorization_scope.allowed_merchant_categories
    return ctx.fb.verdict(
        rule, mcc not in allowed,
        f"{run.run_id}: merchant {run.cart.merchant.merchant_id} is MCC {mcc!r}, not in the "
        f"categories {allowed} the shopper's request allows.",
        f"{run.run_id}: merchant {run.cart.merchant.merchant_id} (MCC {mcc}) is within the "
        f"allowed categories.",
        run_ref=run.run_id,
        values={"mcc": mcc, "merchant_id": run.cart.merchant.merchant_id,
                "allowed_merchant_categories": allowed},
        refs=[_cart_ref(run, "merchant.mcc", mcc), _scope_ref("allowed_merchant_categories", allowed)])


def _cap_03(rule, run, ctx):
    if run.cart is None:
        return _no_cart(rule, run, ctx)
    scope = run.intent_mandate.authorization_scope
    if not scope.allowed_counterparties:
        # Empty allowlist means category-governed eligibility, not deny-all
        # — see schemas/mandate.py::AuthorizationScope.counterparty_policy.
        return ctx.fb.absent(
            rule, "out_of_scope",
            f"{run.run_id}: the Intent names no counterparty allowlist "
            f"({scope.counterparty_policy or 'category-governed'}); eligibility is decided by "
            f"category (MND-CAP-02).",
            run_ref=run.run_id, values={"counterparty_policy": scope.counterparty_policy})
    merchant_id = run.cart.merchant.merchant_id
    allowed = sorted(c.counterparty_id for c in scope.allowed_counterparties)
    return ctx.fb.verdict(
        rule, merchant_id not in allowed,
        f"{run.run_id}: merchant {merchant_id} is not in the Intent's allowed counterparty list "
        f"{allowed}.",
        f"{run.run_id}: merchant {merchant_id} is on the Intent's allowed counterparty list.",
        run_ref=run.run_id, values={"merchant_id": merchant_id, "allowed_counterparties": allowed},
        refs=[_cart_ref(run, "merchant.merchant_id", merchant_id)])


def _cap_04(rule, run, ctx):
    """F48 — the merchant is in a region the mandate excludes. `GLOBAL`
    admits any region; otherwise the scope names the region(s) allowed."""
    if run.cart is None:
        return _no_cart(rule, run, ctx)
    scope = run.intent_mandate.authorization_scope.geographic_scope
    region = run.cart.merchant.region
    if region is None:
        return ctx.fb.absent(
            rule, "missing_block",
            f"{run.run_id}: merchant {run.cart.merchant.merchant_id} carries no region, so the "
            f"Intent's geographic scope {scope!r} cannot be checked.",
            missing="cart.merchant.region", run_ref=run.run_id, values={"geographic_scope": scope})
    allowed = {s.strip() for s in scope.split(",")} if scope.upper() != "GLOBAL" else None
    outside = allowed is not None and region not in allowed
    return ctx.fb.verdict(
        rule, outside,
        f"{run.run_id}: merchant {run.cart.merchant.merchant_id} is in region {region!r}, outside "
        f"the Intent's geographic scope {scope!r}.",
        f"{run.run_id}: merchant region {region!r} is within the Intent's geographic scope "
        f"{scope!r}.",
        run_ref=run.run_id, values={"region": region, "geographic_scope": scope},
        refs=[_cart_ref(run, "merchant.region", region), _scope_ref("geographic_scope", scope)])


def _use_01(rule, run, ctx):
    """F50 — the same authorisation used twice. A single-use mandate is
    spent by its first run; a second run under the same intent_mandate_id,
    or a uses_consumed past max_uses, is money the shopper authorised once
    and paid twice for."""
    usage = run.intent_mandate.authorization_scope.usage
    intent_id = run.intent_mandate.intent_mandate_id
    if usage is None:
        return ctx.fb.absent(
            rule, "missing_block",
            f"{run.run_id}: the Intent declares no usage mode, so how many times it may be drawn "
            f"on is unstated.", missing="intent_mandate.authorization_scope.usage",
            run_ref=run.run_id)
    earlier = [r.run_id for r in ctx.runs_by_intent.get(intent_id, [])
               if r.started_at < run.started_at and r.run_id != run.run_id]
    over = usage.max_uses is not None and usage.uses_consumed > usage.max_uses
    reused = usage.mode == "single_use" and bool(earlier)
    values = {"mode": usage.mode, "max_uses": usage.max_uses, "uses_consumed": usage.uses_consumed,
              "intent_mandate_id": intent_id, "earlier_draws": earlier}
    refs = [_scope_ref("usage", usage.model_dump()), *[EvidenceRef(kind="run", ref=e) for e in earlier]]
    if reused or over:
        why = []
        if reused:
            why.append(f"already drawn on by {', '.join(earlier)}")
        if over:
            why.append(f"uses_consumed {usage.uses_consumed} exceeds max_uses {usage.max_uses}")
        return ctx.fb.breach(
            rule, f"{run.run_id}: {usage.mode} mandate {intent_id} was {'; '.join(why)}.",
            run_ref=run.run_id, values=values, refs=refs)
    return ctx.fb.satisfied(
        rule, f"{run.run_id}: {usage.mode} mandate {intent_id} is on its "
              f"{'first' if not earlier else 'permitted'} draw ({usage.uses_consumed} of "
              f"{usage.max_uses if usage.max_uses is not None else 'unbounded'}).",
        run_ref=run.run_id, values=values, refs=refs)


def _cap_05(rule, run, ctx):
    """Cumulative spend under THIS mandate, as of this run.

    The cap is a property of the Intent Mandate, so what it bounds is the
    total drawn on that mandate — every settled payment by every run that
    executed under the same `intent_mandate_id`, up to and including this one.
    In the human-present flow that is normally one payment; a second run on
    the same mandate (F50) is exactly when the sum can exceed it.

    The rule's original "calendar month" reading came from a standing
    corporate mandate with a monthly budget. Against single-task consumer
    mandates, where the cumulative cap equals the per-transaction cap, summing
    a month across unrelated tasks would breach on every run — see
    docs/phases/14-facts-and-assessments.md.
    """
    if run.payment is None:
        return _no_payment(rule, run, ctx)
    scope = run.intent_mandate.authorization_scope
    intent_id = run.intent_mandate.intent_mandate_id
    draws = [r for r in ctx.runs_by_intent.get(intent_id, [])
             if r.started_at <= run.started_at and r.payment is not None]
    cumulative = round(sum(ctx.settled_by_run.get(r.run_id, 0.0) for r in draws), 2)
    cap = scope.max_cumulative_amount
    values = {"cumulative_settled": cumulative, "max_cumulative_amount": cap,
              "intent_mandate_id": intent_id, "draws": [r.run_id for r in draws]}
    return ctx.fb.verdict(
        rule, cumulative > cap,
        f"{run.run_id}: settled spend under mandate {intent_id} reaches {cumulative} across "
        f"{len(draws)} run(s), above its cumulative cap of {cap}.",
        f"{run.run_id}: settled spend under mandate {intent_id} is {cumulative}, within its "
        f"cumulative cap of {cap}.",
        run_ref=run.run_id, values=values,
        refs=[EvidenceRef(kind="transaction", ref=r.run_id, value=ctx.settled_by_run.get(r.run_id))
              for r in draws] + [_scope_ref("max_cumulative_amount", cap)])


# ---------------------------------------------------------------------------
# CON / CUR / VAL — internal consistency of the chain
# ---------------------------------------------------------------------------

def _con_01(rule, run, ctx):
    if run.cart is None:
        return _no_cart(rule, run, ctx)
    if run.payment is None:
        return _no_payment(rule, run, ctx)
    tolerance = typed_params(rule).tolerance
    amount, total = run.payment.amount, run.cart.cart_total
    return ctx.fb.verdict(
        rule, abs(amount - total) > tolerance,
        f"{run.run_id}: payment {run.payment.payment_mandate_id} authorises {amount} but the "
        f"signed cart total is {total}.",
        f"{run.run_id}: the payment amount {amount} matches the signed cart total.",
        run_ref=run.run_id,
        values={"payment_amount": amount, "cart_total": total, "tolerance": tolerance},
        refs=[EvidenceRef(kind="field", ref="payment.amount", value=amount),
              _cart_ref(run, "cart_total", total)])


def _cur_01(rule, run, ctx):
    if run.cart is None:
        return _no_cart(rule, run, ctx)
    cart_ccy = run.cart.currency
    scope_ccy = run.intent_mandate.authorization_scope.currency
    return ctx.fb.verdict(
        rule, cart_ccy != scope_ccy,
        f"{run.run_id}: cart currency {cart_ccy!r} does not match the Intent's {scope_ccy!r}.",
        f"{run.run_id}: cart currency {cart_ccy!r} matches the Intent.",
        run_ref=run.run_id, values={"cart_currency": cart_ccy, "scope_currency": scope_ccy})


def _cur_02(rule, run, ctx):
    if run.cart is None:
        return _no_cart(rule, run, ctx)
    if run.payment is None:
        return _no_payment(rule, run, ctx)
    pay_ccy, cart_ccy = run.payment.currency, run.cart.currency
    return ctx.fb.verdict(
        rule, pay_ccy != cart_ccy,
        f"{run.run_id}: payment currency {pay_ccy!r} does not match the cart's {cart_ccy!r}.",
        f"{run.run_id}: payment currency {pay_ccy!r} matches the cart.",
        run_ref=run.run_id, values={"payment_currency": pay_ccy, "cart_currency": cart_ccy})


def _val_01(rule, run, ctx):
    if run.payment is None:
        return _no_payment(rule, run, ctx)
    scope = run.intent_mandate.authorization_scope
    auth = date.fromisoformat(run.payment.authorized_at[:10])
    valid_from = date.fromisoformat(scope.valid_from[:10])
    valid_until = date.fromisoformat(scope.valid_until[:10])
    return ctx.fb.verdict(
        rule, not (valid_from <= auth <= valid_until),
        f"{run.run_id}: payment authorised {auth.isoformat()} falls outside the Intent's validity "
        f"window {valid_from.isoformat()}..{valid_until.isoformat()}.",
        f"{run.run_id}: payment authorised {auth.isoformat()}, inside the Intent's validity "
        f"window {valid_from.isoformat()}..{valid_until.isoformat()}.",
        run_ref=run.run_id,
        values={"authorized_at": auth.isoformat(), "valid_from": valid_from.isoformat(),
                "valid_until": valid_until.isoformat()})


# ---------------------------------------------------------------------------
# SEM — what the cart means
# ---------------------------------------------------------------------------

def _sem_01_measurement(rule, run, ctx):
    """What MND-SEM-01's judgement rests on: the shopper's sentence and what
    the agent bought. Recorded as a measurement so the reasoning pass's
    assessment cites a fact, and so the critic can check the assessment's
    quoted values against what the model was actually shown. The shopper's
    sentence and the line-item text are UNTRUSTED (CLAUDE.md rule 4) — this
    records them as data; delimiting them is the prompt's job."""
    if run.cart is None:
        return []
    items = [{"sku": li.sku, "description": li.description, "qty": li.qty,
              "unit_price": li.unit_price} for li in run.cart.line_items]
    intent = run.intent_mandate.natural_language_intent
    return ctx.fb.measurement(
        "intent_vs_cart",
        f"{run.run_id}: the shopper asked for {intent[:80]!r}; the cart holds {len(items)} "
        f"item(s) from {run.cart.merchant.name} totalling {run.cart.cart_total}.",
        rule=rule, run_ref=run.run_id,
        values={"natural_language_intent": intent, "line_items": items,
                "merchant": run.cart.merchant.name, "cart_total": run.cart.cart_total,
                "agent_reasoning": run.cart.agent_attestation.reasoning},
        refs=[EvidenceRef(kind="field", ref="intent_mandate.natural_language_intent", value=intent),
              *[EvidenceRef(kind="line_item", ref=f"cart.line_items[{i}]", value=it["sku"])
                for i, it in enumerate(items)]])


_RUN_CHECKERS = {
    "cart_total_within_per_transaction_cap": _cap_01,
    "cart_merchant_category_allowed": _cap_02,
    "cart_counterparty_allowed": _cap_03,
    "cart_merchant_geographic_scope_allowed": _cap_04,
    "cumulative_spend_within_monthly_cap": _cap_05,
    "single_use_mandate_not_reused": _use_01,
    "payment_amount_matches_cart_total": _con_01,
    "cart_currency_matches_scope": _cur_01,
    "payment_currency_matches_cart": _cur_02,
    "payment_authorized_within_validity_window": _val_01,
    # judged — check() only records the evidence; the reasoning pass decides
    "cart_reasoning_matches_intent": _sem_01_measurement,
}



def run_policy_checks(dossier: LoadedDossier, ruleset: Ruleset, *,
                      ctx: MandateContext | None = None) -> list[Fact]:
    ctx = ctx or build_policy_context(dossier)
    return evaluate_ruleset(
        ruleset, builder=ctx.fb, ctx=ctx, runs=dossier.runs,
        run_checkers=_RUN_CHECKERS, handled_elsewhere=CHAIN_HANDLED_TYPES,
        module="agents/mandate_checks.py")
