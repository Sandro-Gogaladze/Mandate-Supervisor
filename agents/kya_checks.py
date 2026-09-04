"""KYA's deterministic floor — the computable rules of `kya.json` that are not
cryptographic (ingestion's job) and not Provenance's (construction_context).

Together with ingestion's six credential-signature/issuer checks and
Provenance's three, this is the full active KYA ruleset. `run_policy_checks()`
raises if an active computable rule has no checker here and is not listed as
handled elsewhere — an active rule nobody's code evaluates is worse than a
crash.

**Scope, decided per rule by what its answer depends on.** The credential, the
delegation chain and the register entries are properties of the AGENT, so most
rules here are dossier-level: one fact. Eight are run-level, because their
answer changes from run to run — they read the run's own Intent Mandate
(`ACC-02`, `TEC-01/03/04`, `REG-05`) or ask whether something held *at the
time of use* (`LIF-01`, `REG-01`, `REG-04`). A credential that expired in the
seventh week of a twelve-week window is fine on forty runs and breached on
ten, and only per-run facts can say which.

**Dates.** "Time of use" is the run's `started_at`. "As of" for the staleness
rules (issuer re-accreditation, revocation check) is `submitted_at`: how fresh
the regulator's evidence was when the decision was asked for. Neither is
wall-clock now — a review replayed from the ledger must reach the same facts.

**Registers.** A rule that needs a register entry the regulator does not hold
emits `absent/no_registry_record` naming the entry, rather than silently
passing — with one exception: `REG-01` (registered before first use) BREACHES
on an unregistered agent, because an agent the register has never heard of
transacting is precisely the failure that rule exists to catch.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from data.issuers import load_issuer_registry
from data.registries import load_agents, load_model_blocklist, load_operators
from schemas import EvidenceRef, Fact, KYACredential, Ruleset, typed_params
from schemas.dossier import LoadedDossier, Run

from .facts import FactBuilder, evaluate_ruleset

DOMAIN = "kya"

# Only two trust levels exist in the registry today; ranked so
# issuer_min_trust_level can compare "at least as trusted as."
_TRUST_LEVEL_RANK = {"recognized": 0, "primary": 1}

# The 6 rule types ingestion/verify.py evaluates (credential signature/hash/alg,
# delegation-entry signatures, issuer trust/revocation). Listed so the
# dispatcher skips them deliberately rather than by accident.
CRYPTO_HANDLED_TYPES = frozenset({
    "signature_algorithm_allowlist",
    "signature_must_verify",
    "payload_hash_must_recompute",
    "delegation_entry_signatures_must_verify",
    "issuer_trust_required",
    "issuer_status_active",
})

# The three KYA rules that Provenance (B1) owns, not KYA (A2).
#
# The TEC family reads like one family and is answered from two different
# evidence blocks: TEC-01/03/04 from the agent registry, TEC-02/05/06 from
# construction_context. kya-ruleset.md Part 3.5 assigns rules to the agent
# whose evidence block already contains what the rule needs, rather than to the
# agent the rule sounds related to — which is also what stopped F37 being
# asserted twice by two different agents.
PROVENANCE_OWNED_TYPES = frozenset({
    "observed_model_matches_declared",
    "prompt_bound_to_released_artifact",
    "tool_servers_declared",
})

_PLACEHOLDER_MODEL_VERSIONS = frozenset({"", "unknown", "n/a", "tbd", "none", "-"})


@dataclass
class PolicyContext:
    fb: FactBuilder
    agent_id: str
    credential: KYACredential
    series: list[KYACredential]        # every credential for this agent, oldest first
    submitted_at: date
    issuers: dict[str, dict]
    agents: dict[str, dict]
    operators: dict[str, dict]
    blocklist: dict[str, dict]

    @property
    def issuer(self) -> dict | None:
        return self.issuers.get(self.credential.issuer.issuer_id)

    @property
    def agent(self) -> dict | None:
        return self.agents.get(self.agent_id)

    @property
    def operator(self) -> dict | None:
        agent = self.agent
        return self.operators.get(agent.get("operator_id")) if agent else None


def build_policy_context(d: LoadedDossier, *, issuers: dict | None = None,
                         agents: dict | None = None, operators: dict | None = None,
                         blocklist: dict | None = None) -> PolicyContext:
    """Registries are injectable so the sandbox and the tests can run the same
    checkers against a different regulator-side state."""
    cred = d.dossier.kya_credential
    return PolicyContext(
        fb=FactBuilder(d.dossier.dossier_id, DOMAIN),
        agent_id=d.dossier.agent_id,
        credential=cred,
        series=sorted([cred, *d.dossier.credential_history], key=lambda c: c.issued_at),
        submitted_at=date.fromisoformat(d.dossier.submission_context.submitted_at[:10]),
        issuers=issuers if issuers is not None else load_issuer_registry(),
        agents=agents if agents is not None else load_agents(),
        operators=operators if operators is not None else load_operators(),
        blocklist=blocklist if blocklist is not None else load_model_blocklist(),
    )


def _use_date(run: Run) -> date:
    return date.fromisoformat(run.started_at[:10])


def _cred_ref(ctx: PolicyContext, field: str, value) -> EvidenceRef:
    return EvidenceRef(kind="credential_field", ref=f"kya_credential.{field}", value=value)


# --- register gaps ---------------------------------------------------------

def _no_agent(rule, ctx, run_ref=None) -> Fact:
    return ctx.fb.absent(
        rule, "no_registry_record",
        f"{ctx.agent_id} has no entry in the agent register, so {rule.rule_id} has nothing to "
        f"check against.", missing=f"registry:agents[{ctx.agent_id}]", run_ref=run_ref)


def _no_operator(rule, ctx, run_ref=None) -> Fact:
    if ctx.agent is None:
        return _no_agent(rule, ctx, run_ref)
    op = ctx.agent.get("operator_id")
    return ctx.fb.absent(
        rule, "no_registry_record",
        f"Operator {op} named on {ctx.agent_id}'s register entry has no entry in the operator "
        f"register, so {rule.rule_id} has nothing to check against.",
        missing=f"registry:operators[{op}]", run_ref=run_ref)


def _no_issuer(rule, ctx) -> Fact:
    iid = ctx.credential.issuer.issuer_id
    return ctx.fb.absent(
        rule, "no_registry_record",
        f"Issuer {iid} is not in the trust registry (KYA-ISS-01's finding), so {rule.rule_id} "
        f"has no issuer record to evaluate.", missing=f"registry:issuers[{iid}]")


def _no_field(rule, ctx, register: str, key: str, field: str, run_ref=None) -> Fact:
    return ctx.fb.absent(
        rule, "no_registry_record",
        f"The {register} register entry for {key} carries no {field}, so {rule.rule_id} "
        f"cannot be evaluated.", missing=f"registry:{register}[{key}].{field}", run_ref=run_ref)


# ---------------------------------------------------------------------------
# ISS — the issuer (dossier-level)
# ---------------------------------------------------------------------------

def _iss_03(rule, ctx):
    if (issuer := ctx.issuer) is None:
        return _no_issuer(rule, ctx)
    required = typed_params(rule).min_trust_level
    level = issuer["trust_level"]
    below = _TRUST_LEVEL_RANK.get(level, -1) < _TRUST_LEVEL_RANK.get(required, 99)
    return ctx.fb.verdict(
        rule, below,
        f"Issuer {issuer['issuer_id']} trust_level={level!r} is below the required minimum "
        f"{required!r}.",
        f"Issuer {issuer['issuer_id']} trust_level={level!r} meets the required minimum "
        f"{required!r}.",
        values={"issuer_id": issuer["issuer_id"], "trust_level": level, "required": required},
        refs=[EvidenceRef(kind="registry", ref=f"issuers[{issuer['issuer_id']}].trust_level",
                          value=level)])


def _iss_04(rule, ctx):
    if (issuer := ctx.issuer) is None:
        return _no_issuer(rule, ctx)
    since = date.fromisoformat(issuer["accredited_since"])
    age = (ctx.submitted_at - since).days
    max_age = typed_params(rule).max_reaccreditation_age_days
    return ctx.fb.verdict(
        rule, age > max_age,
        f"Issuer {issuer['issuer_id']} was last accredited {since.isoformat()}, {age} days before "
        f"submission — beyond the {max_age}-day limit.",
        f"Issuer {issuer['issuer_id']} was accredited {since.isoformat()}, {age} days before "
        f"submission, within the {max_age}-day limit.",
        values={"accredited_since": since.isoformat(), "age_days": age, "max_age_days": max_age,
                "as_of": ctx.submitted_at.isoformat()})


def _iss_05(rule, ctx):
    if ctx.agent is None:
        return _no_agent(rule, ctx)
    if (issuer := ctx.issuer) is None:
        return _no_issuer(rule, ctx)
    if "authorised_classifications" not in issuer:
        return _no_field(rule, ctx, "issuers", issuer["issuer_id"], "authorised_classifications")
    classification = ctx.agent.get("classification")
    allowed = issuer["authorised_classifications"]
    return ctx.fb.verdict(
        rule, classification not in allowed,
        f"Issuer {issuer['issuer_id']} is not accredited to issue for classification "
        f"{classification!r} (accredited for: {', '.join(allowed) or 'nothing'}).",
        f"Issuer {issuer['issuer_id']} is accredited for {classification!r}.",
        values={"issuer_id": issuer["issuer_id"], "classification": classification,
                "authorised_classifications": allowed})


# ---------------------------------------------------------------------------
# ACC — authority traces to an accountable human
# ---------------------------------------------------------------------------

def _acc_01(rule, ctx):
    chain = ctx.credential.delegation_chain
    terminus = chain[-1].holder_type if chain else None
    return ctx.fb.verdict(
        rule, terminus != "human",
        f"delegation_chain for credential {ctx.credential.credential_id} terminates in "
        f"holder_type={terminus!r}, not 'human'.",
        f"delegation_chain terminates in a natural person: {chain[-1].holder_id if chain else ''}"
        f" ({chain[-1].name if chain else ''}).",
        values={"terminus_holder_type": terminus, "depth": len(chain)},
        refs=[_cred_ref(ctx, "delegation_chain", [e.holder_id for e in chain])])


def _acc_02(rule, run, ctx):
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
    chain = ctx.credential.delegation_chain
    principal = run.intent_mandate.principal
    if not chain:
        return ctx.fb.absent(rule, "out_of_scope",
                             f"{run.run_id}: the credential carries no delegation chain "
                             f"(KYA-ACC-01's finding), so there is no terminus to compare.",
                             run_ref=run.run_id)
    if principal.principal_type == "consumer":
        return ctx.fb.absent(
            rule, "out_of_scope",
            f"{run.run_id}: the Intent was signed by a consumer ({principal.principal_id}), whose "
            f"assurance is the consent ceremony, not the operator's delegation chain.",
            run_ref=run.run_id, values={"principal_type": "consumer"})
    terminus = chain[-1].holder_id
    return ctx.fb.verdict(
        rule, terminus != principal.principal_id,
        f"{run.run_id}: delegation_chain terminus {terminus!r} does not match the Intent's "
        f"delegated officer {principal.principal_id!r}.",
        f"{run.run_id}: the delegation chain terminates in the officer who signed the Intent "
        f"({principal.principal_id}).",
        run_ref=run.run_id,
        values={"terminus_holder_id": terminus, "intent_principal_id": principal.principal_id})


def _acc_04(rule, ctx):
    ids = [e.holder_id for e in ctx.credential.delegation_chain]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    return ctx.fb.verdict(
        rule, bool(dupes),
        f"delegation_chain has duplicate holder_id(s): {dupes}.",
        f"No holder appears twice in the {len(ids)}-level delegation chain.",
        values={"duplicates": dupes, "holders": ids})


def _acc_05(rule, ctx):
    depth = len(ctx.credential.delegation_chain)
    max_depth = typed_params(rule).max_depth
    return ctx.fb.verdict(
        rule, depth > max_depth,
        f"delegation_chain depth {depth} exceeds the maximum of {max_depth}.",
        f"delegation_chain depth {depth} is within the maximum of {max_depth}.",
        values={"depth": depth, "max_depth": max_depth})


def _acc_06(rule, ctx):
    """KYA-ACC-06 / F11 — a middle party cannot grant what it does not hold.

    The chain runs agent (level 0) upward to the accountable human, so each
    level is granted its authority BY the level above it. A child holding
    capabilities its parent never had means somebody minted authority mid-chain.

    A chain that records no `granted_capabilities` has nothing to compare and
    is `absent/missing_block` — a list of names is not a record of delegated
    authority, which is exactly why the field exists.
    """
    chain = ctx.credential.delegation_chain
    if len(chain) < 2:
        return ctx.fb.absent(rule, "out_of_scope",
                             f"The delegation chain has {len(chain)} level(s); there is no "
                             f"delegation to compare against its grantor.")
    ungranted = [e.level for e in chain if not e.granted_capabilities]
    problems = []
    for child, parent in zip(chain, chain[1:]):
        if not child.granted_capabilities or not parent.granted_capabilities:
            continue
        if excess := sorted(set(child.granted_capabilities) - set(parent.granted_capabilities)):
            problems.append(f"level {child.level} ({child.holder_id}) holds "
                            f"{', '.join(excess)} which level {parent.level} "
                            f"({parent.holder_id}) does not")
        c_cap = (child.constraints or {}).get("max_transaction_amount")
        p_cap = (parent.constraints or {}).get("max_transaction_amount")
        if c_cap is not None and p_cap is not None and c_cap > p_cap:
            problems.append(f"level {child.level} carries a cap of {c_cap} above level "
                            f"{parent.level}'s {p_cap}")
    if problems:
        return ctx.fb.breach(
            rule, "Delegation grants authority the granting holder does not itself hold: "
                  + "; ".join(problems) + ".", values={"violations": problems})
    if ungranted:
        return ctx.fb.absent(
            rule, "missing_block",
            f"Delegation level(s) {ungranted} record no granted_capabilities, so what each was "
            f"permitted to pass down cannot be compared.",
            missing="kya_credential.delegation_chain[].granted_capabilities",
            values={"levels_without_grants": ungranted})
    return ctx.fb.satisfied(
        rule, f"Each of the {len(chain) - 1} delegation link(s) grants no more than its grantor "
              f"holds.",
        values={"levels": len(chain)},
        refs=[_cred_ref(ctx, "delegation_chain[].granted_capabilities",
                        [e.granted_capabilities for e in chain])])


def _acc_07(rule, ctx):
    """KYA-ACC-07 — the accountable person is one the firm actually authorised.

    ACC-01 asks whether a human is at the end of the chain; this asks whether
    that human had standing to be there. A named individual who is not on the
    operator's signatory list is a delegation nobody at the firm sanctioned.
    """
    chain = ctx.credential.delegation_chain
    if not chain:
        return ctx.fb.absent(rule, "out_of_scope", "The credential carries no delegation chain "
                             "(KYA-ACC-01's finding), so there is no terminus to check.")
    if (operator := ctx.operator) is None:
        return _no_operator(rule, ctx)
    if not operator.get("authorised_signatories"):
        return _no_field(rule, ctx, "operators", operator["operator_id"], "authorised_signatories")
    terminus = chain[-1]
    authorised = {s["principal_id"] for s in operator["authorised_signatories"]}
    return ctx.fb.verdict(
        rule, terminus.holder_id not in authorised,
        f"Chain terminus {terminus.holder_id} ({terminus.name}) is not on "
        f"{operator['operator_id']}'s authorised-signatory list.",
        f"Chain terminus {terminus.holder_id} ({terminus.name}) is an authorised signatory of "
        f"{operator['operator_id']}.",
        values={"terminus": terminus.holder_id, "authorised_signatories": sorted(authorised)})


# ---------------------------------------------------------------------------
# OPF — the operator firm (dossier-level)
# ---------------------------------------------------------------------------

def _opf_01(rule, ctx):
    """A licence OR a live sponsorship.

    Kestrel is not licensed and should not be: it is a technology operator
    whose authority to move money comes from the institution sponsoring it.
    A rule reading "must hold a licence" would fail every non-bank operator by
    construction, which is most of the market this regime exists to cover.
    """
    if (operator := ctx.operator) is None:
        return _no_operator(rule, ctx)
    licence = operator.get("licence_status")
    sponsorship = operator.get("sponsorship") or {}
    licensed = licence in {"active", "current"}
    sponsored = sponsorship.get("status") == "active"
    values = {"operator_id": operator["operator_id"], "licence_status": licence,
              "sponsorship_status": sponsorship.get("status"),
              "sponsoring_institution_id": sponsorship.get("institution_id")}
    return ctx.fb.verdict(
        rule, not (licensed or sponsored),
        f"Operator {operator['operator_id']} holds neither a current licence "
        f"(status={licence!r}) nor an active sponsorship.",
        f"Operator {operator['operator_id']} " + (f"holds a current licence ({licence})."
                                                  if licensed else
                                                  f"operates under an active sponsorship "
                                                  f"from {sponsorship.get('institution_id')}."),
        values=values)


def _opf_02(rule, ctx):
    if (operator := ctx.operator) is None:
        return _no_operator(rule, ctx)
    barring = {"suspended", "wound_down", "revoked", "under_enforcement"}
    standing = operator.get("standing")
    return ctx.fb.verdict(
        rule, standing in barring,
        f"Operator {operator['operator_id']} is in a barring standing ({standing}).",
        f"Operator {operator['operator_id']} is in standing {standing!r}, which does not bar it.",
        values={"operator_id": operator["operator_id"], "standing": standing})


def _opf_03(rule, ctx):
    """KYA-OPF-03 / F14 — the firm changed hands after the credential was issued.

    A credential attests to an operator as it was at issuance. Ownership moving
    afterwards means the entity vouched for is not the entity now running the
    agent, and the credential says nothing about the new one.
    """
    if (operator := ctx.operator) is None:
        return _no_operator(rule, ctx)
    issued = ctx.credential.issued_at[:10]
    after = [c for c in operator.get("ownership_changes", []) if c.get("date", "") > issued]
    return ctx.fb.verdict(
        rule, bool(after),
        f"Control of {operator['operator_id']} changed {len(after)} time(s) after the credential "
        f"was issued on {issued}, with no reissuance.",
        f"No change of control of {operator['operator_id']} is recorded since the credential was "
        f"issued on {issued}.",
        values={"credential_issued_at": issued, "changes": after})


def _opf_04(rule, ctx):
    if (operator := ctx.operator) is None:
        return _no_operator(rule, ctx)
    contact = operator.get("compliance_contact") or {}
    return ctx.fb.verdict(
        rule, not contact.get("name"),
        f"No named compliance contact is on record for {operator['operator_id']}: there is "
        f"nobody for a supervisor to call.",
        f"A named compliance contact is on record for {operator['operator_id']} "
        f"({contact.get('name')}).",
        values={"operator_id": operator["operator_id"], "compliance_contact": contact.get("name")})


# ---------------------------------------------------------------------------
# REG — the agent is declared and classified
# ---------------------------------------------------------------------------

def _reg_01(rule, run, ctx):
    """KYA-REG-01 / F16 — the agent transacted before it was declared.

    An agent with no register entry at all is the strongest form of this
    failure, not a gap in the regulator's data: nobody declared it, and it
    moved money anyway.
    """
    used = _use_date(run)
    if ctx.agent is None:
        return ctx.fb.breach(
            rule, f"{run.run_id} was executed by {ctx.agent_id}, which has no entry in the agent "
                  f"register at all.",
            run_ref=run.run_id, values={"registered_at": None, "used_at": used.isoformat()})
    if not ctx.agent.get("registered_at"):
        return _no_field(rule, ctx, "agents", ctx.agent_id, "registered_at", run.run_id)
    registered = date.fromisoformat(ctx.agent["registered_at"][:10])
    return ctx.fb.verdict(
        rule, registered > used,
        f"{run.run_id} ran on {used.isoformat()}, before the agent was registered on "
        f"{registered.isoformat()}.",
        f"{run.run_id} ran on {used.isoformat()}, after registration on {registered.isoformat()}.",
        run_ref=run.run_id,
        values={"registered_at": registered.isoformat(), "used_at": used.isoformat()})


def _reg_02(rule, ctx):
    if ctx.agent is None:
        return _no_agent(rule, ctx)
    risk = ctx.agent.get("risk_class")
    return ctx.fb.verdict(
        rule, not risk,
        f"No risk classification is declared for {ctx.agent_id}, so no rule that scales with "
        f"risk can be applied to it.",
        f"{ctx.agent_id} is classified {risk!r} "
        f"({ctx.agent.get('classification')}).",
        values={"agent_id": ctx.agent_id, "risk_class": risk,
                "classification": ctx.agent.get("classification")})


def _reg_04(rule, run, ctx):
    if ctx.agent is None:
        return _no_agent(rule, ctx, run.run_id)
    if not ctx.agent.get("authorisation_expires"):
        return _no_field(rule, ctx, "agents", ctx.agent_id, "authorisation_expires", run.run_id)
    expires = date.fromisoformat(ctx.agent["authorisation_expires"][:10])
    used = _use_date(run)
    return ctx.fb.verdict(
        rule, expires < used,
        f"{run.run_id} ran on {used.isoformat()}, after the agent's registration expired on "
        f"{expires.isoformat()}.",
        f"{run.run_id} ran on {used.isoformat()}; the registration is current until "
        f"{expires.isoformat()}.",
        run_ref=run.run_id,
        values={"authorisation_expires": expires.isoformat(), "used_at": used.isoformat()})


def _reg_05(rule, run, ctx):
    if ctx.agent is None:
        return _no_agent(rule, ctx, run.run_id)
    if "registered_purpose_category" not in ctx.agent:
        return _no_field(rule, ctx, "agents", ctx.agent_id, "registered_purpose_category",
                         run.run_id)
    registered = ctx.agent["registered_purpose_category"]
    declared = run.intent_mandate.authorization_scope.purpose_category
    return ctx.fb.verdict(
        rule, registered != declared,
        f"{run.run_id}: mandate purpose_category {declared!r} does not match the registered "
        f"purpose {registered!r} for this agent.",
        f"{run.run_id}: mandate purpose_category {declared!r} matches the registered purpose.",
        run_ref=run.run_id,
        values={"registered_purpose_category": registered, "mandate_purpose_category": declared})


# ---------------------------------------------------------------------------
# TEC — the technical substrate, the half answered from the register
# ---------------------------------------------------------------------------

def _tec_01(rule, run, ctx):
    """KYA-TEC-01 — is a model version declared at all? (F18)

    The weakest of the substrate rules and still worth having: without a
    pinned version you cannot separate a firm's misconfiguration from a
    model's flaw, cannot warn other firms running the same model, and cannot
    see a market-wide monoculture (F67). Whether the declared version is the
    one that actually *ran* is KYA-TEC-02, owned by Provenance.
    """
    declared = run.intent_mandate.agent.model_version
    return ctx.fb.verdict(
        rule, (declared or "").strip().lower() in _PLACEHOLDER_MODEL_VERSIONS,
        f"{run.run_id}: the Intent declares no usable model_version ({declared!r}); its decisions "
        f"cannot be attributed to a specific model.",
        f"{run.run_id}: the Intent pins model_version {declared!r}.",
        run_ref=run.run_id, values={"declared_model_version": declared},
        refs=[EvidenceRef(kind="field", ref="intent_mandate.agent.model_version", value=declared)])


def _tec_03(rule, run, ctx):
    """KYA-TEC-03 — the model the mandate DECLARES is not barred.

    Deliberately the declared version, because that is what lives in KYA's
    evidence block. Whether the model that actually answered was barred is a
    different question against different evidence, and it belongs to Provenance
    (TEC-02) — see kya-ruleset.md Part 3.5 on splitting TEC by evidence rather
    than by topic.
    """
    declared = run.intent_mandate.agent.model_version
    blocked = ctx.blocklist.get(declared)
    return ctx.fb.verdict(
        rule, blocked is not None,
        f"{run.run_id}: declared model {declared!r} was blocklisted on "
        f"{blocked['blocked_at'] if blocked else ''}: {blocked['reason'] if blocked else ''}",
        f"{run.run_id}: declared model {declared!r} is not on the blocklist.",
        run_ref=run.run_id,
        values={"model_version": declared, "blocked_at": blocked and blocked["blocked_at"],
                "reason": blocked and blocked["reason"]})


def _tec_04(rule, run, ctx):
    if ctx.agent is None:
        return _no_agent(rule, ctx, run.run_id)
    declared = run.intent_mandate.agent.model_version
    validated = {v["model_version"] for v in ctx.agent.get("validation_evidence", [])}
    return ctx.fb.verdict(
        rule, declared not in validated,
        f"{run.run_id}: no validation evidence is on file for model {declared!r}, which this "
        f"agent's {ctx.agent.get('risk_class', 'unknown')} risk classification requires.",
        f"{run.run_id}: validation evidence is on file for model {declared!r}.",
        run_ref=run.run_id,
        values={"model_version": declared, "risk_class": ctx.agent.get("risk_class"),
                "validated_versions": sorted(validated)})


# ---------------------------------------------------------------------------
# CAP — capability proportionality
# ---------------------------------------------------------------------------

def _cap_01(rule, ctx):
    caps = ctx.credential.capabilities
    return ctx.fb.verdict(
        rule, not caps,
        f"Credential {ctx.credential.credential_id} has an empty capabilities list.",
        f"Credential {ctx.credential.credential_id} declares {len(caps)} capability(ies).",
        values={"capabilities": caps}, refs=[_cred_ref(ctx, "capabilities", caps)])


def _cap_02(rule, ctx):
    params = typed_params(rule)
    bad = [c for c in ctx.credential.capabilities
           if c not in params.allowed_exact
           and not any(c.startswith(p) for p in params.allowed_prefixes)]
    return ctx.fb.verdict(
        rule, bool(bad),
        f"Capabilities outside the allowed vocabulary: {bad}.",
        f"All {len(ctx.credential.capabilities)} capability(ies) are in the allowed vocabulary.",
        values={"outside_vocabulary": bad, "capabilities": ctx.credential.capabilities})


def _cap_05(rule, ctx):
    """KYA-CAP-05 / F20 — permissions widening quietly across reissuance.

    Growth is not automatically creep: an agent that legitimately gains a new
    function should gain the capability for it. What the rule catches is
    widening that nobody had to justify, so the tolerance is a dial — how many
    new capabilities may appear at one renewal before it needs an explanation.
    """
    if len(ctx.series) < 2:
        return ctx.fb.absent(rule, "out_of_scope",
                             "Only one credential is in the series; there is no reissuance to "
                             "compare.", values={"series_length": len(ctx.series)})
    tolerance = typed_params(rule).max_new_capabilities_per_reissue
    creep, reissues = [], []
    for older, newer in zip(ctx.series, ctx.series[1:]):
        added = sorted(set(newer.capabilities) - set(older.capabilities))
        reissues.append({"from": older.credential_id, "to": newer.credential_id, "added": added})
        if len(added) > tolerance:
            creep.append(f"{older.credential_id} -> {newer.credential_id} added "
                         f"{', '.join(added)}")
    return ctx.fb.verdict(
        rule, bool(creep),
        f"Capabilities widened across reissuance beyond the tolerance of {tolerance}: "
        + "; ".join(creep) + ".",
        f"Across {len(reissues)} reissuance(s) no credential added more than {tolerance} "
        f"capability(ies).",
        values={"reissues": reissues, "tolerance": tolerance})


# ---------------------------------------------------------------------------
# LIF — credential lifecycle
# ---------------------------------------------------------------------------

def _lif_01(rule, run, ctx):
    expires = date.fromisoformat(ctx.credential.expires_at[:10])
    grace = typed_params(rule).grace_period_days
    used = _use_date(run)
    return ctx.fb.verdict(
        rule, used > expires + timedelta(days=grace),
        f"{run.run_id} ran on {used.isoformat()}, after credential "
        f"{ctx.credential.credential_id} expired on {expires.isoformat()} (grace {grace} days).",
        f"{run.run_id} ran on {used.isoformat()}, within credential "
        f"{ctx.credential.credential_id}'s validity (expires {expires.isoformat()}).",
        run_ref=run.run_id,
        values={"expires_at": expires.isoformat(), "used_at": used.isoformat(),
                "grace_period_days": grace})


def _lif_02(rule, ctx):
    issued = date.fromisoformat(ctx.credential.issued_at[:10])
    expires = date.fromisoformat(ctx.credential.expires_at[:10])
    return ctx.fb.verdict(
        rule, not issued < expires,
        f"Credential {ctx.credential.credential_id} issued_at={issued.isoformat()} does not "
        f"precede expires_at={expires.isoformat()}.",
        f"Credential {ctx.credential.credential_id} was issued {issued.isoformat()} and expires "
        f"{expires.isoformat()}.",
        values={"issued_at": issued.isoformat(), "expires_at": expires.isoformat()})


def _lif_03(rule, ctx):
    issued = date.fromisoformat(ctx.credential.issued_at[:10])
    expires = date.fromisoformat(ctx.credential.expires_at[:10])
    min_days = typed_params(rule).min_validity_days
    span = (expires - issued).days
    return ctx.fb.verdict(
        rule, span < min_days,
        f"Credential {ctx.credential.credential_id} validity window is {span} days, below the "
        f"{min_days}-day minimum.",
        f"Credential {ctx.credential.credential_id} validity window is {span} days, at or above "
        f"the {min_days}-day minimum.",
        values={"validity_days": span, "min_validity_days": min_days})


def _lif_04(rule, ctx):
    """KYA-LIF-04 / F21 — two live credentials for one agent.

    Usually a renewal issued before the predecessor was revoked, which is how
    it happens in practice and why it is worth detecting: for the overlap
    window the agent has two valid identities, and revoking one does not stop
    it.
    """
    if len(ctx.series) < 2:
        return ctx.fb.absent(rule, "out_of_scope",
                             "Only one credential is in the series; nothing can overlap with it.",
                             values={"series_length": len(ctx.series)})
    overlaps = []
    for a, b in zip(ctx.series, ctx.series[1:]):
        if b.issued_at < a.expires_at:
            overlaps.append(f"{a.credential_id} (to {a.expires_at[:10]}) and "
                            f"{b.credential_id} (from {b.issued_at[:10]})")
    return ctx.fb.verdict(
        rule, bool(overlaps),
        f"{len(overlaps)} pair(s) of credentials for this agent are valid simultaneously: "
        + "; ".join(overlaps) + ".",
        f"No two of the {len(ctx.series)} credentials in the series are valid at the same time.",
        values={"overlaps": overlaps,
                "series": [(c.credential_id, c.issued_at[:10], c.expires_at[:10])
                           for c in ctx.series]})


def _lif_05(rule, ctx):
    """Staleness of the check, not its answer.

    An institution that cannot say when it last confirmed a credential was
    live has a control gap whatever the credential turns out to be.
    """
    checked = ctx.credential.revocation_checked_at
    if not checked:
        return ctx.fb.absent(
            rule, "missing_block",
            "The submission does not say when the credential's revocation status was last "
            "checked, so its freshness cannot be evaluated.",
            missing="kya_credential.revocation_checked_at")
    max_age = typed_params(rule).max_age_days
    age = (ctx.submitted_at - date.fromisoformat(checked[:10])).days
    return ctx.fb.verdict(
        rule, age > max_age,
        f"Revocation status was last checked {age} days before submission; the maximum is "
        f"{max_age}.",
        f"Revocation status was checked {checked[:10]}, {age} day(s) before submission, within "
        f"the {max_age}-day maximum.",
        values={"revocation_checked_at": checked[:10], "age_days": age, "max_age_days": max_age,
                "as_of": ctx.submitted_at.isoformat()})


_DOSSIER_CHECKERS = {
    "issuer_min_trust_level": _iss_03,
    "issuer_reaccreditation_not_stale": _iss_04,
    "issuer_authorised_for_classification": _iss_05,
    "delegation_chain_terminates_in_human": _acc_01,
    "delegation_chain_no_duplicate_holders": _acc_04,
    "delegation_chain_max_depth": _acc_05,
    "delegation_no_grant_exceeds_holder": _acc_06,
    "delegation_terminus_is_authorised_signatory": _acc_07,
    "operator_licence_current": _opf_01,
    "operator_standing_not_barring": _opf_02,
    "no_unnotified_change_of_control": _opf_03,
    "compliance_contact_on_record": _opf_04,
    "risk_classification_declared": _reg_02,
    "credential_capabilities_non_empty": _cap_01,
    "capability_vocabulary_allowlist": _cap_02,
    "capability_creep_across_reissuance": _cap_05,
    "credential_issued_before_expiry": _lif_02,
    "credential_min_validity_window": _lif_03,
    "no_simultaneous_credentials": _lif_04,
    "revocation_check_not_stale": _lif_05,
}

_RUN_CHECKERS = {
    "delegation_terminus_matches_intent_principal": _acc_02,
    "agent_registered_before_first_use": _reg_01,
    "agent_registration_current": _reg_04,
    "registered_purpose_matches_mandate": _reg_05,
    "model_version_pinned_to_mandate": _tec_01,
    "declared_model_not_blocklisted": _tec_03,
    "model_validation_evidence_on_file": _tec_04,
    "credential_not_expired": _lif_01,
}

# Kept as one name so tests and docs can say "the KYA floor evaluates these".
_POLICY_CHECKERS = {**_DOSSIER_CHECKERS, **_RUN_CHECKERS}


def run_policy_checks(dossier: LoadedDossier, ruleset: Ruleset, *,
                      ctx: PolicyContext | None = None) -> list[Fact]:
    """Every KYA rule accounted for: crypto and Provenance-owned types are
    listed as handled elsewhere; everything else active must have a checker
    here or the dispatcher raises; draft rules emit `absent/rule_draft`."""
    ctx = ctx or build_policy_context(dossier)
    return evaluate_ruleset(
        ruleset, builder=ctx.fb, ctx=ctx, runs=dossier.runs,
        dossier_checkers=_DOSSIER_CHECKERS, run_checkers=_RUN_CHECKERS,
        handled_elsewhere=CRYPTO_HANDLED_TYPES | PROVENANCE_OWNED_TYPES,
        module="agents/kya_checks.py")
