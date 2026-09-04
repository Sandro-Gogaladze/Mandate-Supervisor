"""Deterministic checkers for the Consent & Harm specialist (C2).

Was the human there, and is the consumer worse off? Everything here reads
`consent_ceremony` — SCA evidence the institution already holds — against the
signed chain. All rules are run-level: a ceremony belongs to a run.

The highest-value pair in the schema is `rendered_values` against the signed
cart (F29): the screen said $54.99, the signature covers $329, and every
other check passes because the fraud happened between the screen and the
signature. The one judged rule, value-for-money (F38), gets a measurement per
run: the selected price against the alternatives the agent considered; the
verdict is the model's, because whether a cheaper option was *equivalent* is
not a comparison a rule can make.
"""
from __future__ import annotations

from dataclasses import dataclass

from schemas import EvidenceRef, Fact, FactBuilder, Rule, Ruleset, typed_params
from schemas.dossier import LoadedDossier, Run

from .facts import evaluate_ruleset

DOMAIN = "consent"


@dataclass
class ConsentContext:
    fb: FactBuilder


def build_context(d: LoadedDossier) -> ConsentContext:
    return ConsentContext(fb=FactBuilder(d.dossier.dossier_id, DOMAIN))


def _no_ceremony(rule: Rule, run: Run, ctx: ConsentContext) -> Fact:
    return ctx.fb.absent(
        rule, "out_of_scope",
        f"{run.run_id} carries no consent ceremony (CNS-REC-01's fact), so {rule.rule_id} has "
        f"nothing to read.", run_ref=run.run_id)


def _not_completed(rule: Rule, run: Run, ctx: ConsentContext) -> Fact:
    return ctx.fb.absent(
        rule, "out_of_scope",
        f"{run.run_id} ({run.outcome}) authorised no payment; {rule.rule_id} concerns the act.",
        run_ref=run.run_id)


def _ref(path: str, value) -> EvidenceRef:
    return EvidenceRef(kind="field", ref=path, value=value)


# --- presence and record ---------------------------------------------------

def _prs_01(rule, run, ctx):
    """F24 — a human was required to be present and wasn't."""
    if run.outcome != "completed":
        return _not_completed(rule, run, ctx)
    required = run.intent_mandate.authorization_scope.human_presence_required
    cc = run.consent_ceremony
    present = bool(cc and cc.occurred)
    if not required:
        return ctx.fb.satisfied(
            rule, f"{run.run_id}: the Intent does not require the shopper present"
                  + ("; a ceremony occurred anyway." if present else "."),
            run_ref=run.run_id, values={"required": False, "occurred": present})
    return ctx.fb.verdict(
        rule, not present,
        f"{run.run_id}: the Intent requires the shopper present and the run completed with "
        + ("no consent ceremony recorded." if cc is None else "a ceremony that did not occur."),
        f"{run.run_id}: the shopper was present — a ceremony occurred at {cc.timestamp if cc else ''}.",
        run_ref=run.run_id, values={"required": True, "occurred": present,
                                    "ceremony_recorded": cc is not None},
        refs=[_ref("intent_mandate.authorization_scope.human_presence_required", required),
              _ref("consent_ceremony.occurred", cc.occurred if cc else None)])


def _rec_01(rule, run, ctx):
    """F31 — no record that a human was ever involved. The block's absence is
    the fact, and it rolls up into the data-gap finding."""
    if run.outcome != "completed":
        return _not_completed(rule, run, ctx)
    if run.consent_ceremony is None:
        return ctx.fb.absent(
            rule, "missing_block",
            f"{run.run_id} completed with no consent_ceremony block at all — no record that a "
            f"human was ever involved.", missing="consent_ceremony", run_ref=run.run_id)
    return ctx.fb.satisfied(rule, f"{run.run_id}: a consent record is present.", run_ref=run.run_id)


def _prn_01(rule, run, ctx):
    cc = run.consent_ceremony
    if cc is None:
        return _no_ceremony(rule, run, ctx)
    if not cc.principal_id:
        return ctx.fb.absent(rule, "missing_block",
                             f"{run.run_id}: the ceremony names no principal.",
                             missing="consent_ceremony.principal_id", run_ref=run.run_id)
    signer = run.intent_mandate.principal.principal_id
    return ctx.fb.verdict(
        rule, cc.principal_id != signer,
        f"{run.run_id}: the ceremony records {cc.principal_id!r} but the Intent was signed by "
        f"{signer!r}.",
        f"{run.run_id}: the shopper who confirmed ({signer}) is the shopper who signed.",
        run_ref=run.run_id, values={"ceremony_principal": cc.principal_id, "intent_principal": signer})


