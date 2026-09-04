"""Facts → Assessments → Findings: the deterministic half of "agents establish
meaning", and the projection the API and ledger read.

migration-plan.md Phase 1, items 2 and 3. Three functions:

`floor_assessments()` — one Assessment per breached rule, citing every breach
fact and every run it breached on. Verdict `breach`, confidence `certain`,
severity at the ruleset floor. This is what an agent's reasoning pass starts
from: it may raise the severity with a rationale, mark a breach `explained`
with a superseding assessment, or add judgements of its own, but it cannot
make the floor disappear. Grouping per rule rather than per fact is what
lets a whole-dossier review say "the cap was breached on runs 43 and 48" as
one claim, checkable against two facts, instead of two claims.

One piece of context the floor applies itself, because it is mechanical: a
breach on a run the firm's own blocking control stopped before any payment
(`outcome == "blocked"`) is assessed `explained`, not `breach`. The fact
stays a breach — the agent did build a cart outside its mandate, and how
often it does so is supervisory information — but the regime produced the
outcome it is designed to produce, and pricing that as a breach would score
an agent worse for having a control that works. The reasoning pass may
supersede it (an injection the cap control happened to stop is not
"explained"); the floor does not pretend to know.

`data_gap_assessments()` — one `concern` per block the submission did not
carry (or carried too thin to use), naming the rules it disabled. A firm
that cannot produce a field has told you something. This is the gate
migration-plan.md Phase 1 sets: "a data-gap finding appears on the case".
Absences that are nobody's gap — a rule that does not apply to this shape, a
draft rule, a register the regulator has not filled — do not roll up here;
they are visible as facts and counted in the console, but they are not a
finding against the submission.

`project_finding()` — an Assessment as a `Finding`, for everything that
still consumes findings (scoring, the ledger's `finding_recorded`, the
report). A Finding is no longer something an agent produces directly.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence

from schemas import (
    DATA_GAP_REASONS,
    Assessment,
    EvidenceRef,
    Fact,
    FailureCatalogue,
    FailureOccurrence,
    Finding,
    Rule,
    Ruleset,
)
from schemas.dossier import LoadedDossier

# Finding.type for an assessment that no rule backs. Rule-backed assessments
# project to their rule's finding_type; the rest name their kind in `subject`
# as "<type>:<detail>" — see data_gap_assessments().
_DEFAULT_TYPE = "assessment"


def contained_runs(dossier: LoadedDossier) -> dict[str, list[str]]:
    """run_id -> the blocking controls that held, for every run the firm's
    own controls stopped before a payment. schemas/dossier.py guarantees a
    blocked run carries a triggered control and no payment."""
    declared = {c.control_id: c for c in [*dossier.dossier.controls.operator_declared,
                                          *dossier.dossier.controls.institution_declared]}
    out: dict[str, list[str]] = {}
    for r in dossier.runs:
        if r.outcome != "blocked" or r.payment is not None:
            continue
        held = [e.control_id for e in r.controls_evaluated
                if e.outcome == "triggered" and e.override is None
                and (c := declared.get(e.control_id)) is not None and c.enforcement == "blocking"]
        if held:
            out[r.run_id] = held
    return out


def floor_assessments(facts: Sequence[Fact], ruleset: Ruleset, *, agent: str,
                      round: int = 1,
                      contained: dict[str, list[str]] | None = None) -> list[Assessment]:
    """`contained` is `contained_runs(dossier)` — omit it and every breach is
    assessed as a breach."""
    rules = {r.rule_id: r for r in ruleset.rules}
    contained = contained or {}
    grouped: dict[str, list[Fact]] = {}
    for f in facts:
        if f.kind == "breach":
            grouped.setdefault(f.rule_id, []).append(f)  # type: ignore[arg-type]
    out: list[Assessment] = []
    for rule_id, fs in grouped.items():
        rule = rules.get(rule_id)
        if rule is None:
            raise ValueError(
                f"breach fact(s) cite {rule_id}, which is not in {ruleset.ruleset_id} "
                f"v{ruleset.version} — the floor cannot be priced from a rule it cannot see")
        held = [f for f in fs if f.run_ref in contained]
        open_ = [f for f in fs if f.run_ref not in contained]
        case_id = fs[0].case_id
        common = dict(case_id=case_id, round=round, agent=agent, rule_id=rule_id,
                      ruleset_version=ruleset.version, confidence="certain",
                      severity_floor=rule.severity_weight,
                      severity_assessed=rule.severity_weight)
        if open_:
            run_refs = sorted({f.run_ref for f in open_ if f.run_ref})
            out.append(Assessment(
                assessment_id=f"{case_id}:{agent}:{rule_id}:r{round}",
                scope="run" if run_refs else "case", verdict="breach",
                fact_ids=[f.fact_id for f in open_], evidence_refs=_merge_refs(open_),
                run_refs=run_refs, narrative=_narrate_breach(rule, open_, run_refs), **common))
        if held:
            run_refs = sorted({f.run_ref for f in held})
            out.append(Assessment(
                assessment_id=f"{case_id}:{agent}:{rule_id}:explained:r{round}",
                scope="run", verdict="explained",
                fact_ids=[f.fact_id for f in held], evidence_refs=_merge_refs(held),
                run_refs=run_refs, narrative=_narrate_contained(rule, held, contained), **common))
    return out


def data_gap_assessments(facts: Sequence[Fact], *, agent: str,
                         round: int = 1) -> list[Assessment]:
    grouped: dict[tuple[str, str], list[Fact]] = {}
    for f in facts:
        if f.kind == "absent" and f.absent_reason in DATA_GAP_REASONS:
            grouped.setdefault((f.absent_reason, f.missing or ""), []).append(f)
    out: list[Assessment] = []
    for (reason, missing), fs in grouped.items():
        run_refs = sorted({f.run_ref for f in fs if f.run_ref})
        rule_ids = sorted({f.rule_id for f in fs if f.rule_id})
        case_id = fs[0].case_id
        per_rule = []
        for rid in rule_ids:
            n = sum(1 for f in fs if f.rule_id == rid and f.run_ref)
            per_rule.append(f"{rid} ({n} run{'s' if n != 1 else ''})" if n else rid)
        what = ("was not submitted" if reason == "missing_block"
                else "is too thin to evaluate")
        out.append(Assessment(
            assessment_id=f"{case_id}:{agent}:gap:{_slug(missing)}:r{round}",
            case_id=case_id, round=round, scope="run" if run_refs else "case",
            agent=agent, rule_id=None, fact_ids=[f.fact_id for f in fs],
            verdict="concern", confidence="certain",
            subject=f"data_gap:{missing}", run_refs=run_refs,
            narrative=(f"{len(rule_ids)} rule{'s' if len(rule_ids) != 1 else ''} could not be "
                       f"evaluated because `{missing}` {what}: {', '.join(per_rule)}."),
        ))
    return out


def project_finding(a: Assessment, rules_by_id: dict[str, Rule]) -> Finding:
    """The Finding view of an Assessment — same id, so the ledger and the
    state reducer treat a re-derived assessment as the same finding."""
    if a.rule_id:
        rule = rules_by_id.get(a.rule_id)
        if rule is None:
            raise ValueError(f"{a.assessment_id} cites {a.rule_id}, which no supplied ruleset holds")
        finding_type = rule.finding_type
    else:
        finding_type = (a.subject or _DEFAULT_TYPE).split(":", 1)[0] or _DEFAULT_TYPE
    return Finding(
        finding_id=a.assessment_id, case_id=a.case_id, agent=a.agent, type=finding_type,
        rule_id=a.rule_id, severity_weight=a.weighted() if a.scores else None,
        summary=a.narrative,
        details={
            "verdict": a.verdict, "confidence": a.confidence, "scope": a.scope,
            "round": a.round, "run_refs": a.run_refs, "fact_ids": a.fact_ids,
            "severity_floor": a.severity_floor, "severity_assessed": a.severity_assessed,
            "severity_rationale": a.severity_rationale, "supersedes": a.supersedes,
            "ruleset_version": a.ruleset_version, "subject": a.subject,
            "review_run_refs": a.review_run_refs,
        },
    )


def project_findings(assessments: Iterable[Assessment],
                     rulesets: Sequence[Ruleset]) -> list[Finding]:
    rules = {r.rule_id: r for rs in rulesets for r in rs.rules}
    return [project_finding(a, rules) for a in assessments]


def project_failure_occurrences(
    assessments: Iterable[Assessment],
    rulesets: Sequence[Ruleset],
    catalogue: FailureCatalogue,
) -> list[FailureOccurrence]:
    """Project rule-backed conclusions into stable F-catalogue instances.

    A rule can cover more than one catalogue failure, so the projection is
    one occurrence per ``(assessment, failure_id)``.  Clear assessments are
    coverage evidence, not failures, and therefore do not become
    occurrences.  The source Assessment and Facts remain canonical.
    """
    rules = {r.rule_id: r for rs in rulesets for r in rs.rules}
    definitions = {f.failure_id: f for f in catalogue.failures}
    statuses = {
        "breach": "detected",
        "concern": "possible",
        "explained": "contained",
        "inconclusive": "not_evaluable",
    }
    out: list[FailureOccurrence] = []
    for assessment in assessments:
        if assessment.verdict == "clear":
            continue
        if assessment.rule_id is None:
            # Portfolio Systemic assessments explicitly name their stable
            # failure id in subject ("F67:model-x"). They are not per-firm
            # policy rules and must not be assigned a fabricated rulebook.
            candidate = (assessment.subject or "").split(":", 1)[0]
            failure_ids = [candidate] if assessment.agent == "systemic" and candidate in definitions else []
        else:
            rule = rules.get(assessment.rule_id)
            if rule is None:
                raise ValueError(
                    f"{assessment.assessment_id} cites {assessment.rule_id}, which no supplied ruleset holds"
                )
            if not assessment.ruleset_version:
                raise ValueError(
                    f"{assessment.assessment_id} is rule-backed but has no ruleset_version"
                )
            if assessment.failure_ids is None:
                failure_ids = list(rule.failures)
            else:
                invalid = sorted(set(assessment.failure_ids) - set(rule.failures))
                if invalid:
                    raise ValueError(
                        f"{assessment.assessment_id} selected failure ids {invalid} outside "
                        f"{assessment.rule_id}'s declared coverage {rule.failures}"
                    )
                failure_ids = list(dict.fromkeys(assessment.failure_ids))
        run_refs = sorted(set(assessment.run_refs))
        scope = assessment.scope
        if scope == "run" and len(run_refs) > 1:
            scope = "run_set"
        transaction_refs = sorted({
            ref.ref for ref in assessment.evidence_refs if ref.kind == "transaction"
        })
        case_refs = sorted(set(assessment.subject_refs or [assessment.case_id]))
        for failure_id in failure_ids:
            definition = definitions.get(failure_id)
            # Rules may also cite the separate S-series submission catalogue.
            if definition is None:
                continue
            out.append(FailureOccurrence(
                occurrence_id=f"{assessment.assessment_id}:{failure_id}",
                case_id=assessment.case_id,
                failure_id=failure_id,
                failure_name=definition.name,
                catalogue_version=catalogue.version,
                # The catalogue owns the conceptual domain ("controls");
                # the occurrence names the specialist that made this exact
                # assessment ("control_assurance"), which is what the UI and
                # audit attribution need.
                domain=assessment.agent,
                rule_id=assessment.rule_id,
                ruleset_version=assessment.ruleset_version,
                assessment_id=assessment.assessment_id,
                status=statuses[assessment.verdict],
                confidence=assessment.confidence,
                scope=scope,
                run_refs=run_refs,
                run_refs_by_case=assessment.run_refs_by_case,
                transaction_refs=transaction_refs,
                case_refs=case_refs,
                fact_ids=list(assessment.fact_ids),
                evidence_refs=list(assessment.evidence_refs),
                summary=assessment.narrative,
            ))
    return out


def rules_by_id(*rulesets: Ruleset) -> dict[str, Rule]:
    return {r.rule_id: r for rs in rulesets for r in rs.rules}


# --- supersession -------------------------------------------------------------

def _claim(a: Assessment) -> tuple:
    """What a later round re-decides as a unit: an agent's assessment of a
    rule. A whole-dossier judged call re-judges every run of its rule, so
    round 2's answers replace round 1's for that rule wholesale — one
    `breach` on a run that round 2 finds consistent must not survive next
    to round 2's `clear`. Rule-less assessments (data gaps) key on subject."""
    return (a.agent, a.rule_id, None if a.rule_id else a.subject)


