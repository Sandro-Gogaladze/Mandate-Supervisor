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
from data.registries import load_agents, load_model_blocklist, load_operators
from registry.loader import active_rules_by_type
from schemas import CaseBundle, Finding, Rule, Ruleset, typed_params

# Only two trust levels exist in the registry today; ranked so
# issuer_min_trust_level can compare "at least as trusted as."
_TRUST_LEVEL_RANK = {"recognized": 0, "primary": 1}

# The 6 rule types ingestion/verify.py already evaluates (credential
# signature/hash/alg, delegation-entry signatures, issuer trust/revocation)
# — run_policy_checks() must not re-implement or skip past these silently.
# The three KYA rules that Provenance (B1) owns, not KYA (A2).
#
# The TEC family reads like one family and is answered from two different
# evidence blocks: TEC-01/03/04 from the agent registry, TEC-02/05/06 from
# construction_context. kya-ruleset.md Part 3.5 assigns rules to the agent
# whose evidence block already contains what the rule needs, rather than to the
# agent the rule sounds related to — which is also what stopped F37 being
# asserted twice by two different agents.
#
# Listed here so KYA's dispatcher skips them deliberately. It must not fall
# back to skipping silently: an active rule nobody evaluates is worse than a
# crash, and that guarantee is what surfaced this split in the first place.
PROVENANCE_OWNED_TYPES = frozenset({
    "observed_model_matches_declared",
    "prompt_bound_to_released_artifact",
    "tool_servers_declared",
})

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
    """KYA-ACC-02 — the chain ends in the person who signed the mandate.

    Scoped, because it is only true of corporate delegation. There one officer
    both delegates authority to the agent AND signs the mandate, so the two
    must be the same person. In AP2's human-present consumer flow they are
    structurally different people: the shopper signs their own Intent, while
    the agent's credential chain terminates at the OPERATOR's accountable
    officer. Applying this rule there would breach on every consumer purchase
    ever made — not because anything is wrong, but because the rule is being
    asked a question about a relationship that does not exist.

    For a consumer principal the equivalent assurance is not the delegation
    chain at all: it is that the consent ceremony records the same principal
    who signed, which is SCA evidence the institution already holds.
    """
    chain = case.kya_credential.delegation_chain
    if not chain:
        return None
    if case.mandate_chain.intent.principal.principal_type == "consumer":
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


_PLACEHOLDER_MODEL_VERSIONS = frozenset({"", "unknown", "n/a", "tbd", "none", "-"})


def _check_model_version_pinned(case: CaseBundle, rule: Rule, ctx: PolicyContext, counter: _FindingIdCounter) -> Finding | None:
    """KYA-TEC-01 — is a model version declared at all? (F18)

    The weakest of the substrate rules and still worth having: without a
    pinned version you cannot separate a firm's misconfiguration from a
    model's flaw, cannot warn other firms running the same model, and cannot
    see a market-wide monoculture (F67). Whether the declared version is the
    one that actually *ran* is KYA-TEC-02, owned by Provenance, and blocked
    until construction_context is submitted.
    """
    declared = (case.mandate_chain.intent.agent.model_version or "").strip()
    if declared.lower() in _PLACEHOLDER_MODEL_VERSIONS:
        return _finding(counter, case.case_id, rule,
            f"agent {case.kya_credential.agent_id} declares no usable model_version "
            f"({case.mandate_chain.intent.agent.model_version!r}); its decisions cannot be "
            f"attributed to a specific model.",
            details={"declared_model_version": case.mandate_chain.intent.agent.model_version})
    return None


# ---------------------------------------------------------------------------
# Registry-backed rules (Stage 2).
#
# All five return None when the registry has no entry for this case. That is
# NOT "satisfied" — it is "absent", and the distinction matters: an agent the
# regulator has never heard of is a finding, not a pass. Findings cannot
# express absence, which is exactly why schemas/fact.py exists; until the Fact
# migration lands these skip cleanly rather than assert something false, and
# the legacy 7-case corpus (which predates every one of these registries) is
# the reason the distinction shows up at all.
# ---------------------------------------------------------------------------

