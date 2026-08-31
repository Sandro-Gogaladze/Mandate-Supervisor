"""Mandate's deterministic checks: scope/cap (PLAN item 6 part 1) plus the
injection heuristic (part 2's deterministic half).

Together with the 2 chain-integrity rules ingestion/verify.py already
evaluates (Phase 3), this is the full deterministic floor —
MandateAgent.run() (agents/mandate.py), no LLM, no API key needed. The LLM
prompt-playback semantic subcheck (cart_reasoning_matches_intent) lives in
agents/mandate_reasoning.py instead and is only run by
MandateAgent.review() — same run()/review() split as agents/kya.py, and
for the same reason: the deterministic pipeline path should never require
a live key.

Unlike agents/kya_checks.py, most of the scope/cap rules carry no
ruleset-level params: the threshold being checked against
(max_transaction_amount, allowed merchant categories, ...) is the case's
own Intent, not a regulator policy constant — there's nothing for the
registry to configure beyond severity and status. Operates on the typed
CaseBundle, same reasoning as agents/kya_checks.py (no need to fight
raw-dict indexing for checks that don't touch cryptographic hashing).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from registry.loader import active_rules_by_type
from schemas import CaseBundle, Finding, Rule, Ruleset, typed_params

# The 2 rule types ingestion/verify.py already evaluates (chain-link hash
# integrity) — run_policy_checks() must not re-implement or skip past
# these silently.
CHAIN_HANDLED_TYPES = frozenset({
    "cart_chain_link_matches_intent",
    "payment_chain_link_matches_cart",
})

# Evaluated in agents/mandate_reasoning.py instead (needs an LLM call) —
# only reachable via MandateAgent.review(), never run(). Expected to have
# no checker here.
LLM_HANDLED_TYPES = frozenset({
    "cart_reasoning_matches_intent",
})

# Phrase patterns characteristic of an instruction embedded in
# merchant-authored product text, aimed at whoever/whatever processes the
# cart. Deliberately independent of the LLM semantic check (module
# docstring) — kept generic (direct address, false-authorization claims,
# no-confirmation-needed urgency, instruction-override language) rather
# than fitted to case-007's exact wording, so it isn't just a lookup table
# for one known example.
_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bnote to (?:the )?\w*\s*agent\b",
        r"\bno confirmation needed\b",
        r"\bwithout (?:confirmation|asking|approval)\b",
        r"\bpre[- ]authorized\b",
        r"\bthis is (?:pre-)?authoriz(?:ed|ation)\b",
        r"\bon behalf of (?:your |the )?operator\b",
        r"\byour operator\b",
        r"\bignore (?:previous|prior|all) instructions\b",
        r"\bas instructed by\b",
        r"\bdo not (?:tell|notify|inform) the (?:principal|human|user|customer)\b",
    ]
]


@dataclass
class PolicyContext:
    pass  # nothing global needed yet — every check reads only from the case itself


def build_policy_context(case: CaseBundle) -> PolicyContext:
    return PolicyContext()


class _FindingIdCounter:
    def __init__(self, case_id: str) -> None:
        self._case_id = case_id
        self._n = 0

    def next(self) -> str:
        self._n += 1
        return f"{self._case_id}-MND-{self._n:03d}"


def _finding(counter: _FindingIdCounter, case_id: str, rule: Rule, summary: str, details: dict | None = None) -> Finding:
    return Finding(
        finding_id=counter.next(),
        case_id=case_id,
        agent="mandate",
        type=rule.finding_type,
        rule_id=rule.rule_id,
        severity_weight=rule.severity_weight,
        summary=summary,
        details=details or {},
    )


def _check_per_transaction_cap(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    cap = case.mandate_chain.intent.authorization_scope.max_transaction_amount
    total = case.mandate_chain.cart.cart_total
    if total > cap:
        return _finding(counter, case.case_id, rule,
            f"Cart {case.mandate_chain.cart.cart_mandate_id} total {total} exceeds the "
            f"per-transaction cap of {cap} declared in the Intent.",
            details={"cart_total": total, "max_transaction_amount": cap})
    return None


def _check_merchant_category_allowed(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    mcc = case.mandate_chain.cart.merchant.mcc
    allowed = case.mandate_chain.intent.authorization_scope.allowed_merchant_categories
    if mcc not in allowed:
        return _finding(counter, case.case_id, rule,
            f"Merchant {case.mandate_chain.cart.merchant.merchant_id} category {mcc!r} is not "
            f"in the allowed categories {allowed} declared in the Intent.",
            details={"mcc": mcc, "allowed_merchant_categories": allowed})
    return None


def _check_counterparty_allowed(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    scope = case.mandate_chain.intent.authorization_scope
    if not scope.allowed_counterparties:
        # Empty allowlist means category-governed eligibility, not deny-all
        # — see schemas/mandate.py::AuthorizationScope.counterparty_policy
        # and case-006, which relies on exactly this.
        return None
    merchant_id = case.mandate_chain.cart.merchant.merchant_id
    allowed_ids = {c.counterparty_id for c in scope.allowed_counterparties}
    if merchant_id not in allowed_ids:
        return _finding(counter, case.case_id, rule,
            f"Merchant {merchant_id} is not in the Intent's allowed counterparty list "
            f"{sorted(allowed_ids)}.",
            details={"merchant_id": merchant_id, "allowed_counterparties": sorted(allowed_ids)})
    return None


def _check_cumulative_spend_within_monthly_cap(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    # "Month" = calendar month of Payment.authorized_at. Not a formal
    # schema field — inferred from the Intent's own natural_language_intent
    # ("don't let the month's total go over ₾X") and verified to match
    # case-001's own agent_attestation.reasoning ("month-to-date spend to
    # ₾1,748.10") to the cent. transaction_history's last entry is always
    # this case's own payment (verified across the whole corpus), so
    # summing history directly already includes the current transaction —
    # no separate cart_total addition needed.
    auth_date = date.fromisoformat(case.mandate_chain.payment.authorized_at[:10])
    month_to_date = sum(
        t.amount for t in case.transaction_history
        if date.fromisoformat(t.timestamp[:10]).year == auth_date.year
        and date.fromisoformat(t.timestamp[:10]).month == auth_date.month
    )
    cap = case.mandate_chain.intent.authorization_scope.max_cumulative_amount
    if month_to_date > cap:
        return _finding(counter, case.case_id, rule,
            f"Month-to-date spend {round(month_to_date, 2)} (calendar month of "
            f"{auth_date.isoformat()}) exceeds the cumulative cap of {cap}.",
            details={"month_to_date": round(month_to_date, 2), "max_cumulative_amount": cap})
    return None


def _check_payment_amount_matches_cart_total(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    tolerance = typed_params(rule).tolerance
    amount = case.mandate_chain.payment.amount
    total = case.mandate_chain.cart.cart_total
    if abs(amount - total) > tolerance:
        return _finding(counter, case.case_id, rule,
            f"Payment {case.mandate_chain.payment.payment_mandate_id} authorizes {amount} "
            f"but Cart {case.mandate_chain.cart.cart_mandate_id}'s total is {total}.",
            details={"payment_amount": amount, "cart_total": total})
    return None


def _check_cart_currency_matches_scope(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    cart_currency = case.mandate_chain.cart.currency
    scope_currency = case.mandate_chain.intent.authorization_scope.currency
    if cart_currency != scope_currency:
        return _finding(counter, case.case_id, rule,
            f"Cart currency {cart_currency!r} does not match the Intent scope's "
            f"currency {scope_currency!r}.")
    return None


def _check_payment_currency_matches_cart(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    payment_currency = case.mandate_chain.payment.currency
    cart_currency = case.mandate_chain.cart.currency
    if payment_currency != cart_currency:
        return _finding(counter, case.case_id, rule,
            f"Payment currency {payment_currency!r} does not match the Cart's "
            f"currency {cart_currency!r}.")
    return None


def _check_payment_authorized_within_validity_window(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    scope = case.mandate_chain.intent.authorization_scope
    auth_date = date.fromisoformat(case.mandate_chain.payment.authorized_at[:10])
    valid_from = date.fromisoformat(scope.valid_from[:10])
    valid_until = date.fromisoformat(scope.valid_until[:10])
    if not (valid_from <= auth_date <= valid_until):
        return _finding(counter, case.case_id, rule,
            f"Payment authorized {auth_date.isoformat()} falls outside the Intent's "
            f"validity window {valid_from.isoformat()}–{valid_until.isoformat()}.",
            details={"authorized_at": auth_date.isoformat(), "valid_from": valid_from.isoformat(), "valid_until": valid_until.isoformat()})
    return None


def _check_line_item_injection_heuristic(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    # Deliberately produces at most one Finding even if multiple line
    # items match — one clear signal per cart, with every matching item
    # and pattern recorded in details for a reviewer to inspect.
    matches = []
    for index, item in enumerate(case.mandate_chain.cart.line_items):
        for pattern in _INJECTION_PATTERNS:
            hit = pattern.search(item.description)
            if hit:
                matches.append({"line_item_index": index, "sku": item.sku, "matched_text": hit.group(0)})
    if matches:
        first = matches[0]
        return _finding(counter, case.case_id, rule,
            f"line_items[{first['line_item_index']}].description ({first['sku']}) contains "
            f"instruction-like text: {first['matched_text']!r}.",
            details={"matches": matches})
    return None


_POLICY_CHECKERS = {
    "cart_total_within_per_transaction_cap": _check_per_transaction_cap,
    "cart_merchant_category_allowed": _check_merchant_category_allowed,
    "cart_counterparty_allowed": _check_counterparty_allowed,
    "cumulative_spend_within_monthly_cap": _check_cumulative_spend_within_monthly_cap,
    "payment_amount_matches_cart_total": _check_payment_amount_matches_cart_total,
    "cart_currency_matches_scope": _check_cart_currency_matches_scope,
    "payment_currency_matches_cart": _check_payment_currency_matches_cart,
    "payment_authorized_within_validity_window": _check_payment_authorized_within_validity_window,
    "line_item_description_injection_heuristic": _check_line_item_injection_heuristic,
}


def run_policy_checks(case: CaseBundle, ruleset: Ruleset) -> list[Finding]:
    ctx = build_policy_context(case)
    counter = _FindingIdCounter(case.case_id)
    findings: list[Finding] = []
    for rule_type, rule in active_rules_by_type(ruleset).items():
        if rule_type in CHAIN_HANDLED_TYPES or rule_type in LLM_HANDLED_TYPES:
            continue
        checker = _POLICY_CHECKERS.get(rule_type)
        if checker is None:
            raise NotImplementedError(
                f"Active Mandate rule {rule.rule_id} (type={rule_type!r}) has no registered "
                f"checker in agents/mandate_checks.py — every active rule must be evaluable."
            )
        finding = checker(case, rule, ctx, counter)
        if finding is not None:
            findings.append(finding)
    return findings