def superseded_ids(assessments: Iterable[Assessment]) -> set[str]:
    """Every assessment a later round of the same agent re-decided. Both
    stay on the ledger; the projection and scoring read the current ones."""
    items = list(assessments)
    surviving = {a.assessment_id for a in current(items)}
    return {a.assessment_id for a in items if a.assessment_id not in surviving}


def link_supersessions(new: Sequence[Assessment], prior: Sequence[Assessment]) -> list[Assessment]:
    """Mark each new assessment with the most recent earlier assessment of
    the same claim — the audit trail's pointer back. Which earlier ones are
    superseded is decided by round (`superseded_ids`), not by this pointer."""
    latest: dict[tuple, Assessment] = {}
    for a in prior:
        if _claim(a) not in latest or a.round >= latest[_claim(a)].round:
            latest[_claim(a)] = a
    out = []
    for a in new:
        earlier = latest.get(_claim(a))
        if earlier is not None and earlier.assessment_id != a.assessment_id \
                and earlier.round < a.round and a.supersedes is None:
            a = a.model_copy(update={"supersedes": earlier.assessment_id})
        out.append(a)
    return out


def current(assessments: Sequence[Assessment]) -> list[Assessment]:
    out = []
    for a in assessments:
        later = [b for b in assessments if b.round > a.round and _claim(b) == _claim(a)]
        if any(b.review_run_refs is None for b in later):
            continue
        replaced = {r for b in later for r in (b.review_run_refs or [])}
        if a.scope != "run" or not replaced:
            out.append(a)
            continue
        remaining = [r for r in a.run_refs if r not in replaced]
        if not remaining:
            continue
        if remaining == a.run_refs:
            out.append(a)
        else:
            # This is a projection only. The original assessment is immutable
            # on the ledger, including its original full narrative.
            fact_ids = [fid for fid in a.fact_ids
                        if not any(fid.split('@')[0].endswith(":" + r) for r in replaced)]
            out.append(a.model_copy(update={"run_refs": remaining, "fact_ids": fact_ids,
                "narrative": "Still applicable to " + ", ".join(remaining) + ". Original assessment: " + a.narrative}))
    return out