def _mth_01(rule, run, ctx):
    """F27 — consent obtained in a way that isn't strong enough."""
    cc = run.consent_ceremony
    if cc is None:
        return _no_ceremony(rule, run, ctx)
    if not cc.method:
        return ctx.fb.absent(rule, "missing_block", f"{run.run_id}: the ceremony records no method.",
                             missing="consent_ceremony.method", run_ref=run.run_id)
    allowed = typed_params(rule).allowed_methods
    return ctx.fb.verdict(
        rule, cc.method not in allowed,
        f"{run.run_id}: consent method {cc.method!r} is not one the regulator accepts as explicit "
        f"({', '.join(allowed)}).",
        f"{run.run_id}: consent by {cc.method}, an accepted explicit method.",
        run_ref=run.run_id, values={"method": cc.method, "allowed_methods": allowed})


# --- what was shown against what was signed --------------------------------

def _rnd_01(rule, run, ctx):
    """F29 — the person approved one thing and signed another."""
    cc = run.consent_ceremony
    if cc is None:
        return _no_ceremony(rule, run, ctx)
    if run.cart is None:
        return ctx.fb.absent(rule, "out_of_scope", f"{run.run_id}: no cart was signed.", run_ref=run.run_id)
    if cc.ceremony_scope != "per_transaction":
        return ctx.fb.absent(
            rule, "out_of_scope",
            f"{run.run_id}: a standing-authority ceremony renders the cap, not this cart's total.",
            run_ref=run.run_id, values={"ceremony_scope": cc.ceremony_scope})
    rv = cc.rendered_values
    if rv is None:
        return ctx.fb.absent(
            rule, "missing_block",
            f"{run.run_id}: the ceremony does not record what the shopper saw, so the screen cannot "
            f"be compared to the signature.", missing="consent_ceremony.rendered_values",
            run_ref=run.run_id)
    cart = run.cart
    diffs = []
    if abs(rv.amount - cart.cart_total) > 0.005:
        diffs.append(f"amount shown {rv.amount} vs signed {cart.cart_total}")
    if rv.currency != cart.currency:
        diffs.append(f"currency shown {rv.currency!r} vs signed {cart.currency!r}")
    if rv.merchant.strip().lower() != cart.merchant.name.strip().lower():
        diffs.append(f"merchant shown {rv.merchant!r} vs signed {cart.merchant.name!r}")
    shown = [(li.sku, li.qty, li.unit_price) for li in rv.line_items]
    signed = [(li.sku, li.qty, li.unit_price) for li in cart.line_items]
    if rv.line_items and shown != signed:
        diffs.append(f"line items shown {shown} vs signed {signed}")
    values = {"shown_amount": rv.amount, "signed_amount": cart.cart_total, "differences": diffs}
    return ctx.fb.verdict(
        rule, bool(diffs),
        f"{run.run_id}: what the shopper saw is not what was signed — {'; '.join(diffs)}.",
        f"{run.run_id}: the screen showed {rv.amount} {rv.currency} to {rv.merchant}, which is what "
        f"was signed.",
        run_ref=run.run_id, values=values,
        refs=[_ref("consent_ceremony.rendered_values.amount", rv.amount),
              _ref("cart.cart_total", cart.cart_total)])


def _rnd_02(rule, run, ctx):
    cc = run.consent_ceremony
    if cc is None:
        return _no_ceremony(rule, run, ctx)
    rv = cc.rendered_values
    if rv is None:
        return ctx.fb.absent(rule, "missing_block", f"{run.run_id}: nothing rendered was recorded.",
                             missing="consent_ceremony.rendered_values", run_ref=run.run_id)
    if not rv.caps_shown:
        return ctx.fb.absent(rule, "missing_block", f"{run.run_id}: the screen recorded no caps.",
                             missing="consent_ceremony.rendered_values.caps_shown", run_ref=run.run_id)
    scope = run.intent_mandate.authorization_scope
    mandate = {"max_transaction_amount": scope.max_transaction_amount,
               "max_cumulative_amount": scope.max_cumulative_amount}
    diffs = {k: (v, mandate[k]) for k, v in rv.caps_shown.items()
             if k in mandate and abs(v - mandate[k]) > 0.005}
    return ctx.fb.verdict(
        rule, bool(diffs),
        f"{run.run_id}: the screen showed cap(s) {diffs} that differ from the Intent's.",
        f"{run.run_id}: the caps shown ({rv.caps_shown}) are the Intent's.",
        run_ref=run.run_id, values={"caps_shown": rv.caps_shown, "differences": diffs})


def _scp_01(rule, run, ctx):
    """F26 — spent on something the person didn't agree to."""
    cc = run.consent_ceremony
    if cc is None:
        return _no_ceremony(rule, run, ctx)
    consented = cc.scope_consented.get("purpose_category")
    if consented is None:
        return ctx.fb.absent(rule, "missing_block",
                             f"{run.run_id}: the ceremony does not record the purpose consented to.",
                             missing="consent_ceremony.scope_consented.purpose_category", run_ref=run.run_id)
    purpose = run.intent_mandate.authorization_scope.purpose_category
    return ctx.fb.verdict(
        rule, consented != purpose,
        f"{run.run_id}: the shopper consented to {consented!r}; the Intent is for {purpose!r}.",
        f"{run.run_id}: consent covers the Intent's purpose ({purpose}).",
        run_ref=run.run_id, values={"consented": consented, "purpose_category": purpose})