def _agent_record(case: CaseBundle) -> dict | None:
    return load_agents().get(case.kya_credential.agent_id)


def _check_issuer_authorised_for_classification(case, rule, ctx, counter):
    agent = _agent_record(case)
    issuer = ctx.issuers.get(case.kya_credential.issuer.issuer_id)
    if agent is None or issuer is None or "authorised_classifications" not in issuer:
        return None
    classification = agent.get("classification")
    allowed = issuer["authorised_classifications"]
    if classification not in allowed:
        return _finding(counter, case.case_id, rule,
            f"Issuer {issuer['issuer_id']} is not accredited to issue for classification "
            f"{classification!r} (accredited for: {', '.join(allowed) or 'nothing'}).",
            details={"issuer_id": issuer["issuer_id"], "classification": classification,
                     "authorised_classifications": allowed})
    return None


def _check_operator_licence_current(case, rule, ctx, counter):
    """A licence OR a live sponsorship.

    Kestrel is not licensed and should not be: it is a technology operator
    whose authority to move money comes from the institution sponsoring it.
    A rule reading "must hold a licence" would fail every non-bank operator by
    construction, which is most of the market this regime exists to cover.
    """
    agent = _agent_record(case)
    if agent is None:
        return None
    operator = load_operators().get(agent.get("operator_id"))
    if operator is None:
        return None
    if operator.get("licence_status") in {"active", "current"}:
        return None
    sponsorship = operator.get("sponsorship") or {}
    if sponsorship.get("status") == "active":
        return None
    return _finding(counter, case.case_id, rule,
        f"Operator {operator['operator_id']} holds neither a current licence "
        f"(status={operator.get('licence_status')!r}) nor an active sponsorship.",
        details={"operator_id": operator["operator_id"],
                 "licence_status": operator.get("licence_status"),
                 "sponsorship_status": sponsorship.get("status")})


def _check_agent_registration_current(case, rule, ctx, counter):
    agent = _agent_record(case)
    if agent is None or not agent.get("authorisation_expires"):
        return None
    expires = date.fromisoformat(agent["authorisation_expires"][:10])
    if expires < ctx.reference_date:
        return _finding(counter, case.case_id, rule,
            f"Agent registration expired {expires.isoformat()}, before this transaction "
            f"({ctx.reference_date.isoformat()}).",
            details={"authorisation_expires": expires.isoformat(),
                     "as_of": ctx.reference_date.isoformat()})
    return None


def _check_registered_purpose_matches_mandate(case, rule, ctx, counter):
    agent = _agent_record(case)
    if agent is None or "registered_purpose_category" not in agent:
        return None
    registered = agent["registered_purpose_category"]
    declared = case.mandate_chain.intent.authorization_scope.purpose_category
    if registered != declared:
        return _finding(counter, case.case_id, rule,
            f"Mandate purpose_category {declared!r} does not match the registered purpose "
            f"{registered!r} for this agent.",
            details={"registered_purpose_category": registered, "mandate_purpose_category": declared})
    return None


def _check_revocation_check_not_stale(case, rule, ctx, counter):
    """Staleness of the check, not its answer.

    An institution that cannot say when it last confirmed a credential was
    live has a control gap whatever the credential turns out to be. `None`
    here means the field was not supplied at all — absent, not a breach.
    """
    checked = case.kya_credential.revocation_checked_at
    if not checked:
        return None
    max_age = typed_params(rule).max_age_days
    age = (ctx.reference_date - date.fromisoformat(checked[:10])).days
    if age > max_age:
        return _finding(counter, case.case_id, rule,
            f"Revocation status last checked {age} days before this transaction; "
            f"the maximum is {max_age}.",
            details={"revocation_checked_at": checked[:10], "age_days": age,
                     "max_age_days": max_age})
    return None



