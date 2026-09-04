"""The fact contract every deterministic `check()` is written against.

migration-plan.md Phase 1. Before this, a checker returned `Finding | None`,
and `None` meant two different things: *this rule was satisfied* and *this
rule had no evidence*. Nothing downstream could tell them apart, so an agent
that stayed silent for lack of evidence scored identically to one that
checked and found nothing — and an eval computed over that would have been
measuring the wrong thing.

Two pieces live here:

`FactBuilder` (schemas/fact.py, re-exported here) mints facts with
deterministic ids for one case and one specialist domain. Every rule outcome
is `breach` / `satisfied` / `absent`, and `absent` must say why.

`evaluate_ruleset()` is the dispatcher: it walks a rulebook and makes sure
every rule produces something. Retired rules are skipped; draft rules emit
one `absent/rule_draft` fact each, so the coverage gap is a fact on the
case rather than an absence nobody counts; an active *computable* rule with
no registered checker raises — an active rule nobody's code evaluates is
worse than a crash, and that guarantee is what surfaced the KYA/Provenance
ownership split in the first place. An active *judged* rule may register a
checker that emits the measurements its reasoning pass will judge over,
and is otherwise left to that pass.

**Rule scope.** A checker is registered as either dossier-level (called
once) or run-level (called once per run, its fact carrying `run_ref`).
Which is which is a property of the rule, decided by what its answer
depends on: "does the chain end in a human" has one answer per dossier,
"is this cart within this shopper's cap" has one per run. The dispatcher
does not decide; the module registering the checker does.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from schemas import AbsentReason, Fact, FactBuilder, Rule, Ruleset
from schemas.dossier import Run

__all__ = ["FactBuilder", "evaluate_ruleset", "by_rule", "breaches", "absent"]


DossierChecker = Callable[[Rule, Any], "Fact | list[Fact]"]
RunChecker = Callable[[Rule, Run, Any], "Fact | list[Fact]"]


def evaluate_ruleset(
    ruleset: Ruleset,
    *,
    builder: FactBuilder,
    ctx: Any,
    runs: Sequence[Run],
    dossier_checkers: Mapping[str, DossierChecker] = {},
    run_checkers: Mapping[str, RunChecker] = {},
    handled_elsewhere: frozenset[str] = frozenset(),
    module: str,
) -> list[Fact]:
    """Every rule in `ruleset` accounted for, in rulebook order.

    `handled_elsewhere` names the rule types another module evaluates on
    purpose (ingestion's cryptographic checks; the three KYA rules Provenance
    owns). Listing them is what stops "skipped deliberately" from decaying
    into "skipped by accident": anything active, computable and not listed
    must have a checker here or the dispatcher raises.
    """
    facts: list[Fact] = []
    for rule in ruleset.rules:
        if rule.status == "retired":
            continue
        if rule.status == "draft":
            facts.append(builder.absent(
                rule, "rule_draft",
                f"{rule.rule_id} is draft in {ruleset.ruleset_id} v{ruleset.version} and was "
                f"not evaluated" + (f": {rule.notes}" if rule.notes else "."),
                values={"status": rule.status, "evaluation": rule.evaluation}))
            continue
        if rule.type in handled_elsewhere:
            continue
        if (check := dossier_checkers.get(rule.type)) is not None:
            facts.extend(_as_list(check(rule, ctx)))
        elif (check := run_checkers.get(rule.type)) is not None:
            for run in runs:
                facts.extend(_as_list(check(rule, run, ctx)))
        elif rule.evaluation == "judged":
            # Its verdict is the reasoning pass's; measurements are optional.
            continue
        else:
            raise NotImplementedError(
                f"Active {ruleset.domain} rule {rule.rule_id} (type={rule.type!r}) has no "
                f"registered checker in {module} — every active computable rule must be "
                f"evaluable, or listed as handled elsewhere.")

    seen: dict[str, Fact] = {}
    for f in facts:
        if f.fact_id in seen:
            raise ValueError(
                f"{module}: two facts share id {f.fact_id!r} — a rule must produce exactly one "
                f"outcome per scope unit, so this is a checker emitting twice")
        seen[f.fact_id] = f
    return facts


def _as_list(out: Fact | list[Fact]) -> list[Fact]:
    return out if isinstance(out, list) else [out]


def by_rule(facts: Sequence[Fact]) -> dict[str, list[Fact]]:
    out: dict[str, list[Fact]] = {}
    for f in facts:
        if f.rule_id:
            out.setdefault(f.rule_id, []).append(f)
    return out


def breaches(facts: Sequence[Fact]) -> list[Fact]:
    return [f for f in facts if f.kind == "breach"]


def absent(facts: Sequence[Fact], *reasons: AbsentReason) -> list[Fact]:
    return [f for f in facts if f.kind == "absent" and (not reasons or f.absent_reason in reasons)]
