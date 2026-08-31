"""The 12 active KYA rules ingestion (Phase 3) deliberately left uncovered:
issuer trust-level/re-accreditation, credential lifecycle, delegation-chain
shape, capability hygiene, consent method. Together with
ingestion/verify.py's 6 credential-signature/issuer checks (see
CRYPTO_HANDLED_TYPES below), this is the full active KYA ruleset.

Operates on the typed `CaseBundle` (case.case), not the raw dict — unlike
ingestion/verify.py, none of these need byte-exact canonical hashing, so
there's no reason to fight with dict indexing.

`run_policy_checks()` raises loudly if an active rule has no registered
checker here, rather than silently skipping it — an active rule nobody's
code evaluates is worse than a crash (see docs/phases/05-kya-agent.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from data.issuers import load_issuer_registry
from registry.loader import active_rules_by_type
from schemas import CaseBundle, Finding, Rule, Ruleset, typed_params

# Only two trust levels exist in the registry today; ranked so
# issuer_min_trust_level can compare "at least as trusted as."
_TRUST_LEVEL_RANK = {"recognized": 0, "primary": 1}

# The 6 rule types ingestion/verify.py already evaluates (credential
# signature/hash/alg, delegation-entry signatures, issuer trust/revocation)
# — run_policy_checks() must not re-implement or skip past these silently.
CRYPTO_HANDLED_TYPES = frozenset({
    "signature_algorithm_allowlist",
    "signature_must_verify",
    "payload_hash_must_recompute",
    "delegation_entry_signatures_must_verify",
    "issuer_trust_required",
    "issuer_status_active",
})


@dataclass
class PolicyContext:
    issuers: dict[str, dict]
    # "As of" reference for date-based rules — the case's own Payment
    # authorization time, not wall-clock "now". A batch-supervision system
    # meant to be replayable from the ledger shouldn't get a different
    # verdict depending on when it happens to be (re-)run.
    reference_date: date


def build_policy_context(case: CaseBundle) -> PolicyContext:
    authorized_at = case.mandate_chain.payment.authorized_at
    return PolicyContext(
        issuers=load_issuer_registry(),
        reference_date=date.fromisoformat(authorized_at[:10]),
    )


class _FindingIdCounter:
    def __init__(self, case_id: str) -> None:
        self._case_id = case_id
        self._n = 0

    def next(self) -> str:
        self._n += 1
        return f"{self._case_id}-POL-{self._n:03d}"


def _finding(counter: _FindingIdCounter, case_id: str, rule: Rule, summary: str, details: dict | None = None) -> Finding:
    return Finding(
        finding_id=counter.next(),
        case_id=case_id,
        agent="kya",
        type=rule.finding_type,
        rule_id=rule.rule_id,
        severity_weight=rule.severity_weight,
        summary=summary,
        details=details or {},
    )


def _check_issuer_min_trust_level(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    issuer = ctx.issuers.get(case.kya_credential.issuer.issuer_id)
    if issuer is None:
        return None  # KYA-ISS-01's job, not this rule's
    required = typed_params(rule).min_trust_level
    if _TRUST_LEVEL_RANK.get(issuer["trust_level"], -1) < _TRUST_LEVEL_RANK.get(required, 99):
        return _finding(counter, case.case_id, rule,
            f"Issuer {issuer['issuer_id']} trust_level={issuer['trust_level']!r} "
            f"is below the required minimum {required!r}.")
    return None


def _check_issuer_reaccreditation_not_stale(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    issuer = ctx.issuers.get(case.kya_credential.issuer.issuer_id)
    if issuer is None:
        return None
    accredited_since = date.fromisoformat(issuer["accredited_since"])
    age_days = (ctx.reference_date - accredited_since).days
    max_age = typed_params(rule).max_reaccreditation_age_days
    if age_days > max_age:
        return _finding(counter, case.case_id, rule,
            f"Issuer {issuer['issuer_id']} was last accredited {accredited_since.isoformat()}, "
            f"{age_days} days before this case's reference date — exceeds the {max_age}-day limit.")
    return None


def _check_credential_not_expired(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    expires = date.fromisoformat(case.kya_credential.expires_at[:10])
    grace = typed_params(rule).grace_period_days
    if ctx.reference_date > expires + timedelta(days=grace):
        return _finding(counter, case.case_id, rule,
            f"Credential {case.kya_credential.credential_id} expired {expires.isoformat()}, "
            f"before this case's reference date {ctx.reference_date.isoformat()} "
            f"(grace period {grace} days).")
    return None


def _check_credential_min_validity_window(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    issued = date.fromisoformat(case.kya_credential.issued_at[:10])
    expires = date.fromisoformat(case.kya_credential.expires_at[:10])
    min_days = typed_params(rule).min_validity_days
    span = (expires - issued).days
    if span < min_days:
        return _finding(counter, case.case_id, rule,
            f"Credential {case.kya_credential.credential_id} validity window is "
            f"{span} days, below the {min_days}-day minimum.")
    return None


def _check_credential_issued_before_expiry(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    issued = date.fromisoformat(case.kya_credential.issued_at[:10])
    expires = date.fromisoformat(case.kya_credential.expires_at[:10])
    if not issued < expires:
        return _finding(counter, case.case_id, rule,
            f"Credential {case.kya_credential.credential_id} issued_at={issued.isoformat()} "
            f"does not precede expires_at={expires.isoformat()}.")
    return None


def _check_delegation_terminates_in_human(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    chain = case.kya_credential.delegation_chain
    terminus_type = chain[-1].holder_type if chain else None
    if terminus_type != "human":
        return _finding(counter, case.case_id, rule,
            f"delegation_chain for credential {case.kya_credential.credential_id} "
            f"terminates in holder_type={terminus_type!r}, not 'human'.",
            details={"terminus_holder_type": terminus_type})
    return None


def _check_delegation_no_duplicate_holders(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    ids = [e.holder_id for e in case.kya_credential.delegation_chain]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        return _finding(counter, case.case_id, rule,
            f"delegation_chain has duplicate holder_id(s): {dupes}.",
            details={"duplicates": dupes})
    return None


def _check_delegation_max_depth(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    depth = len(case.kya_credential.delegation_chain)
    max_depth = typed_params(rule).max_depth
    if depth > max_depth:
        return _finding(counter, case.case_id, rule,
            f"delegation_chain depth {depth} exceeds the maximum of {max_depth}.")
    return None


def _check_delegation_terminus_matches_principal(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    chain = case.kya_credential.delegation_chain
    if not chain:
        return None
    terminus_id = chain[-1].holder_id
    principal_id = case.mandate_chain.intent.principal.principal_id
    if terminus_id != principal_id:
        return _finding(counter, case.case_id, rule,
            f"delegation_chain terminus holder_id={terminus_id!r} does not match "
            f"Intent principal_id={principal_id!r}.",
            details={"terminus_holder_id": terminus_id, "intent_principal_id": principal_id})
    return None


def _check_capability_vocabulary_allowlist(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    params = typed_params(rule)
    bad = [
        c for c in case.kya_credential.capabilities
        if c not in params.allowed_exact and not any(c.startswith(p) for p in params.allowed_prefixes)
    ]
    if bad:
        return _finding(counter, case.case_id, rule,
            f"capabilities outside the allowed vocabulary: {bad}.",
            details={"capabilities": bad})
    return None


def _check_capabilities_non_empty(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    if not case.kya_credential.capabilities:
        return _finding(counter, case.case_id, rule,
            f"credential {case.kya_credential.credential_id} has an empty capabilities list.")
    return None


def _check_consent_method_allowlist(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    params = typed_params(rule)
    method = case.mandate_chain.intent.consent.method
    if method not in params.allowed_methods:
        return _finding(counter, case.case_id, rule,
            f"consent.method={method!r} is not in the allowed list {params.allowed_methods}.")
    return None


_POLICY_CHECKERS = {
    "issuer_min_trust_level": _check_issuer_min_trust_level,
    "issuer_reaccreditation_not_stale": _check_issuer_reaccreditation_not_stale,
    "credential_not_expired": _check_credential_not_expired,
    "credential_min_validity_window": _check_credential_min_validity_window,
    "credential_issued_before_expiry": _check_credential_issued_before_expiry,
    "delegation_chain_terminates_in_human": _check_delegation_terminates_in_human,
    "delegation_chain_no_duplicate_holders": _check_delegation_no_duplicate_holders,
    "delegation_chain_max_depth": _check_delegation_max_depth,
    "delegation_terminus_matches_intent_principal": _check_delegation_terminus_matches_principal,
    "capability_vocabulary_allowlist": _check_capability_vocabulary_allowlist,
    "credential_capabilities_non_empty": _check_capabilities_non_empty,
    "consent_method_allowlist": _check_consent_method_allowlist,
}


def run_policy_checks(case: CaseBundle, ruleset: Ruleset) -> list[Finding]:
    ctx = build_policy_context(case)
    counter = _FindingIdCounter(case.case_id)
    findings: list[Finding] = []
    for rule_type, rule in active_rules_by_type(ruleset).items():
        if rule_type in CRYPTO_HANDLED_TYPES:
            continue
        checker = _POLICY_CHECKERS.get(rule_type)
        if checker is None:
            raise NotImplementedError(
                f"Active KYA rule {rule.rule_id} (type={rule_type!r}) has no registered "
                f"checker in agents/kya_checks.py — every active rule must be evaluable."
            )
        finding = checker(case, rule, ctx, counter)
        if finding is not None:
            findings.append(finding)
    return findings