def _check_no_link_grants_more_than_it_holds(case, rule, ctx, counter):
    """KYA-ACC-06 / F11 — a middle party cannot grant what it does not hold.

    The chain runs agent (level 0) upward to the accountable human, so each
    level is granted its authority BY the level above it. A child holding
    capabilities its parent never had means somebody minted authority mid-chain.

    Silent when no level records `granted_capabilities`: a chain that only lists
    names has nothing to compare, which is absence, not compliance. That gap is
    exactly why the field was added.
    """
    chain = case.kya_credential.delegation_chain
    if len(chain) < 2 or not any(e.granted_capabilities for e in chain):
        return None
    problems = []
    for child, parent in zip(chain, chain[1:]):
        if not parent.granted_capabilities:
            continue
        if excess := sorted(set(child.granted_capabilities) - set(parent.granted_capabilities)):
            problems.append(
                f"level {child.level} ({child.holder_id}) holds {', '.join(excess)} which "
                f"level {parent.level} ({parent.holder_id}) does not")
        c_cap = (child.constraints or {}).get("max_transaction_amount")
        p_cap = (parent.constraints or {}).get("max_transaction_amount")
        if c_cap is not None and p_cap is not None and c_cap > p_cap:
            problems.append(
                f"level {child.level} carries a cap of {c_cap} above level "
                f"{parent.level}'s {p_cap}")
    if problems:
        return _finding(counter, case.case_id, rule,
            "Delegation grants authority the granting holder does not itself hold: "
            + "; ".join(problems) + ".", details={"violations": problems})
    return None


def _check_declared_model_not_blocklisted(case, rule, ctx, counter):
    """KYA-TEC-03 — the model the mandate DECLARES is not barred.

    Deliberately the declared version, because that is what lives in KYA's
    evidence block. Whether the model that actually answered was barred is a
    different question against different evidence, and it belongs to Provenance
    (TEC-02) — see kya-ruleset.md Part 3.5 on splitting TEC by evidence rather
    than by topic.
    """
    declared = case.mandate_chain.intent.agent.model_version
    blocked = load_model_blocklist().get(declared)
    if blocked is None:
        return None
    return _finding(counter, case.case_id, rule,
        f"Declared model {declared!r} was blocklisted on {blocked['blocked_at']}: "
        f"{blocked['reason']}",
        details={"model_version": declared, "blocked_at": blocked["blocked_at"],
                 "reason": blocked["reason"]})


def _check_model_validation_evidence_on_file(case, rule, ctx, counter):
    agent = _agent_record(case)
    if agent is None:
        return None
    declared = case.mandate_chain.intent.agent.model_version
    validated = {v["model_version"] for v in agent.get("validation_evidence", [])}
    if declared in validated:
        return None
    return _finding(counter, case.case_id, rule,
        f"No validation evidence is on file for model {declared!r}, which this agent's "
        f"{agent.get('risk_class', 'unknown')} risk classification requires.",
        details={"model_version": declared, "risk_class": agent.get("risk_class"),
                 "validated_versions": sorted(validated)})



def _check_terminus_is_an_authorised_signatory(case, rule, ctx, counter):
    """KYA-ACC-07 — the accountable person is one the firm actually authorised.

    ACC-01 asks whether a human is at the end of the chain; this asks whether
    that human had standing to be there. A named individual who is not on the
    operator's signatory list is a delegation nobody at the firm sanctioned.
    """
    chain = case.kya_credential.delegation_chain
    agent = _agent_record(case)
    if not chain or agent is None:
        return None
    operator = load_operators().get(agent.get("operator_id"))
    if operator is None or not operator.get("authorised_signatories"):
        return None
    terminus = chain[-1]
    authorised = {s["principal_id"] for s in operator["authorised_signatories"]}
    if terminus.holder_id in authorised:
        return None
    return _finding(counter, case.case_id, rule,
        f"Chain terminus {terminus.holder_id} ({terminus.name}) is not on "
        f"{operator['operator_id']}'s authorised-signatory list.",
        details={"terminus": terminus.holder_id, "authorised_signatories": sorted(authorised)})


