"""One rulebook, the whole labelled corpus, one scorecard.

This is `eval/__main__.py` made parameterisable: same production graph, same
temporary ledger, same discipline of opening the labels only *after* the
graph has returned. What it adds is a `rulesets` argument, a typed result,
and the two questions eval never asked — whether a rule fires at all, and
whether the dossier ends up with the right disposition.

The isolation that makes the numbers honest is structural, not conventional:

- `load_for_pipeline()` does not read `ground_truth.json`. Labels are opened
  here, in the runner, after `run_triage` returns. Nothing in the pipeline
  can see them.
- Every sweep runs against a throwaway ledger, so a sandbox experiment can
  never touch case history or a real disposition.
- Draft rulebooks reach the graph as an argument (`run_triage(rulesets=...)`)
  and are never written into `registry/rulesets/`.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from agents.assess import current
from data.canonical import payload_hash
from data.dossier_loader import list_dossiers, load_for_pipeline
from ledger import LedgerStore
from ledger.seed import submit_dossier
from pipeline.authorisation import recommend
from pipeline.graph import run_triage
from agents.catalog import RULESET_LOADERS
from schemas import (
    Detection,
    DossierOutcome,
    Label,
    Metrics,
    Ruleset,
    RuleScore,
    SweepPins,
    SweepResult,
)

ROOT = Path(__file__).resolve().parent.parent


def judged_only_failures(books: dict) -> set[str]:
    """Failures no mechanical sweep can establish, derived from the rulebook.

    A failure is unscoreable without the model when EVERY active rule that
    declares it is `judged`. Excluding those is what stops a mechanical sweep
    reporting a false negative for a judgement nobody asked for.

    This was a hardcoded `{"F49", "F55", "F38"}` inherited from
    eval/__main__.py, and it was wrong in both directions: F32 (`INJ-ACT-01`,
    judged) was missing, so all three of its labels counted as missed; F55
    (`CPT-NEW-01`) is computable and was excluded, so two labels a code rule
    genuinely catches were dropped from the score. `rule.evaluation` is the
    source of truth and is right there on every rule.
    """
    owners: dict[str, list] = {}
    for book in books.values():
        if book is None:
            continue
        for rule in book.rules:
            if rule.status == "retired":
                continue
            for failure in rule.failures:
                owners.setdefault(failure, []).append(rule)
    return {failure for failure, rules in owners.items()
            if all(r.evaluation == "judged" for r in rules)}

# A dossier with any planted defect should not be authorised. The corpus
# holds no clean dossier today, so this is a weak label — see the spec's
# constraints — but it is the question a regulator actually asks.
ADVERSE_DISPOSITIONS = {"refuse", "monitor", "incomplete-submission"}


def corpus_digest() -> str:
    """Every dossier and its labels. A sweep taken against a different corpus
    is not comparable, and this is what says so."""
    parts = []
    for path in sorted(list_dossiers()):
        gt = path / "ground_truth.json"
        parts.append({
            "dossier": json.loads((path / "dossier.json").read_text(encoding="utf-8")),
            "labels": json.loads(gt.read_text(encoding="utf-8")) if gt.exists() else None,
        })
    return payload_hash({"corpus": parts}, exclude_keys=())


def code_revision() -> str:
    """Which commit this was taken at. Provenance only — `SweepPins` explains
    why a git hash is the wrong thing to gate comparability on."""
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5,
                             cwd=ROOT)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _digest_files(paths: list[Path]) -> str:
    """Content hash over a set of files, keyed by path relative to the repo.

    Missing files are recorded as missing rather than skipped, so deleting an
    input is as visible as editing one.
    """
    return payload_hash({
        str(path.relative_to(ROOT)): (
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None)
        for path in sorted(set(paths))
    }, exclude_keys=())


# Every policy input a sweep reads off disk. Not "the rulebook under test" —
# that reaches the graph as an argument and is pinned separately as
# `Sweep.ruleset_digest`; this is the ground the sweep stands on while it
# measures one book against it.
POLICY_PATHS: tuple[Path, ...] = (
    ROOT / "registry" / "rulesets",       # all ten books: a sweep's headline
                                          # counts breaches from every domain
    ROOT / "registry" / "scoring.json",
    ROOT / "registry" / "failures.json",  # default_scope decides how a
                                          # detection is keyed, so this file
                                          # moves the numbers on its own
    ROOT / "registry" / "authorisation.json",
    ROOT / "data" / "registry",           # operators, agents, keystore, tools:
                                          # what KYA checks identity against
)

# The source that turns a dossier into facts. `data/authored/` is excluded on
# purpose — those scripts generate the corpus, and their output is already
# pinned by `corpus_digest()`.
ENGINE_PATHS: tuple[Path, ...] = (
    ROOT / "agents",
    ROOT / "pipeline",
    ROOT / "ingestion",
    ROOT / "ledger",
    ROOT / "schemas",
    ROOT / "registry" / "loader.py",
    ROOT / "data" / "canonical.py",
    ROOT / "data" / "dossier_loader.py",
    ROOT / "data" / "registries.py",
    ROOT / "data" / "keystore.py",
    Path(__file__).resolve(),             # the scorer itself
)


def _expand(roots: tuple[Path, ...], suffix: str | None = None) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        if root.is_dir():
            out += [p for p in root.rglob(f"*{suffix}" if suffix else "*")
                    if p.is_file() and "__pycache__" not in p.parts]
        else:
            out.append(root)
    return out


def policy_digest() -> str:
    """Every rulebook, weight and registry on disk. Moves when a book is
    promoted, when the failure catalogue is re-scoped, or when the regulator's
    own keystore gains an operator — each of which changes what a sweep
    measures without touching the rulebook under test."""
    return _digest_files(_expand(POLICY_PATHS, ".json"))


def engine_digest() -> str:
    """The detection code. Content-addressed, so an unrelated commit leaves
    every stored scorecard comparable and an uncommitted edit to a specialist
    does not."""
    return _digest_files(_expand(ENGINE_PATHS, ".py"))


def pins(*, mode: str = "mechanical") -> SweepPins:
    return SweepPins(corpus_digest=corpus_digest(), code_revision=code_revision(),
                     policy_digest=policy_digest(), engine_digest=engine_digest(),
                     mode=mode)


def _scoped_key(cid: str, run_ref: str | None, failure: str, scopes: dict[str, str]) -> tuple:
    """One key per claim, at the scope the CATALOGUE gives the failure.

    F35 is "the objective was redirected AND STAYED redirected" — a `run_set`
    failure. The corpus plants it on the three runs that show the pattern, and
    the specialist reports it once with every affected run attached. Keyed per
    run, one judgement became 37 detections against 3 labels: 34 false
    positives out of a single correct finding, which is what made a live sweep
    look like a 30% false-positive rate.

    Both sides of the comparison are normalised here, so a `run_set` or `case`
    failure is counted once per submission however many runs either side names.
    The occurrence projection already reasons this way (agents/assess.py
    promotes a multi-run assessment to one run_set occurrence); this makes the
    scorer agree with it.
    """
    return (cid, None, failure) if scopes.get(failure) in ("run_set", "case", "portfolio") \
        else (cid, run_ref, failure)


def _metrics(expected: set, detected: set) -> Metrics:
    return Metrics(tp=len(expected & detected), fp=len(detected - expected),
                   fn=len(expected - detected))


async def run_sweep(
    *,
    rulesets: dict[str, Ruleset] | None = None,
    live: bool = False,
    model=None,
) -> SweepResult:
    """Run every labelled dossier through the production graph under
    `rulesets` (the active books where a domain is not overridden)."""
    books = {**{name: load() for name, load in RULESET_LOADERS.items()},
             **(rulesets or {})}
    rules = {r.rule_id: r for rs in books.values() if rs for r in rs.rules}
    domain_of = {r.rule_id: name for name, rs in books.items() if rs for r in rs.rules}
    judged_only = judged_only_failures(books)
    from registry.loader import load_failure_catalogue

    scopes = {f.failure_id: f.default_scope for f in load_failure_catalogue().failures}
    # Labels a mechanical sweep is structurally unable to score. Reported so
    # the headline denominator cannot quietly shrink to flatter itself.
    excluded: list[Label] = []

    expected: set[tuple] = set()
    detected: set[tuple] = set()
    clean: set[tuple] = set()
    fired: dict[str, int] = defaultdict(int)
    by_rule: dict[str, set[tuple]] = defaultdict(set)
    clean_hits: dict[str, set[str]] = defaultdict(set)
    label_text: dict[tuple, str] = {}
    detection_rule: dict[tuple, str] = {}
    outcomes: list[DossierOutcome] = []

    with tempfile.TemporaryDirectory(prefix="mandate-sweep-") as directory:
        store = LedgerStore(Path(directory) / "ledger.db")
        for path in list_dossiers():
            dossier = load_for_pipeline(path)
            cid = submit_dossier(store, dossier)
            record = await run_triage(cid, store=store, model=model,
                                      deterministic_only=not live, rulesets=rulesets)

            # Labels are opened only now, after the graph has returned.
            gt_path = path / "ground_truth.json"
            labels = json.loads(gt_path.read_text(encoding="utf-8")) if gt_path.exists() else {}
            planted = labels.get("planted", [])
            clean_runs = labels.get("clean_runs", [])
            clean |= {(cid, rid) for rid in clean_runs}

            for p in planted:
                failure = p["failure"]
                if failure.startswith("S"):
                    continue  # submission-level label, not a run failure
                if failure in judged_only and not live:
                    excluded.append(Label(dossier_id=cid, run_ref=p.get("run_ref"),
                                          failure=failure, what=p.get("what", "")))
                    continue
                key = _scoped_key(cid, p.get("run_ref"), failure, scopes)
                expected.add(key)
                label_text.setdefault(key, p.get("what", ""))

            for fact in record.facts:
                rule = rules.get(fact.rule_id)
                if rule is None or fact.kind != "breach":
                    continue
                fired[rule.rule_id] += 1
                if fact.run_ref and (cid, fact.run_ref) in clean:
                    clean_hits[rule.rule_id].add(fact.run_ref)
                for failure in rule.failures:
                    if failure in judged_only and not live:
                        continue
                    # No per-failure special cases. F19 used to need one
                    # because it was only reachable through a broad rule; now
                    # KYA-TEC-03 owns the declared side and KYA-TEC-07 the
                    # observed one, so each rule's `failures` is simply true.
                    # The old guard also discarded a legitimate declared-
                    # blocklist F19, whose fact carries no `observed_blocklisted`.
                    key = _scoped_key(cid, fact.run_ref, failure, scopes)
                    detected.add(key)
                    by_rule[rule.rule_id].add(key)
                    detection_rule.setdefault(key, rule.rule_id)

            if live:
                for a in current(record.assessments):
                    rule = rules.get(a.rule_id) if a.rule_id else None
                    if rule is None or a.verdict != "breach":
                        continue
                    fired[rule.rule_id] += 1
                    # Which clean runs this judged rule flagged. Recorded on
                    # the deterministic side since the beginning; without it
                    # here, a false positive produced by a judged rule showed
                    # in the total and could not be traced to the rule that
                    # produced it — and the judged tier is where most of them
                    # turn out to be.
                    for rid in a.run_refs:
                        if (cid, rid) in clean:
                            clean_hits[rule.rule_id].add(rid)
                    for failure in set(rule.failures) & judged_only:
                        for rid in a.run_refs or [None]:
                            key = _scoped_key(cid, rid, failure, scopes)
                            detected.add(key)
                            by_rule[rule.rule_id].add(key)
                            detection_rule.setdefault(key, rule.rule_id)

            outcomes.append(_dossier_outcome(dossier, record, cid, planted, clean_runs))

    return _assemble(books, rules, domain_of, expected, detected, clean, fired,
                     by_rule, clean_hits, label_text, detection_rule, outcomes, live,
                     excluded, judged_only)


def _dossier_outcome(dossier, record, cid, planted, clean_runs) -> DossierOutcome:
    """Question 5: with this rulebook, does the submission get the right
    disposition? A dossier carrying planted defects must not be authorised."""
    weight, gates, adequacy = None, 0, 0
    try:
        rec = recommend(dossier, record.facts, record.assessments,
                        correlations=record.correlations)
        actual = rec.disposition
        # Recorded so a severity edit is visible even when the disposition
        # holds: the tier is a step function over this.
        weight, gates = rec.weight_per_run, len(rec.hard_gates)
        # …and this is what says when the disposition is NOT a detection
        # result. See `DossierOutcome.adequacy_gaps`.
        adequacy = len(rec.adequacy)
    except Exception:
        actual = "unavailable"
    expected = "authorise" if not planted else "not-authorise"
    correct = (actual in ADVERSE_DISPOSITIONS) if planted else (actual == "authorise")
    return DossierOutcome(dossier_id=cid, expected=expected, actual=actual, correct=correct,
                          planted_defects=len(planted), clean_runs=len(clean_runs),
                          weight_per_run=weight, hard_gates=gates, adequacy_gaps=adequacy)


def _assemble(books, rules, domain_of, expected, detected, clean, fired, by_rule,
              clean_hits, label_text, detection_rule, outcomes, live,
              excluded, judged_only) -> SweepResult:
    per_rule = {}
    for rule_id, rule in rules.items():
        per_rule[rule_id] = RuleScore(
            rule_id=rule_id,
            domain=domain_of.get(rule_id, "unknown"),
            status=rule.status,
            evaluation=rule.evaluation,
            severity_weight=rule.severity_weight,
            failures=list(rule.failures),
            fired=fired.get(rule_id, 0),
            metrics=_metrics({k for k in expected if k[2] in rule.failures},
                             by_rule.get(rule_id, set())),
            clean_run_hits=sorted(clean_hits.get(rule_id, set())),
        )

    per_domain = {}
    unevaluated = []
    for name, book in books.items():
        if book is None:
            continue
        ids = {r.rule_id for r in book.rules}
        failures = {f for r in book.rules for f in r.failures}
        per_domain[name] = _metrics({k for k in expected if k[2] in failures},
                                    {k for rid in ids for k in by_rule.get(rid, set())})
        # A mechanical sweep never runs the model, so a book that is entirely
        # judged was not evaluated at all. Saying so is the difference between
        # a total that means something and one that implies coverage it lacks.
        if not live and all(r.evaluation == "judged" for r in book.rules if r.status == "active"):
            unevaluated.append(name)

    clean_fps = sorted({rid for cid, rid in clean
                        if any(k[0] == cid and k[1] == rid for k in detected)})

    return SweepResult(
        overall=_metrics(expected, detected),
        dossiers=outcomes,
        per_rule=per_rule,
        per_failure={f: _metrics({k for k in expected if k[2] == f},
                                 {k for k in detected if k[2] == f})
                     for f in sorted({k[2] for k in expected | detected})},
        per_domain=per_domain,
        clean_runs=len(clean),
        clean_run_false_positives=clean_fps,
        missed=[Label(dossier_id=k[0], run_ref=k[1], failure=k[2], what=label_text.get(k, ""))
                for k in sorted(expected - detected, key=str)],
        unexpected=[Detection(dossier_id=k[0], run_ref=k[1], failure=k[2],
                              rule_id=detection_rule.get(k))
                    for k in sorted(detected - expected, key=str)],
        dead_rules=sorted(rid for rid, score in per_rule.items() if score.dead),
        unevaluated_domains=sorted(unevaluated),
        not_scoreable=excluded,
        model_judged_failures=sorted(judged_only),
    )


def now() -> str:
    return datetime.now(timezone.utc).isoformat()