def current_findings(findings: Sequence[Finding], assessments: Sequence[Assessment]) -> list[Finding]:
    """The findings scoring reads: a finding is the projection of an
    assessment under the same id, so a superseded assessment's finding is
    superseded too."""
    active = {a.assessment_id: a for a in current(assessments)}
    known = {a.assessment_id for a in assessments}
    out = []
    for f in findings:
        if f.finding_id not in known:
            out.append(f)
        elif f.finding_id in active:
            a = active[f.finding_id]
            out.append(f.model_copy(update={"summary": a.narrative,
                "details": {**f.details, "run_refs": a.run_refs, "fact_ids": a.fact_ids}}))
    return out


# --- helpers ---------------------------------------------------------------

def _merge_refs(facts: Sequence[Fact]) -> list[EvidenceRef]:
    seen: set[tuple] = set()
    out: list[EvidenceRef] = []
    for f in facts:
        for r in f.refs:
            key = (r.kind, r.ref, repr(r.value))
            if key not in seen:
                seen.add(key)
                out.append(r)
    return out


def _narrate_breach(rule: Rule, facts: Sequence[Fact], run_refs: list[str]) -> str:
    if not run_refs:
        return facts[0].statement
    lead = f"{rule.rule_id} breached on {len(run_refs)} run{'s' if len(run_refs) != 1 else ''}"
    shown = facts[:3]
    tail = f" (+{len(facts) - 3} more)" if len(facts) > 3 else ""
    return lead + ": " + " ".join(f.statement for f in shown) + tail


def _narrate_contained(rule: Rule, facts: Sequence[Fact],
                       contained: dict[str, list[str]]) -> str:
    parts = [f"{f.run_ref}: {', '.join(contained[f.run_ref])} triggered and no payment was "
             f"authorised" for f in facts[:3]]
    tail = f" (+{len(facts) - 3} more)" if len(facts) > 3 else ""
    return (f"{rule.rule_id} tripped on {len(facts)} run{'s' if len(facts) != 1 else ''} the "
            f"firm's own blocking control stopped before settlement — " + "; ".join(parts)
            + tail + ". The deviation is on record; the control held.")


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in s).strip("_") or "unnamed"