def _check_operator_standing_not_barring(case, rule, ctx, counter):
    agent = _agent_record(case)
    operator = load_operators().get(agent.get("operator_id")) if agent else None
    if operator is None:
        return None
    barring = {"suspended", "wound_down", "revoked", "under_enforcement"}
    if (standing := operator.get("standing")) in barring:
        return _finding(counter, case.case_id, rule,
            f"Operator {operator['operator_id']} is in a barring standing ({standing}).",
            details={"operator_id": operator["operator_id"], "standing": standing})
    return None


def _check_no_unnotified_change_of_control(case, rule, ctx, counter):
    """KYA-OPF-03 / F14 — the firm changed hands after the credential was issued.

    A credential attests to an operator as it was at issuance. Ownership moving
    afterwards means the entity vouched for is not the entity now running the
    agent, and the credential says nothing about the new one.
    """
    agent = _agent_record(case)
    operator = load_operators().get(agent.get("operator_id")) if agent else None
    if operator is None:
        return None
    issued = case.kya_credential.issued_at[:10]
    after = [c for c in operator.get("ownership_changes", []) if c.get("date", "") > issued]
    if after:
        return _finding(counter, case.case_id, rule,
            f"Control of {operator['operator_id']} changed {len(after)} time(s) after the "
            f"credential was issued on {issued}, with no reissuance.",
            details={"credential_issued_at": issued, "changes": after})
    return None


def _check_compliance_contact_on_record(case, rule, ctx, counter):
    agent = _agent_record(case)
    operator = load_operators().get(agent.get("operator_id")) if agent else None
    if operator is None:
        return None
    contact = operator.get("compliance_contact") or {}
    if contact.get("name"):
        return None
    return _finding(counter, case.case_id, rule,
        f"No named compliance contact is on record for {operator['operator_id']}: there is "
        f"nobody for a supervisor to call.",
        details={"operator_id": operator["operator_id"]})


def _check_agent_registered_before_first_use(case, rule, ctx, counter):
    """KYA-REG-01 / F16 — the agent transacted before it was declared."""
    agent = _agent_record(case)
    if agent is None or not agent.get("registered_at"):
        return None
    registered = date.fromisoformat(agent["registered_at"][:10])
    if registered <= ctx.reference_date:
        return None
    return _finding(counter, case.case_id, rule,
        f"Agent was registered {registered.isoformat()}, after this transaction "
        f"({ctx.reference_date.isoformat()}).",
        details={"registered_at": registered.isoformat(), "as_of": ctx.reference_date.isoformat()})


def _check_risk_classification_declared(case, rule, ctx, counter):
    agent = _agent_record(case)
    if agent is None:
        return None
    if agent.get("risk_class"):
        return None
    return _finding(counter, case.case_id, rule,
        f"No risk classification is declared for {agent['agent_id']}, so no rule that scales "
        f"with risk can be applied to it.",
        details={"agent_id": agent["agent_id"]})


