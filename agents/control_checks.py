"""Deterministic checkers for the 15 CTL-* rules.

The other rulebooks ask whether the *agent* misbehaved. These ask whether the
*firm's own controls worked* — which is the question a supervisor is actually
empowered to act on, and the difference between a supervision tool and a
detection tool.

Control evidence is split across the dossier (which controls were declared, by
whom) and every run (what each evaluation decided). Neither half means anything
alone, so the rules split the same way: the repository, override-rate and
audit-log families are dossier-level, one fact each; the disposition and
effectiveness families are run-level, one fact per run, because "a blocking
control triggered and the payment settled anyway" is a statement about a run.

Two rules need care:

`CTL-EFF-01` consumes the OTHER agents' findings — it asks whether a control
that should have triggered did — so Control Assurance runs after the peer
fan-out, not inside it. `peer_breaches` carries those in. Given `None` (not
yet supplied) it emits `absent/awaiting_peers`; given `{}` (supplied, nothing
breached) every run is `satisfied`. The old contract could not tell those
apart, and the difference is the whole point of the rule.

`CTL-EFF-03` is a rate, and a rate over four evaluations is noise. Below
`min_evaluations` it emits `absent/insufficient_history` rather than a number
the sample cannot support.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from schemas import EvidenceRef, Fact, Rule, Ruleset, typed_params
from schemas.dossier import LoadedDossier, Run

from .facts import FactBuilder, evaluate_ruleset

DOMAIN = "control_assurance"


@dataclass
class ControlContext:
    fb: FactBuilder
    dossier: LoadedDossier
    controls: dict[str, object]                 # control_id -> DeclaredControl, both owners
    peers: dict[str, set[str]] | None           # run_id -> failure ids other specialists confirmed
    evaluations: list[tuple[str, object]] = field(default_factory=list)  # (run_id, execution)


def build_context(d: LoadedDossier, peers: dict[str, set[str]] | None) -> ControlContext:
    c = d.dossier.controls
    return ControlContext(
        fb=FactBuilder(d.dossier.dossier_id, DOMAIN), dossier=d,
        controls={x.control_id: x for x in [*c.operator_declared, *c.institution_declared]},
        peers=peers,
        evaluations=[(r.run_id, e) for r in d.runs for e in r.controls_evaluated],
    )


def _ctl_ref(e) -> EvidenceRef:
    return EvidenceRef(kind="control", ref=e.control_id, value=e.outcome)


def _no_evaluations(rule: Rule, run: Run, ctx: ControlContext) -> Fact:
    return ctx.fb.absent(
        rule, "out_of_scope",
        f"{run.run_id} records no control evaluations, so there is no disposition to inspect "
        f"(CTL-DIS-01 says whether that is itself a failure).", run_ref=run.run_id)


def _triggered_blocking(run: Run, ctx: ControlContext) -> list:
    """The evaluations where a blocking control said no."""
    return [e for e in run.controls_evaluated
            if e.outcome == "triggered"
            and (c := ctx.controls.get(e.control_id)) is not None and c.enforcement == "blocking"]


# ---------------------------------------------------------------------------
# REP — the controls repository (dossier-level)
# ---------------------------------------------------------------------------

def _rep_01(rule, ctx):
    ids = sorted(ctx.controls)
    return ctx.fb.verdict(
        rule, not ids,
        "No control set is declared for this agent: every claim about how its risk is managed "
        "rests on assertion alone.",
        f"{len(ids)} control(s) are declared across operator and institution.",
        values={"declared": ids})


def _rep_02(rule, ctx):
    required = set(typed_params(rule).required_risks)
    covered = {c.risk_addressed for c in ctx.controls.values()}
    missing = sorted(required - covered)
    return ctx.fb.verdict(
        rule, bool(missing),
        f"The mandate creates risks with no declared control: {', '.join(missing)}.",
        f"Every risk the ruleset requires a control for has one declared "
        f"({', '.join(sorted(required)) or 'none required'}).",
        values={"uncontrolled_risks": missing, "required": sorted(required),
                "declared_risks": sorted(covered)})


def _rep_03(rule, ctx):
    unversioned = sorted(c.control_id for c in ctx.controls.values() if not c.version)
    return ctx.fb.verdict(
        rule, bool(unversioned),
        f"Controls carry no version, so what ran cannot be pinned: {', '.join(unversioned)}.",
        "Every declared control carries a version.",
        values={"unversioned": unversioned})


def _rep_04(rule, ctx):
    undeclared = sorted(c.control_id for c in ctx.controls.values()
                        if c.enforcement not in {"blocking", "advisory"})
    return ctx.fb.verdict(
        rule, bool(undeclared),
        f"Controls do not declare an enforcement mode: {', '.join(undeclared)}.",
        "Every declared control states whether it blocks or advises.",
        values={"undeclared": undeclared})


# ---------------------------------------------------------------------------
# DIS — the disposition engine (run-level)
# ---------------------------------------------------------------------------

def _dis_01(rule, run, ctx):
    # A run that moved money without any control looking at it bypassed the
    # checkpoint entirely, which makes every other rule here blind to it.
    n = len(run.controls_evaluated)
    if n == 0 and run.payment is None:
        return ctx.fb.absent(
            rule, "out_of_scope",
            f"{run.run_id} ({run.outcome}) authorised no payment and evaluated no control; "
            f"there was no action to evaluate.", run_ref=run.run_id)
    return ctx.fb.verdict(
        rule, n == 0,
        f"{run.run_id} authorised a payment with no control evaluation at all.",
        f"{run.run_id}: {n} control(s) evaluated"
        + (" before the payment was authorised." if run.payment else
           f"; the run ended {run.outcome} with no payment."),
        run_ref=run.run_id, values={"evaluations": n, "payment": run.payment is not None},
        refs=[_ctl_ref(e) for e in run.controls_evaluated])


def _dis_02(rule, run, ctx):
    if not run.controls_evaluated:
        return _no_evaluations(rule, run, ctx)
    valid = {"passed", "triggered", "not_evaluated"}
    bad = [e.control_id for e in run.controls_evaluated if e.outcome not in valid]
    return ctx.fb.verdict(
        rule, bool(bad),
        f"{run.run_id}: {len(bad)} control evaluation(s) record no disposition ({', '.join(bad)}).",
        f"{run.run_id}: every one of {len(run.controls_evaluated)} evaluation(s) records a "
        f"disposition.",
        run_ref=run.run_id, values={"undecided": bad},
        refs=[_ctl_ref(e) for e in run.controls_evaluated])


def _dis_03(rule, run, ctx):
    # An override IS the human decision on a triggered control. One recorded
    # without a named decider is the escalation path existing on paper only.
    if not run.controls_evaluated:
        return _no_evaluations(rule, run, ctx)
    anonymous = [e.control_id for e in run.controls_evaluated
                 if e.override is not None and not e.override.by]
    overrides = [e.control_id for e in run.controls_evaluated if e.override is not None]
    return ctx.fb.verdict(
        rule, bool(anonymous),
        f"{run.run_id}: {len(anonymous)} escalation(s) carry no recorded human decision "
        f"({', '.join(anonymous)}).",
        f"{run.run_id}: " + (f"every override names its decider ({', '.join(overrides)})."
                             if overrides else "no control was escalated to a human."),
        run_ref=run.run_id, values={"overrides": overrides, "anonymous": anonymous})


def _dis_04(rule, run, ctx):
    """F73 — it fired, it held, and the payment went through anyway.

    No override, so nobody ever claimed the authority to let it through. That
    is what makes this worse than CTL-EFF-04's overridden case and why it
    carries weight 1.0: an overridden control is a conduct question with a name
    attached; this one is a system that does not do what it says.
    """
    rejected = [e.control_id for e in _triggered_blocking(run, ctx) if e.override is None]
    if not rejected:
        return ctx.fb.satisfied(
            rule, f"{run.run_id}: no blocking control rejected the action"
                  + (", so there was nothing that settlement could have ignored."
                     if run.payment else "."),
            run_ref=run.run_id, values={"rejected": [], "payment": run.payment is not None})
    if run.payment is None:
        # The control said no and nothing moved. This is the control working,
        # and it is a fact worth recording rather than a case the rule skips:
        # a blocked run is the strongest evidence a blocking control is real.
        return ctx.fb.satisfied(
            rule, f"{run.run_id}: {', '.join(rejected)} rejected the action and no payment was "
                  f"authorised — the control held.",
            run_ref=run.run_id, values={"rejected": rejected, "payment": False},
            refs=[_ctl_ref(e) for e in _triggered_blocking(run, ctx)])
    return ctx.fb.breach(
        rule, f"{run.run_id}: a blocking control rejected the action and the payment settled "
              f"anyway ({', '.join(rejected)}).",
        run_ref=run.run_id, values={"rejected": rejected, "payment": True},
        refs=[_ctl_ref(e) for e in _triggered_blocking(run, ctx)])


# ---------------------------------------------------------------------------
# EFF — control effectiveness. The heart of the ruleset.
# ---------------------------------------------------------------------------

# risk_addressed -> the failure ids that prove that risk materialised. Keyed on
# the coverage model's vocabulary because that is what peers report in; the
# rule -> failure mapping lives with the rulebooks.
RISK_EVIDENCE = {
    "stated_budget_cap": {"F42"}, "per_transaction_cap": {"F42"},
    "category_match": {"F44"}, "counterparty_allowlist": {"F45"},
    "shopper_confirmation": {"F24"}, "buyer_confirmation_required": {"F24"},
    "mandate_single_use": {"F50"}, "cumulative_cap": {"F43"},
}


def _eff_01(rule, run, ctx):
    """F71 — a control existed, should have fired, and did not.

    `peers` is what the other specialists found. That is the only way to know a
    control *should* have triggered: the breach it was meant to catch is a fact
    somebody else established. A control marked `passed` on a run where its own
    risk breached is a control that is on paper, not in the system.
    """
    if ctx.peers is None:
        return ctx.fb.absent(
            rule, "awaiting_peers",
            f"{run.run_id}: whether a control should have triggered depends on the other "
            f"specialists' findings, which have not been supplied.",
            missing="peer findings", run_ref=run.run_id)
    if not run.controls_evaluated:
        return _no_evaluations(rule, run, ctx)
    breached = ctx.peers.get(run.run_id, set())
    silent = []
    for e in run.controls_evaluated:
        c = ctx.controls.get(e.control_id)
        if c is None or e.outcome != "passed":
            continue
        if RISK_EVIDENCE.get(c.risk_addressed, set()) & breached:
            silent.append(f"{e.control_id} ({c.risk_addressed})")
    return ctx.fb.verdict(
        rule, bool(silent),
        f"{run.run_id}: {len(silent)} control(s) recorded `passed` on a run where the very risk "
        f"they address had breached: {', '.join(silent)}.",
        f"{run.run_id}: no control passed a risk that materialised"
        + (f" (peers found {', '.join(sorted(breached))})." if breached else "."),
        run_ref=run.run_id,
        values={"silent_controls": silent, "peer_failures": sorted(breached)})


def _eff_02(rule, run, ctx):
    if not run.controls_evaluated:
        return _no_evaluations(rule, run, ctx)
    bad = [e.control_id for e in run.controls_evaluated
           if e.override is not None and not (e.override.by and e.override.reason)]
    overrides = [e.control_id for e in run.controls_evaluated if e.override is not None]
    return ctx.fb.verdict(
        rule, bool(bad),
        f"{run.run_id}: {len(bad)} override(s) carry no authority or no reason "
        f"({', '.join(bad)}).",
        f"{run.run_id}: " + (f"every override records who and why ({', '.join(overrides)})."
                             if overrides else "nothing was overridden."),
        run_ref=run.run_id, values={"overrides": overrides, "unattributed": bad})


def _eff_03(rule, ctx):
    params = typed_params(rule)
    evals = ctx.evaluations
    triggered = [(rid, e) for rid, e in evals if e.outcome == "triggered"]
    values = {"evaluations": len(evals), "triggered": len(triggered),
              "min_evaluations": params.min_evaluations,
              "max_override_rate": params.max_override_rate}
    if len(evals) < params.min_evaluations:
        # A rate over a handful of evaluations is noise. Say so rather than
        # report a number the sample cannot support.
        return ctx.fb.absent(
            rule, "insufficient_history",
            f"{len(evals)} control evaluation(s) are too few to support an override rate "
            f"(minimum {params.min_evaluations}).", missing="controls_evaluated", values=values)
    if not triggered:
        # The evidence is present and complete; there is simply no denominator.
        # This is non-applicability, not an evidence gap that should block an
        # otherwise complete authorisation dossier.
        return ctx.fb.absent(
            rule, "out_of_scope",
            f"{len(evals)} control evaluation(s) were filed, but none triggered; "
            "an override rate is not applicable.", values=values)
    overridden = [(rid, e) for rid, e in triggered if e.override is not None]
    rate = len(overridden) / len(triggered)
    values.update({"overridden": len(overridden), "rate": round(rate, 4),
                   "runs": [rid for rid, _ in overridden]})
    return ctx.fb.verdict(
        rule, rate > params.max_override_rate,
        f"{len(overridden)} of {len(triggered)} triggered controls were overridden ({rate:.0%}), "
        f"above the {params.max_override_rate:.0%} maximum — override is operating as routine "
        f"rather than exception.",
        f"{len(overridden)} of {len(triggered)} triggered controls were overridden ({rate:.0%}), "
        f"within the {params.max_override_rate:.0%} maximum.",
        values=values, refs=[EvidenceRef(kind="statistic", ref="override_rate", value=round(rate, 4))])


def _eff_04(rule, run, ctx):
    """A blocking control triggered and settlement happened after an override.

    The same execution shape as CTL-DIS-04, partitioned on whether an override
    was recorded, so the two never double-report one transaction. Here somebody
    took a decision and signed their name to it — which makes this a conduct
    question rather than a systems failure.
    """
    overridden = [(e.control_id, e.override.by) for e in _triggered_blocking(run, ctx)
                  if e.override is not None]
    settled = run.payment is not None
    return ctx.fb.verdict(
        rule, bool(overridden) and settled,
        f"{run.run_id}: a blocking control triggered and the transaction settled after an "
        f"override ({'; '.join(f'{cid} overridden by {by}' for cid, by in overridden)}).",
        f"{run.run_id}: " + (f"{', '.join(cid for cid, _ in overridden)} was overridden but no "
                             f"payment was authorised." if overridden else
                             "no blocking control was overridden into settlement."),
        run_ref=run.run_id,
        values={"overridden": [cid for cid, _ in overridden],
                "overridden_by": sorted({by for _, by in overridden}), "payment": settled},
        refs=[_ctl_ref(e) for e in run.controls_evaluated if e.override is not None])


# ---------------------------------------------------------------------------
# LOG — the audit log (dossier-level)
# ---------------------------------------------------------------------------

def _log_01(rule, ctx):
    """Present, and actually covering the period it claims to.

    Two ways a log fails this. It can be empty. Or it can have a hole — and a
    hole is not a neutral absence: the stretch nobody logged is exactly where a
    supervisor would look first.
    """
    d = ctx.dossier
    sc = d.dossier.submission_context
    if not d.runs:
        return ctx.fb.breach(rule, "No runs were submitted for the declared reporting period.",
                             values={"runs": 0})
    max_gap = typed_params(rule).max_gap_days
    days = sorted({datetime.fromisoformat(r.started_at).date() for r in d.runs})
    start = datetime.fromisoformat(sc.executed_from).date()
    end = datetime.fromisoformat(sc.executed_to).date()
    gaps = [f"{a.isoformat()}..{b.isoformat()} ({(b - a).days}d)"
            for a, b in zip([start, *days], [*days, end]) if (b - a).days > max_gap]
    values = {"gaps": gaps, "max_gap_days": max_gap, "runs": len(d.runs),
              "declared_period": [start.isoformat(), end.isoformat()]}
    return ctx.fb.verdict(
        rule, bool(gaps),
        f"The submitted log has {len(gaps)} gap(s) longer than {max_gap} days inside the "
        f"declared period: {', '.join(gaps)}.",
        f"{len(d.runs)} runs cover the declared period {start.isoformat()}..{end.isoformat()} "
        f"with no gap longer than {max_gap} days.", values=values)


def _log_02(rule, ctx):
    # The run index IS the tamper-evidence: it commits to the content digest of
    # every run file, so a run edited, added or removed after filing is
    # detectable. Its absence means the log is a narrative, not evidence.
    index = ctx.dossier.dossier.run_index
    return ctx.fb.verdict(
        rule, not index,
        "The submission carries no run index, so nothing commits to the content of the runs "
        "and the log is editable after the fact.",
        f"The run index commits to the content digest of all {len(index)} run file(s).",
        values={"indexed_runs": len(index)})


def _log_03(rule, ctx):
    """Silent omission — the strongest signal in this family.

    Reconciles both ways. A settled transaction with no run is money that moved
    outside any recorded episode; a completed run with no transaction is an
    episode the ledger never saw.
    """
    d = ctx.dossier
    in_window = {t.run_ref for t in d.transaction_history if t.run_ref}
    completed = {r.run_id for r in d.runs if r.outcome == "completed"}
    orphan_txn = sorted(in_window - {r.run_id for r in d.runs})
    missing_txn = sorted(completed - in_window)
    return ctx.fb.verdict(
        rule, bool(orphan_txn or missing_txn),
        f"Log and settlement do not reconcile: {len(orphan_txn)} transaction(s) reference no "
        f"submitted run, {len(missing_txn)} completed run(s) have no settlement record.",
        f"All {len(completed)} completed run(s) have a settlement record and every in-window "
        f"transaction references a submitted run.",
        values={"transactions_without_a_run": orphan_txn[:20],
                "runs_without_a_transaction": missing_txn[:20],
                "completed_runs": len(completed), "linked_transactions": len(in_window)})


_DOSSIER_CHECKERS = {
    "control_set_declared": _rep_01,
    "every_mandate_risk_has_a_control": _rep_02,
    "controls_versioned": _rep_03,
    "control_enforcement_declared": _rep_04,
    "override_rate_within_maximum": _eff_03,
    "audit_log_covers_period": _log_01,
    "audit_log_tamper_evident": _log_02,
    "log_reconciles_to_settlement": _log_03,
}

_RUN_CHECKERS = {
    "every_action_evaluated": _dis_01,
    "disposition_recorded": _dis_02,
    "human_review_has_a_decision": _dis_03,
    "no_execution_after_reject": _dis_04,
    "control_that_should_trigger_did": _eff_01,
    "override_has_authority_and_reason": _eff_02,
    "triggered_blocking_control_has_no_settlement": _eff_04,
}


def run_control_checks(dossier: LoadedDossier, ruleset: Ruleset,
                       peer_breaches: dict[str, set[str]] | None = None) -> list[Fact]:
    """Every CTL rule against this dossier, as facts.

    `peer_breaches` maps run_id -> the failure ids other specialists confirmed.
    CTL-EFF-01 is the only rule that reads it. `None` means it has not been
    supplied yet and EFF-01 reports `absent/awaiting_peers`; an empty dict
    means the peers ran and found nothing, and EFF-01 is satisfied.
    """
    ctx = build_context(dossier, peer_breaches)
    return evaluate_ruleset(
        ruleset, builder=ctx.fb, ctx=ctx, runs=dossier.runs,
        dossier_checkers=_DOSSIER_CHECKERS, run_checkers=_RUN_CHECKERS,
        module="agents/control_checks.py")
