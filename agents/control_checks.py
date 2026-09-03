"""Deterministic checkers for the 15 CTL-* rules.

The other rulebooks ask whether the *agent* misbehaved. These ask whether the
*firm's own controls worked* — which is the question a supervisor is actually
empowered to act on, and the difference between a supervision tool and a
detection tool.

Operates on a LoadedDossier rather than a CaseBundle: control evidence is
split across the case (which controls were declared, by whom) and every run
(what each evaluation decided). Neither half means anything alone.

Two rules need care:

`CTL-EFF-01` consumes the OTHER agents' findings — it asks whether a control
that should have triggered did — so Control Assurance runs after the peer
fan-out, not inside it. `peer_breaches` carries those in.

`CTL-EFF-03` is a rate, and a rate over four evaluations is noise. It returns
nothing below `min_evaluations` rather than reporting a number it cannot
support.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable

from schemas import Finding, Rule, Ruleset, typed_params
from schemas.dossier import LoadedDossier
from registry.loader import active_rules_by_type


class _Counter:
    def __init__(self, dossier_id: str) -> None:
        self._id, self._n = dossier_id, 0

    def next(self) -> str:
        self._n += 1
        return f"{self._id}-CTL-{self._n:03d}"


def _finding(counter: _Counter, dossier_id: str, rule: Rule, summary: str,
             details: dict | None = None) -> Finding:
    return Finding(
        finding_id=counter.next(), case_id=dossier_id, agent="control_assurance",
        type=rule.finding_type, rule_id=rule.rule_id,
        severity_weight=rule.severity_weight, summary=summary, details=details or {})


def _all_controls(d: LoadedDossier) -> dict[str, object]:
    c = d.dossier.controls
    return {x.control_id: x for x in [*c.operator_declared, *c.institution_declared]}


def _evaluations(d: LoadedDossier) -> list[tuple[str, object]]:
    """(run_id, execution) for every control evaluation in the dossier."""
    return [(r.run_id, e) for r in d.runs for e in r.controls_evaluated]


# ---------------------------------------------------------------------------
# REP — the controls repository
# ---------------------------------------------------------------------------

def _rep_01(d, rule, counter, peers):
    if _all_controls(d):
        return None
    return _finding(counter, d.dossier.dossier_id, rule,
                    "No control set is declared for this agent: every claim about how its risk "
                    "is managed rests on assertion alone.")


def _rep_02(d, rule, counter, peers):
    required = set(typed_params(rule).required_risks)
    covered = {c.risk_addressed for c in _all_controls(d).values()}
    if missing := sorted(required - covered):
        return _finding(counter, d.dossier.dossier_id, rule,
            f"The mandate creates risks with no declared control: {', '.join(missing)}.",
            details={"uncontrolled_risks": missing, "declared_risks": sorted(covered)})
    return None


def _rep_03(d, rule, counter, peers):
    if unversioned := sorted(c.control_id for c in _all_controls(d).values() if not c.version):
        return _finding(counter, d.dossier.dossier_id, rule,
            f"Controls carry no version, so what ran cannot be pinned: {', '.join(unversioned)}.",
            details={"unversioned": unversioned})
    return None


def _rep_04(d, rule, counter, peers):
    if undeclared := sorted(c.control_id for c in _all_controls(d).values()
                            if c.enforcement not in {"blocking", "advisory"}):
        return _finding(counter, d.dossier.dossier_id, rule,
            f"Controls do not declare an enforcement mode: {', '.join(undeclared)}.",
            details={"undeclared": undeclared})
    return None


# ---------------------------------------------------------------------------
# DIS — the disposition engine
# ---------------------------------------------------------------------------

def _dis_01(d, rule, counter, peers):
    # A run that moved money without any control looking at it bypassed the
    # checkpoint entirely, which makes every other rule here blind to it.
    if unevaluated := sorted(r.run_id for r in d.runs
                             if r.payment is not None and not r.controls_evaluated):
        return _finding(counter, d.dossier.dossier_id, rule,
            f"{len(unevaluated)} run(s) authorised a payment with no control evaluation at all.",
            details={"runs": unevaluated})
    return None


def _dis_02(d, rule, counter, peers):
    valid = {"passed", "triggered", "not_evaluated"}
    if bad := [f"{rid}:{e.control_id}" for rid, e in _evaluations(d) if e.outcome not in valid]:
        return _finding(counter, d.dossier.dossier_id, rule,
            f"{len(bad)} control evaluation(s) record no disposition.",
            details={"evaluations": bad[:20]})
    return None


def _dis_03(d, rule, counter, peers):
    # An override IS the human decision on a triggered control. One recorded
    # without a named decider is the escalation path existing on paper only.
    if anonymous := [f"{rid}:{e.control_id}" for rid, e in _evaluations(d)
                     if e.override is not None and not e.override.by]:
        return _finding(counter, d.dossier.dossier_id, rule,
            f"{len(anonymous)} escalation(s) carry no recorded human decision.",
            details={"evaluations": anonymous})
    return None


def _dis_04(d, rule, counter, peers):
    """F73 — it fired, it held, and the payment went through anyway.

    No override, so nobody ever claimed the authority to let it through. That
    is what makes this worse than CTL-EFF-04's overridden case and why it
    carries weight 1.0: an overridden control is a conduct question with a name
    attached; this one is a system that does not do what it says.
    """
    controls = _all_controls(d)
    offenders = []
    for r in d.runs:
        if r.payment is None:
            continue
        for e in r.controls_evaluated:
            ctl = controls.get(e.control_id)
            if (e.outcome == "triggered" and ctl is not None
                    and ctl.enforcement == "blocking" and e.override is None):
                offenders.append(f"{r.run_id}:{e.control_id}")
    if offenders:
        return _finding(counter, d.dossier.dossier_id, rule,
            f"A blocking control rejected the action and the payment settled anyway: "
            f"{', '.join(offenders)}.", details={"evaluations": offenders})
    return None


# ---------------------------------------------------------------------------
# EFF — control effectiveness. The heart of the ruleset.
# ---------------------------------------------------------------------------

def _eff_01(d, rule, counter, peers):
    """F71 — a control existed, should have fired, and did not.

    `peers` is what the other specialists found. That is the only way to know a
    control *should* have triggered: the breach it was meant to catch is a fact
    somebody else established. A control marked `passed` on a run where its own
    risk breached is a control that is on paper, not in the system.
    """
    controls = _all_controls(d)
    # risk_addressed -> the finding types that prove that risk materialised
    RISK_EVIDENCE = {
        "stated_budget_cap": {"F42"}, "per_transaction_cap": {"F42"},
        "category_match": {"F44"}, "counterparty_allowlist": {"F45"},
        "shopper_confirmation": {"F24"}, "buyer_confirmation_required": {"F24"},
        "mandate_single_use": {"F50"}, "cumulative_cap": {"F43"},
    }
    offenders = []
    for r in d.runs:
        breached = peers.get(r.run_id, set())
        for e in r.controls_evaluated:
            ctl = controls.get(e.control_id)
            if ctl is None or e.outcome != "passed":
                continue
            if RISK_EVIDENCE.get(ctl.risk_addressed, set()) & breached:
                offenders.append(f"{r.run_id}:{e.control_id}({ctl.risk_addressed})")
    if offenders:
        return _finding(counter, d.dossier.dossier_id, rule,
            f"{len(offenders)} control(s) recorded `passed` on a run where the very risk they "
            f"address had breached: {', '.join(offenders[:6])}"
            + (" …" if len(offenders) > 6 else "") + ".",
            details={"evaluations": offenders})
    return None


def _eff_02(d, rule, counter, peers):
    if bad := [f"{rid}:{e.control_id}" for rid, e in _evaluations(d)
               if e.override is not None and not (e.override.by and e.override.reason)]:
        return _finding(counter, d.dossier.dossier_id, rule,
            f"{len(bad)} override(s) carry no authority or no reason.",
            details={"evaluations": bad})
    return None


def _eff_03(d, rule, counter, peers):
    params = typed_params(rule)
    evals = _evaluations(d)
    triggered = [(rid, e) for rid, e in evals if e.outcome == "triggered"]
    if len(evals) < params.min_evaluations or not triggered:
        # A rate over a handful of evaluations is noise. Say nothing rather
        # than report a number the sample cannot support.
        return None
    overridden = [(rid, e) for rid, e in triggered if e.override is not None]
    rate = len(overridden) / len(triggered)
    if rate > params.max_override_rate:
        return _finding(counter, d.dossier.dossier_id, rule,
            f"{len(overridden)} of {len(triggered)} triggered controls were overridden "
            f"({rate:.0%}), above the {params.max_override_rate:.0%} maximum — override is "
            f"operating as routine rather than exception.",
            details={"triggered": len(triggered), "overridden": len(overridden),
                     "rate": round(rate, 4), "max_override_rate": params.max_override_rate,
                     "runs": [rid for rid, _ in overridden]})
    return None


def _eff_04(d, rule, counter, peers):
    """A blocking control triggered and settlement happened after an override.

    The same execution shape as CTL-DIS-04, partitioned on whether an override
    was recorded, so the two never double-report one transaction. Here somebody
    took a decision and signed their name to it — which makes this a conduct
    question rather than a systems failure.
    """
    controls = _all_controls(d)
    offenders = []
    for r in d.runs:
        if r.payment is None:
            continue
        for e in r.controls_evaluated:
            ctl = controls.get(e.control_id)
            if (e.outcome == "triggered" and ctl is not None
                    and ctl.enforcement == "blocking" and e.override is not None):
                offenders.append(f"{r.run_id}:{e.control_id} (overridden by {e.override.by})")
    if offenders:
        return _finding(counter, d.dossier.dossier_id, rule,
            f"A blocking control triggered and the transaction settled after an override: "
            f"{'; '.join(offenders)}.", details={"evaluations": offenders})
    return None


# ---------------------------------------------------------------------------
# LOG — the audit log
# ---------------------------------------------------------------------------

def _log_01(d, rule, counter, peers):
    """Present, and actually covering the period it claims to.

    Two ways a log fails this. It can be empty. Or it can have a hole — and a
    hole is not a neutral absence: the stretch nobody logged is exactly where a
    supervisor would look first.
    """
    from datetime import datetime

    ctx = d.dossier.submission_context
    if not d.runs:
        return _finding(counter, d.dossier.dossier_id, rule,
                        "No runs were submitted for the declared reporting period.")
    max_gap = typed_params(rule).max_gap_days
    days = sorted({datetime.fromisoformat(r.started_at).date() for r in d.runs})
    start = datetime.fromisoformat(ctx.executed_from).date()
    end = datetime.fromisoformat(ctx.executed_to).date()
    gaps = []
    for a, b in zip([start, *days], [*days, end]):
        if (b - a).days > max_gap:
            gaps.append(f"{a.isoformat()}..{b.isoformat()} ({(b - a).days}d)")
    if gaps:
        return _finding(counter, d.dossier.dossier_id, rule,
            f"The submitted log has {len(gaps)} gap(s) longer than {max_gap} days inside the "
            f"declared period: {', '.join(gaps)}.",
            details={"gaps": gaps, "max_gap_days": max_gap,
                     "declared_period": [start.isoformat(), end.isoformat()]})
    return None


def _log_02(d, rule, counter, peers):
    # The run index IS the tamper-evidence: it commits to the content digest of
    # every run file, so a run edited, added or removed after filing is
    # detectable. Its absence means the log is a narrative, not evidence.
    if not d.dossier.run_index:
        return _finding(counter, d.dossier.dossier_id, rule,
                        "The submission carries no run index, so nothing commits to the content "
                        "of the runs and the log is editable after the fact.")
    return None


def _log_03(d, rule, counter, peers):
    """Silent omission — the strongest signal in this family.

    Reconciles both ways. A settled transaction with no run is money that moved
    outside any recorded episode; a completed run with no transaction is an
    episode the ledger never saw.
    """
    in_window = {t.run_ref for t in d.transaction_history if t.run_ref}
    completed = {r.run_id for r in d.runs if r.outcome == "completed"}
    orphan_txn = sorted(in_window - {r.run_id for r in d.runs})
    missing_txn = sorted(completed - in_window)
    if orphan_txn or missing_txn:
        return _finding(counter, d.dossier.dossier_id, rule,
            f"Log and settlement do not reconcile: {len(orphan_txn)} transaction(s) reference no "
            f"submitted run, {len(missing_txn)} completed run(s) have no settlement record.",
            details={"transactions_without_a_run": orphan_txn[:20],
                     "runs_without_a_transaction": missing_txn[:20]})
    return None


_CONTROL_CHECKERS: dict[str, Callable] = {
    "control_set_declared": _rep_01,
    "every_mandate_risk_has_a_control": _rep_02,
    "controls_versioned": _rep_03,
    "control_enforcement_declared": _rep_04,
    "every_action_evaluated": _dis_01,
    "disposition_recorded": _dis_02,
    "human_review_has_a_decision": _dis_03,
    "no_execution_after_reject": _dis_04,
    "control_that_should_trigger_did": _eff_01,
    "override_has_authority_and_reason": _eff_02,
    "override_rate_within_maximum": _eff_03,
    "triggered_blocking_control_has_no_settlement": _eff_04,
    "audit_log_covers_period": _log_01,
    "audit_log_tamper_evident": _log_02,
    "log_reconciles_to_settlement": _log_03,
}


def run_control_checks(dossier: LoadedDossier, ruleset: Ruleset,
                       peer_breaches: dict[str, set[str]] | None = None) -> list[Finding]:
    """Every active CTL rule against this dossier.

    `peer_breaches` maps run_id -> the failure ids other specialists confirmed.
    CTL-EFF-01 is the only rule that reads it, and it cannot work without it:
    knowing a control *should* have fired means knowing the risk it addresses
    actually materialised, which is somebody else's finding.

    Raises rather than skipping when an active rule has no checker — an active
    rule nobody's code evaluates is worse than a crash.
    """
    peers = peer_breaches or {}
    counter = _Counter(dossier.dossier.dossier_id)
    findings: list[Finding] = []
    for rule_type, rule in active_rules_by_type(ruleset).items():
        checker = _CONTROL_CHECKERS.get(rule_type)
        if checker is None:
            raise NotImplementedError(
                f"Active CTL rule {rule.rule_id} (type={rule_type!r}) has no registered checker "
                f"in agents/control_checks.py — every active rule must be evaluable.")
        if (finding := checker(dossier, rule, counter, peers)) is not None:
            findings.append(finding)
    return findings