_POLICY_CHECKERS = {
    "delegation_terminus_is_authorised_signatory": _check_terminus_is_an_authorised_signatory,
    "operator_standing_not_barring": _check_operator_standing_not_barring,
    "no_unnotified_change_of_control": _check_no_unnotified_change_of_control,
    "compliance_contact_on_record": _check_compliance_contact_on_record,
    "agent_registered_before_first_use": _check_agent_registered_before_first_use,
    "risk_classification_declared": _check_risk_classification_declared,
    "delegation_no_grant_exceeds_holder": _check_no_link_grants_more_than_it_holds,
    "declared_model_not_blocklisted": _check_declared_model_not_blocklisted,
    "model_validation_evidence_on_file": _check_model_validation_evidence_on_file,
    "issuer_authorised_for_classification": _check_issuer_authorised_for_classification,
    "operator_licence_current": _check_operator_licence_current,
    "agent_registration_current": _check_agent_registration_current,
    "registered_purpose_matches_mandate": _check_registered_purpose_matches_mandate,
    "revocation_check_not_stale": _check_revocation_check_not_stale,
    "model_version_pinned_to_mandate": _check_model_version_pinned,
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
        if rule_type in PROVENANCE_OWNED_TYPES:
            continue
        if rule_type in _SERIES_CHECKERS:
            # Cross-credential: needs the whole series, so it runs through
            # run_credential_series_checks() against the Dossier instead.
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


# ---------------------------------------------------------------------------
# Credential-series rules.
#
# KYA-CAP-05 and KYA-LIF-04 are cross-credential by nature: capability creep is
# invisible in one credential BY DEFINITION, and two credentials cannot overlap
# if you are only ever shown one. They read `credential_history`, which lives on
# the Dossier rather than the CaseBundle, so they run through their own entry
# point rather than the per-case dispatcher.
#
# Both are properties of the identity, not of any run — the findings they emit
# carry no run_ref, and that is correct rather than a gap.
# ---------------------------------------------------------------------------

def _series(dossier) -> list:
    return sorted([dossier.dossier.kya_credential, *dossier.dossier.credential_history],
                  key=lambda c: c.issued_at)


def _check_no_capability_creep(dossier, rule, counter) -> Finding | None:
    """KYA-CAP-05 / F20 — permissions widening quietly across reissuance.

    Growth is not automatically creep: an agent that legitimately gains a new
    function should gain the capability for it. What the rule catches is
    widening that nobody had to justify, so the tolerance is a dial — how many
    new capabilities may appear at one renewal before it needs an explanation.
    """
    params = typed_params(rule)
    tolerance = getattr(params, "max_new_capabilities_per_reissue", 1)
    creep = []
    for older, newer in zip(_series(dossier), _series(dossier)[1:]):
        added = sorted(set(newer.capabilities) - set(older.capabilities))
        if len(added) > tolerance:
            creep.append(f"{older.credential_id} -> {newer.credential_id} added "
                         f"{', '.join(added)}")
    if creep:
        return _finding_for(dossier, rule, counter,
            f"Capabilities widened across reissuance beyond the tolerance of {tolerance}: "
            + "; ".join(creep) + ".", {"reissues": creep, "tolerance": tolerance})
    return None


def _check_no_simultaneous_credentials(dossier, rule, counter) -> Finding | None:
    """KYA-LIF-04 / F21 — two live credentials for one agent.

    Usually a renewal issued before the predecessor was revoked, which is how
    it happens in practice and why it is worth detecting: for the overlap
    window the agent has two valid identities, and revoking one does not stop
    it.
    """
    overlaps = []
    series = _series(dossier)
    for a, b in zip(series, series[1:]):
        if b.issued_at < a.expires_at:
            overlaps.append(f"{a.credential_id} (to {a.expires_at[:10]}) and "
                            f"{b.credential_id} (from {b.issued_at[:10]})")
    if overlaps:
        return _finding_for(dossier, rule, counter,
            f"{len(overlaps)} pair(s) of credentials for this agent are valid simultaneously: "
            + "; ".join(overlaps) + ".", {"overlaps": overlaps})
    return None


def _finding_for(dossier, rule, counter, summary, details) -> Finding:
    return Finding(
        finding_id=counter.next(), case_id=dossier.dossier.dossier_id, agent="kya",
        type=rule.finding_type, rule_id=rule.rule_id,
        severity_weight=rule.severity_weight, summary=summary, details=details)


_SERIES_CHECKERS = {
    "capability_creep_across_reissuance": _check_no_capability_creep,
    "no_simultaneous_credentials": _check_no_simultaneous_credentials,
}


def run_credential_series_checks(dossier, ruleset: Ruleset) -> list[Finding]:
    """The cross-credential KYA rules, which need the whole series at once."""
    counter = _FindingIdCounter(dossier.dossier.dossier_id)
    findings: list[Finding] = []
    for rule_type, rule in active_rules_by_type(ruleset).items():
        if checker := _SERIES_CHECKERS.get(rule_type):
            if (f := checker(dossier, rule, counter)) is not None:
                findings.append(f)
    return findings
