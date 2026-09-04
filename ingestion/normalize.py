"""Intake: a `LoadedDossier` in, an `EvidencePack` out. Code only, no model.

`normalize_dossier()` is what the triage graph's ingest node calls. It
verifies every signature and chain link (ingestion/verify.py), resolves the
six registries, computes the shared statistics once and records which
submission blocks are present. It evaluates no rules beyond the eight
cryptographic/chain ones — rules belong to agents.

This module also owns the shape a dossier takes in the ledger:
`submission_payload()` is what `case_submitted` carries, and
`dossier_from_submission()` rebuilds a `LoadedDossier` from it, so the graph
reads the case by id from the ledger and never from a client-supplied path.
The loader verified the run index against the file digests at the door;
rebuilt from the ledger there are no files, so the rebuild re-validates the
schema and index membership and the hash chain vouches for the rest.

A schema-invalid submission raises — garbage that cannot be normalised is a
different failure class from a submission with something wrong in it, which
comes back as facts.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

from pydantic import ValidationError

from data.issuers import load_issuer_registry
from data.registries import load_agents, load_institutions, load_merchants, load_operators
from ingestion.verify import VerificationContext, build_verification_context, verify_dossier
from registry.loader import load_drift_ruleset
from schemas import (
    AmountProfile,
    ControlProfile,
    CounterpartyProfile,
    DriftBaseline,
    EvidencePack,
    RegistryResolution,
    Ruleset,
    SubmissionProfile,
    TimingProfile,
    typed_params,
)
from schemas.dossier import Dossier, LoadedDossier, Run
from schemas.transaction import TransactionLogEntry


class SubmissionInvalid(ValueError):
    """The submission does not validate against the dossier schema."""


# ---------------------------------------------------------------------------
# the ledger shape
# ---------------------------------------------------------------------------

def submission_payload(d: LoadedDossier, *, operators: dict | None = None,
                       institutions: dict | None = None) -> dict:
    """What `case_submitted` carries: the dossier as filed, its runs, the
    institution's ledger, and a `firm` block resolved from the registries so
    the projection and the queue can name who is being supervised without a
    lookup. Ground truth is never part of it."""
    if d.raw_dossier is None:
        raise ValueError(f"{d.dossier.dossier_id}: cannot submit a dossier that carries no raw "
                         f"submission — the ledger records what was filed, not a model dump")
    operators = operators if operators is not None else load_operators()
    institutions = institutions if institutions is not None else load_institutions()
    op = operators.get(d.dossier.operator_id, {})
    inst = institutions.get(d.dossier.institution_id, {})
    return {
        "case_id": d.dossier.dossier_id,
        "firm": {
            "name": op.get("legal_name", d.dossier.operator_id),
            "trading_name": op.get("trading_name"),
            "sector": op.get("sector", "unknown"),
            "hq": op.get("hq", "unknown"),
            "operator_id": d.dossier.operator_id,
            "institution_id": d.dossier.institution_id,
            "institution_name": inst.get("legal_name", d.dossier.institution_id),
            "agent_id": d.dossier.agent_id,
        },
        "dossier": d.raw_dossier,
        "runs": [d.raw_runs[r.run_id] for r in d.runs],
        "transaction_history": [t.model_dump(exclude_none=True) for t in d.transaction_history],
    }


def dossier_from_submission(payload: dict) -> LoadedDossier:
    try:
        dossier = Dossier.model_validate(payload["dossier"])
        runs = [Run.model_validate(r) for r in payload.get("runs", [])]
        txns = [TransactionLogEntry.model_validate(t) for t in payload.get("transaction_history", [])]
        loaded = LoadedDossier(
            dossier=dossier, runs=runs, transaction_history=txns, ground_truth=None,
            raw_dossier=payload["dossier"], raw_runs={r["run_id"]: r for r in payload.get("runs", [])},
        )
    except (ValidationError, KeyError, TypeError) as exc:
        raise SubmissionInvalid(f"submission does not validate as a dossier:\n{exc}") from exc
    return loaded


# ---------------------------------------------------------------------------
# the evidence pack
# ---------------------------------------------------------------------------

def _present(value) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, dict, str)):
        return len(value) > 0
    return True


def _run_blocks(run: Run) -> dict[str, bool]:
    cc, cart, payment = run.consent_ceremony, run.cart, run.payment
    ctx = run.construction_context
    return {
        "cart": cart is not None,
        "payment": payment is not None,
        "consent_ceremony": cc is not None,
        "rendered_values": bool(cc and cc.rendered_values is not None),
        "selection_context": ctx.selection_context is not None,
        "tool_calls": _present(ctx.tool_calls),
        "result_excerpt": any(tc.result_excerpt is not None for tc in ctx.tool_calls),
        "controls_evaluated": _present(run.controls_evaluated),
        "payee": bool(payment and payment.payee is not None),
        "sub_merchant": bool(cart and cart.merchant.sub_merchant is not None),
        "merchant_region": bool(cart and cart.merchant.region),
        "usage": run.intent_mandate.authorization_scope.usage is not None,
    }


def _dossier_blocks(d: LoadedDossier) -> dict[str, bool]:
    x = d.dossier
    return {
        "agent_card": x.agent_card is not None,
        "credential_history": _present(x.credential_history),
        "change_log": _present(x.change_log),
        "controls_operator_declared": _present(x.controls.operator_declared),
        "controls_institution_declared": _present(x.controls.institution_declared),
        "run_index": _present(x.run_index),
        "transaction_history": _present(d.transaction_history),
        "revocation_checked_at": x.kya_credential.revocation_checked_at is not None,
        "delegation_grants": any(e.granted_capabilities for e in x.kya_credential.delegation_chain),
    }


def _registries(d: LoadedDossier, *, agents, operators, institutions, issuers, merchants
                ) -> RegistryResolution:
    x = d.dossier
    agent = agents.get(x.agent_id)
    op = operators.get(x.operator_id)
    inst = institutions.get(x.institution_id)
    issuer = issuers.get(x.kya_credential.issuer.issuer_id)
    payees = {t.counterparty_id for t in d.transaction_history} | {
        r.cart.merchant.merchant_id for r in d.runs if r.cart}
    return RegistryResolution(
        institution=inst is not None, operator=op is not None, agent=agent is not None,
        issuer=issuer is not None,
        institution_name=inst.get("legal_name") if inst else None,
        operator_name=op.get("legal_name") if op else None,
        agent_classification=agent.get("classification") if agent else None,
        risk_class=agent.get("risk_class") if agent else None,
        unresolved_merchants=sorted(p for p in payees if p not in merchants),
    )


def _submission(d: LoadedDossier) -> SubmissionProfile:
    x = d.dossier
    sc = x.submission_context
    return SubmissionProfile(
        purpose=x.submission_purpose, environment=sc.environment,
        runs_executed_total=sc.runs_executed_total, runs_submitted=sc.runs_submitted,
        runs_filed=len(d.runs),
        deployment_model_version=sc.deployment_target.model_version,
        deployment_prompt_release_ref=sc.deployment_target.prompt_release_ref,
        deployment_tool_servers=list(sc.deployment_target.tool_servers),
        observed_model_versions=sorted({r.construction_context.model.observed_version for r in d.runs}),
        observed_release_refs=sorted({r.construction_context.policy_version.release_ref for r in d.runs}),
        observed_tool_servers=sorted({tc.server_id for r in d.runs
                                      for tc in r.construction_context.tool_calls}),
    )


def _in_window(t: TransactionLogEntry, start: datetime, end: datetime) -> bool:
    ts = datetime.fromisoformat(t.timestamp)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=start.tzinfo)
    return start <= ts <= end


def _counterparties(d: LoadedDossier, merchants: dict) -> list[CounterpartyProfile]:
    by_cp: dict[str, list[TransactionLogEntry]] = defaultdict(list)
    for t in d.transaction_history:
        by_cp[t.counterparty_id].append(t)
    settled_total = sum(t.amount for t in d.transaction_history if t.status == "settled") or 1.0
    out = []
    for cp, rows in by_cp.items():
        settled = [t for t in rows if t.status == "settled"]
        record = merchants.get(cp)
        names = Counter(t.counterparty_name for t in rows)
        out.append(CounterpartyProfile(
            counterparty_id=cp, name=names.most_common(1)[0][0],
            count=len(rows), total=round(sum(t.amount for t in settled), 2),
            share=round(sum(t.amount for t in settled) / settled_total, 4),
            in_window_count=sum(1 for t in rows if t.run_ref),
            in_window_total=round(sum(t.amount for t in settled if t.run_ref), 2),
            first_seen=min(t.timestamp for t in rows), last_seen=max(t.timestamp for t in rows),
            mccs=sorted({t.mcc for t in rows}), registered=record is not None,
            beneficial_owner=record.get("beneficial_owner") if record else None,
            watchlist_flags=list(record.get("watchlist_flags", [])) if record else [],
            registry_first_seen=record.get("first_seen") if record else None,
        ))
    return sorted(out, key=lambda c: (-c.total, c.counterparty_id))


def _statistics(d: LoadedDossier, drift_ruleset: Ruleset
                ) -> tuple[TimingProfile, AmountProfile, DriftBaseline]:
    from agents import drift_stats, log_stats  # pure pandas, no model

    rule = next((r for r in drift_ruleset.rules
                 if r.type == "behavioral_drift_detected" and r.status == "active"), None)
    params = typed_params(rule) if rule else None
    window_days = params.baseline_window_days if params else 30
    minimum = params.min_total_transactions if params else 30
    n = len(d.transaction_history)
    if n == 0:
        return TimingProfile(), AmountProfile(), DriftBaseline(
            baseline_window_days=window_days, min_total_transactions=minimum, sufficient=False)

    df = log_stats.to_dataframe(d.transaction_history)
    hours = df["timestamp"].apply(lambda ts: ts.hour)
    weekdays = df["timestamp"].apply(lambda ts: ts.strftime("%a"))
    velocity = log_stats.velocity_stats(df)
    timing = TimingProfile(
        hour_histogram={str(h): int(c) for h, c in hours.value_counts().sort_index().items()},
        weekday_histogram={str(w): int(c) for w, c in weekdays.value_counts().items()},
        off_hours_share=round(float(((hours < 8) | (hours >= 18)).mean()), 4),
        min_gap_hours=velocity["min_gap_hours"], median_gap_hours=velocity["median_gap_hours"],
        gaps_under_1_hour=velocity["gaps_under_1_hour"],
    )
    amounts = AmountProfile(**log_stats.amount_stats(df))

    baseline, comparison = drift_stats.split_baseline(df, baseline_window_days=window_days)
    sufficient = n >= minimum and not baseline.empty and not comparison.empty
    drift = DriftBaseline(
        baseline_window_days=window_days, min_total_transactions=minimum, sufficient=sufficient,
        baseline_count=len(baseline), comparison_count=len(comparison),
        amount_shift=drift_stats.amount_shift(baseline, comparison) if sufficient else {},
        frequency_shift=drift_stats.frequency_shift(baseline, comparison) if sufficient else {},
        counterparty_mix_psi=(drift_stats.distribution_psi(baseline, comparison, "counterparty_id")
                              if sufficient else None),
        mcc_mix_psi=drift_stats.distribution_psi(baseline, comparison, "mcc") if sufficient else None,
    )
    return timing, amounts, drift


def _controls(d: LoadedDossier) -> ControlProfile:
    c = d.dossier.controls
    by_control: dict[str, dict[str, int]] = defaultdict(lambda: {"passed": 0, "triggered": 0,
                                                                  "not_evaluated": 0, "overridden": 0})
    evaluations = triggered = overridden = not_evaluated = 0
    for r in d.runs:
        for e in r.controls_evaluated:
            evaluations += 1
            by_control[e.control_id][e.outcome] += 1
            if e.outcome == "triggered":
                triggered += 1
            if e.outcome == "not_evaluated":
                not_evaluated += 1
            if e.override is not None:
                overridden += 1
                by_control[e.control_id]["overridden"] += 1
    return ControlProfile(
        operator_declared=[x.control_id for x in c.operator_declared],
        institution_declared=[x.control_id for x in c.institution_declared],
        evaluations=evaluations, triggered=triggered, overridden=overridden,
        not_evaluated=not_evaluated, by_control=dict(by_control),
        runs_without_evaluation=[r.run_id for r in d.runs if not r.controls_evaluated],
    )


def normalize_dossier(
    d: LoadedDossier, *, context: VerificationContext | None = None,
    drift_ruleset: Ruleset | None = None,
    agents: dict | None = None, operators: dict | None = None, institutions: dict | None = None,
    issuers: dict | None = None, merchants: dict | None = None,
) -> EvidencePack:
    """Everything intake establishes, once. Registries and the verification
    context are injectable so the sandbox and the tests can run intake
    against a different regulator-side state."""
    agents = agents if agents is not None else load_agents()
    operators = operators if operators is not None else load_operators()
    institutions = institutions if institutions is not None else load_institutions()
    issuers = issuers if issuers is not None else load_issuer_registry()
    merchants = merchants if merchants is not None else load_merchants()
    context = context or build_verification_context(issuers=issuers)
    drift_ruleset = drift_ruleset or load_drift_ruleset()

    x = d.dossier
    sc = x.submission_context
    start, end = datetime.fromisoformat(sc.executed_from), datetime.fromisoformat(sc.executed_to)
    in_window = [t for t in d.transaction_history if _in_window(t, start, end)]
    facts, integrity = verify_dossier(d, context)
    timing, amounts, drift = _statistics(d, drift_ruleset)

    return EvidencePack(
        dossier_id=x.dossier_id, agent_id=x.agent_id, operator_id=x.operator_id,
        institution_id=x.institution_id, submitted_at=sc.submitted_at,
        executed_from=sc.executed_from, executed_to=sc.executed_to,
        run_ids=[r.run_id for r in d.runs],
        runs_by_outcome=dict(Counter(r.outcome for r in d.runs)),
        transactions_total=len(d.transaction_history),
        transactions_in_window=len(in_window),
        transactions_trailing=len(d.transaction_history) - len(in_window),
        in_window_without_run=[t.transaction_id for t in in_window if not t.run_ref],
        blocks=_dossier_blocks(d),
        run_blocks={r.run_id: _run_blocks(r) for r in d.runs},
        submission=_submission(d),
        registries=_registries(d, agents=agents, operators=operators, institutions=institutions,
                               issuers=issuers, merchants=merchants),
        integrity=integrity,
        counterparties=_counterparties(d, merchants),
        timing=timing, amounts=amounts, drift=drift,
        controls=_controls(d),
        ingestion_facts=facts,
    )