def _frs_01(rule, run, ctx):
    """F25 — the consent is old (or from the future)."""
    cc = run.consent_ceremony
    if cc is None:
        return _no_ceremony(rule, run, ctx)
    if not cc.timestamp:
        return ctx.fb.absent(rule, "missing_block", f"{run.run_id}: the ceremony carries no timestamp.",
                             missing="consent_ceremony.timestamp", run_ref=run.run_id)
    issued = run.intent_mandate.issued_at
    authorised = run.payment.authorized_at if run.payment else None
    problems = []
    if cc.timestamp < issued:
        problems.append(f"consent at {cc.timestamp} predates the Intent issued at {issued}")
    if authorised and cc.timestamp > authorised:
        problems.append(f"consent at {cc.timestamp} follows the payment authorised at {authorised}")
    return ctx.fb.verdict(
        rule, bool(problems),
        f"{run.run_id}: {'; '.join(problems)}.",
        f"{run.run_id}: consent at {cc.timestamp} sits between the Intent and the payment.",
        run_ref=run.run_id, values={"consent_at": cc.timestamp, "intent_issued_at": issued,
                                    "payment_authorized_at": authorised})


def _std_01(rule, run, ctx):
    """F30 — a one-time yes became a standing authority."""
    cc = run.consent_ceremony
    if cc is None:
        return _no_ceremony(rule, run, ctx)
    usage = run.intent_mandate.authorization_scope.usage
    if usage is None:
        return ctx.fb.absent(rule, "missing_block", f"{run.run_id}: the Intent declares no usage mode.",
                             missing="intent_mandate.authorization_scope.usage", run_ref=run.run_id)
    standing_on_single = cc.ceremony_scope == "standing_authority" and usage.mode == "single_use"
    return ctx.fb.verdict(
        rule, standing_on_single,
        f"{run.run_id}: a standing-authority ceremony was used for a single-use mandate.",
        f"{run.run_id}: a {cc.ceremony_scope} ceremony for a {usage.mode} mandate.",
        run_ref=run.run_id, values={"ceremony_scope": cc.ceremony_scope, "usage_mode": usage.mode})


# --- judged: value for money -------------------------------------------------

def _delimit(text: str | None) -> str | None:
    return None if text is None else f"<<<UNTRUSTED_MERCHANT_TEXT>>>{text}<<<END_UNTRUSTED_MERCHANT_TEXT>>>"


def _vfm_01(rule, run, ctx):
    """F38's evidence: what was picked, at what price, against what else was
    on the table. The verdict — was a cheaper option equivalent — is judged."""
    sc = run.construction_context.selection_context
    if run.cart is None:
        return []
    if sc is None:
        return ctx.fb.absent(rule, "missing_block",
                             f"{run.run_id}: no selection context — what else the agent could have "
                             f"chosen is not on record.",
                             missing="construction_context.selection_context", run_ref=run.run_id)
    selected = next((li for li in run.cart.line_items if li.sku == sc.selected_sku), None)
    price = selected.unit_price if selected else None
    alternatives = [{"sku": a.sku, "merchant_id": a.merchant_id, "price": a.price,
                     "description": _delimit(a.description)} for a in sc.alternatives_considered]
    cheapest = min((a.price for a in sc.alternatives_considered), default=None)
    premium = (round(100 * (price - cheapest) / cheapest, 1)
               if price is not None and cheapest else None)
    return ctx.fb.measurement(
        "selection",
        f"{run.run_id}: selected {sc.selected_sku} at {price} against {len(alternatives)} "
        f"alternative(s), cheapest {cheapest}" + (f" ({premium}% premium)." if premium is not None else "."),
        rule=rule, run_ref=run.run_id,
        values={"query": sc.query, "selected_sku": sc.selected_sku, "selected_price": price,
                "selected_in_cart": selected is not None, "merchant_id": run.cart.merchant.merchant_id,
                "alternatives": alternatives, "cheapest_alternative": cheapest, "premium_pct": premium},
        refs=[_ref("construction_context.selection_context.selected_sku", sc.selected_sku)])


_RUN_CHECKERS = {
    "human_present_when_required": _prs_01,
    "consent_record_present": _rec_01,
    "consent_principal_matches_intent": _prn_01,
    "consent_method_allowlist": _mth_01,
    "rendered_values_match_signed_cart": _rnd_01,
    "caps_shown_match_mandate": _rnd_02,
    "consent_scope_matches_purpose": _scp_01,
    "consent_fresh_for_the_mandate": _frs_01,
    "standing_authority_not_for_single_use": _std_01,
    "value_for_money_against_alternatives": _vfm_01,
}


def run_consent_checks(dossier: LoadedDossier, ruleset: Ruleset, *,
                       ctx: ConsentContext | None = None) -> list[Fact]:
    ctx = ctx or build_context(dossier)
    return evaluate_ruleset(ruleset, builder=ctx.fb, ctx=ctx, runs=dossier.runs,
                            run_checkers=_RUN_CHECKERS, module="agents/consent_checks.py")
