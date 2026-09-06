"""E2 Systemic — the portfolio sweep.

The only specialist whose question cannot be asked of one submission. Everything
else in the roster reviews an agent; this reviews the *population*, and its
findings are properties of the market rather than of any operator in it.

Three failures live here, and each is invisible from inside a single dossier:

  F57  the same payee is being paid by firms that have nothing to do with
       each other
  F67  everyone is running the same model, so one provider incident is a
       correlated failure across the whole population
  F68  agents at unrelated firms are moving together, and no single
       submission can see it
  F69  the same attack is running at several firms at once

The hard part of F57 is not finding shared counterparties — most are shared,
because popular retailers are popular. It is separating a genuinely suspicious
payee from an ordinary one, which is why this reads concentration and recency
rather than mere presence.

Needs nothing new from firms. Everything here is computable from dossiers
already submitted, which is the whole argument for the tier: twelve failures in
the coverage model need no new data at all, only somewhere to look from.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from data.registries import load_merchants
from schemas.dossier import LoadedDossier


@dataclass
class PortfolioFinding:
    """A finding scoped to a set of dossiers rather than to one case.

    `subject_refs` names every dossier the claim rests on. A portfolio finding
    that cannot say which submissions it spans is an assertion, not evidence —
    and it is the field a supervisor needs to act, because acting means writing
    to those operators.
    """

    finding_id: str
    failure: str
    subject: str
    subject_refs: list[str]
    summary: str
    details: dict = field(default_factory=dict)


def _spend_by_counterparty(d: LoadedDossier) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for t in d.transaction_history:
        if t.run_ref and t.status == "settled":
            out[t.counterparty_id] += t.amount
    return out


def shared_counterparty_concentration(
        dossiers: list[LoadedDossier], *, min_share: float = 15.0,
        min_operators: int = 2, recent_days: int = 90) -> list[PortfolioFinding]:
    """F57 — one payee taking a disproportionate share at unrelated firms.

    Three conditions together, because any one alone is ordinary:

      * the payee appears at `min_operators` or more operators — on its own
        this describes every popular retailer;
      * it holds at least `min_share` of in-window spend at each — popularity
        is broad and shallow, this is narrow and deep;
      * it was first seen recently — an incumbent that grew into a large share
        over years looks nothing like one that arrived last month.

    Drop any of the three and the rule reports the whole high street.
    """
    merchants = load_merchants()
    by_cp: dict[str, dict[str, float]] = defaultdict(dict)
    for d in dossiers:
        spend = _spend_by_counterparty(d)
        total = sum(spend.values()) or 1.0
        for cp, amount in spend.items():
            by_cp[cp][d.dossier.dossier_id] = 100 * amount / total

    findings, n = [], 0
    for cp, shares in by_cp.items():
        qualifying = {k: v for k, v in shares.items() if v >= min_share}
        if len(qualifying) < min_operators:
            continue
        record = merchants.get(cp, {})
        first_seen = record.get("first_seen")
        recent = False
        if first_seen:
            newest_window = max(datetime.fromisoformat(d.dossier.submission_context.executed_to)
                                for d in dossiers)
            age = (newest_window.date() - datetime.fromisoformat(first_seen).date()).days
            recent = age <= recent_days
        if not recent:
            continue
        n += 1
        hits = {
            d.dossier.dossier_id: sorted({
                t.run_ref for t in d.transaction_history
                if t.counterparty_id == cp and t.run_ref and t.status == "settled"
            })
            for d in dossiers if d.dossier.dossier_id in qualifying
        }
        findings.append(PortfolioFinding(
            finding_id=f"PORT-F57-{n:03d}", failure="F57",
            subject=record.get("legal_name", cp), subject_refs=sorted(qualifying),
            summary=(
                f"{record.get('legal_name', cp)} holds "
                + ", ".join(f"{v:.0f}% of {k}" for k, v in sorted(qualifying.items()))
                + f" — a counterparty first seen {first_seen}, {age} days before the end of the "
                  f"review window, reaching a large share at {len(qualifying)} unrelated "
                  f"operators at once."),
            details={"counterparty_id": cp, "shares": shares, "first_seen": first_seen,
                     "beneficial_owner": record.get("beneficial_owner"),
                     "watchlist_flags": record.get("watchlist_flags", []),
                     "hits": hits,
                     "min_share": min_share, "recent_days": recent_days}))
    return findings


def model_monoculture(dossiers: list[LoadedDossier], *,
                      max_share: float = 60.0) -> list[PortfolioFinding]:
    """F67 — everyone running the same model.

    Not a defect in any operator: each one independently picked a good model,
    and every individual choice is defensible. The risk is emergent — one
    provider incident becomes a correlated failure across the whole population,
    and nobody who could see it was looking at the population.

    A judgement about concentration, so `max_share` is a dial. It is also the
    finding most likely to be trivially true in a small corpus, which is worth
    saying out loud rather than letting a demo imply otherwise.
    """
    versions: dict[str, set[str]] = defaultdict(set)
    for d in dossiers:
        for r in d.runs:
            versions[r.construction_context.model.observed_version].add(d.dossier.dossier_id)
    total = len(dossiers)
    findings, n = [], 0
    for version, owners in versions.items():
        share = 100 * len(owners) / total
        if share < max_share:
            continue
        n += 1
        findings.append(PortfolioFinding(
            finding_id=f"PORT-F67-{n:03d}", failure="F67", subject=version,
            subject_refs=sorted(owners),
            summary=(f"{len(owners)} of {total} agents in the portfolio ({share:.0f}%) run "
                     f"{version}. No operator has done anything wrong; the exposure is that a "
                     f"single provider incident would land on all of them at once."),
            details={"model_version": version, "operators": sorted(owners),
                     "share_pct": round(share, 1), "max_share": max_share,
                     "population_size": total}))
    return findings


def shared_attack_content(dossiers: list[LoadedDossier], *,
                          min_operators: int = 2) -> list[PortfolioFinding]:
    """F69 — the same attack running at several firms at once.

    This is where `result_digest` earns its place. The digest cannot reveal that
    content carries an injection — only reading the text does that — but once
    one firm's excerpt has been read, the SAME digest appearing at another firm
    identifies the same payload without anyone reading it twice. Correlation is
    what the hash is for; detection is not.
    """
    from scripts.verify_dossier import INJECTION  # the shared triage net

    by_digest: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    poisoned: set[str] = set()
    for d in dossiers:
        for r in d.runs:
            for tc in r.construction_context.tool_calls:
                if tc.result_excerpt is None:
                    continue
                by_digest[tc.result_digest][d.dossier.dossier_id].append(r.run_id)
                if INJECTION.search(tc.result_excerpt.text):
                    poisoned.add(tc.result_digest)

    findings, n = [], 0
    for digest, hits in by_digest.items():
        if len(hits) < min_operators or digest not in poisoned:
            continue
        n += 1
        findings.append(PortfolioFinding(
            finding_id=f"PORT-F69-{n:03d}", failure="F69", subject=digest[:23] + "…",
            subject_refs=sorted(hits),
            summary=(f"Identical retrieved content flagged as carrying an injected instruction "
                     f"appears at {len(hits)} unrelated operators: "
                     + "; ".join(f"{k} ({len(v)} run(s))" for k, v in sorted(hits.items()))
                     + ". One campaign, several targets, and no single submission can see it."),
            details={"result_digest": digest, "hits": {k: v for k, v in hits.items()}}))
    return findings


def behavioural_correlation(dossiers: list[LoadedDossier], *,
                            min_overlap_days: int = 30,
                            max_correlation: float = 0.7) -> list[PortfolioFinding]:
    """F68 — independent agents moving together.

    Agents at unrelated firms converging on the same rhythm at the same time.
    Individually every day is unremarkable; the correlation is the finding. It
    matters because correlated behaviour amplifies market stress — agents on
    similar models emphasise the same signals and make the same errors under
    pressure, which is the mechanism behind a flash crash, and the reason the
    FSB and BIS name it. Genuinely independent agents should not move this
    tightly together, so tight correlation means an undeclared shared trigger,
    a real market event, or a common compromise.

    Pearson correlation of daily transaction counts over the span two agents
    actually share — first to last shared active day, absences inside it kept.
    The span matters: correlating over the whole calendar union counts the
    months before one agent existed as agreement, which turned a -0.117 pair
    into +0.513 when first measured that way.

    Measured over the span two agents actually share, pairwise daily-count correlation across the four corpus dossiers runs -0.34 to +0.06, and two of the six pairs have too little overlap to measure at all. So 0.7 leaves
    real headroom, but four agents is a small population and daily counts are
    sparse: the dial is asserted rather than proven and belongs in a sandbox
    sweep before it binds anyone.

    `min_overlap_days` exists because a correlation over a fortnight is
    arithmetic, not evidence — and it is why two corpus pairs report nothing
    rather than a number nobody should trust.
    """
    import statistics

    series: dict[str, dict[str, int]] = {}
    for d in dossiers:
        by_day: dict[str, int] = defaultdict(int)
        for t in d.transaction_history:
            by_day[t.timestamp[:10]] += 1
        if by_day:
            series[d.dossier.dossier_id] = by_day

    findings, n = [], 0
    for a, b in sorted((a, b) for i, a in enumerate(sorted(series))
                       for b in sorted(series)[i + 1:]):
        overlap = sorted(set(series[a]) & set(series[b]))
        if len(overlap) < min_overlap_days:
            continue
        # Every day in the shared span, absences included: two agents that are
        # both quiet on the same days are correlated, and dropping the zeros
        # would hide exactly that.
        span = [d for d in sorted(set(series[a]) | set(series[b]))
                if overlap[0] <= d <= overlap[-1]]
        xs = [series[a].get(d, 0) for d in span]
        ys = [series[b].get(d, 0) for d in span]
        if len(set(xs)) < 2 or len(set(ys)) < 2:
            continue
        r = round(statistics.correlation(xs, ys), 3)
        if r < max_correlation:
            continue
        n += 1
        findings.append(PortfolioFinding(
            finding_id=f"PORT-F68-{n:03d}", failure="F68", subject=f"{a}~{b}",
            subject_refs=[a, b],
            summary=(f"Daily activity at {a} and {b} moves together with a correlation of {r} "
                     f"across {len(span)} shared days. Neither firm can see this, and nothing in "
                     f"either submission is wrong on its own."),
            details={"correlation": r, "shared_days": len(span),
                     "window": [span[0], span[-1]], "max_correlation": max_correlation}))
    return findings


def _dials(ruleset, rule_type: str) -> dict:
    """The active rule's params, or {} — which leaves each sweep on its own
    signature defaults. Every dial here is data now: a threshold that lives
    only in a Python default is the one supervisory judgement a regulator
    cannot sweep, compare or promote, which is precisely backwards for the
    market-level layer."""
    if ruleset is None:
        return {}
    rule = next((r for r in ruleset.rules if r.type == rule_type and r.status == "active"), None)
    return typed_params(rule).model_dump() if rule is not None else {}


def sweep(dossiers: list[LoadedDossier], ruleset=None) -> list[PortfolioFinding]:
    """The full portfolio sweep. A scheduled run kind, not a per-case one.

    `ruleset` is taken as an argument rather than loaded, exactly as every
    other specialist takes its book — which is what lets the sandbox run this
    sweep against a draft without touching the code.
    """
    if len(dossiers) < 2:
        # Honest rather than empty: with one submission there is no portfolio,
        # and reporting nothing would read as "nothing found".
        raise ValueError("a portfolio sweep needs at least two dossiers")
    # A rule that is retired or drafted in the book handed in does not sweep.
    def on(rule_type: str) -> bool:
        return ruleset is None or any(r.type == rule_type and r.status == "active"
                                      for r in ruleset.rules)
    out: list[PortfolioFinding] = []
    if on("shared_payee_concentration"):
        out += shared_counterparty_concentration(dossiers, **_dials(ruleset, "shared_payee_concentration"))
    if on("model_monoculture"):
        out += model_monoculture(dossiers, **_dials(ruleset, "model_monoculture"))
    if on("shared_attack_payload"):
        out += shared_attack_content(dossiers, **_dials(ruleset, "shared_attack_payload"))
    if on("behavioural_correlation"):
        out += behavioural_correlation(dossiers, **_dials(ruleset, "behavioural_correlation"))
    return out


# ---------------------------------------------------------------------------
# The agent (E2)
# ---------------------------------------------------------------------------

from schemas import Assessment, EvidencePack, Fact, FactBuilder, Ruleset, typed_params  # noqa: E402

from .base import SpecialistReview, narrated  # noqa: E402


class SystemicAgent:
    """The only specialist whose evidence is many dossiers. Given a
    portfolio of at least two it runs the sweep; its findings are
    portfolio-scoped `concern`s naming the dossiers they span — none of
    F57, F67, F69 is a refusal of any one operator. Given fewer, the one fact
    it records is that there was no portfolio to look from. It has no
    rulebook: its three failures are properties of the population."""

    name = "systemic"

    def run(self, dossier: LoadedDossier, ruleset: Ruleset | None = None, *,
            evidence: EvidencePack | None = None,
            portfolio: list[LoadedDossier] | None = None) -> list[Fact]:
        fb = FactBuilder(dossier.dossier.dossier_id, self.name)
        portfolio = portfolio or [dossier]
        ids = sorted(d.dossier.dossier_id for d in portfolio)
        if len(portfolio) < 2:
            return [fb.measurement("portfolio", "One submission on the ledger: there is no portfolio to "
                                                "look from, and nothing here would read as 'nothing found'.",
                                   values={"portfolio": ids, "size": len(ids), "swept": False})]
        facts = [fb.measurement("portfolio", f"{len(ids)} submissions swept.",
                                values={"portfolio": ids, "size": len(ids), "swept": True})]
        for pf in sweep(portfolio, ruleset):
            facts.append(fb.measurement(
                pf.finding_id, pf.summary,
                values={"failure": pf.failure, "subject": pf.subject, "subject_refs": pf.subject_refs, **pf.details}))
        return facts

    def assess(self, facts: list[Fact], ruleset: Ruleset | None, dossier: LoadedDossier, *,
               round: int = 1) -> list[Assessment]:
        case_id = dossier.dossier.dossier_id
        out = []
        for f in facts:
            if not f.fact_id.split("#")[-1].startswith("PORT-"):
                continue
            hits = f.values.get("hits", {})
            run_refs = sorted({run_id for ids in hits.values() for run_id in ids}) if isinstance(hits, dict) else []
            out.append(Assessment(
                assessment_id=f"{case_id}:systemic:{f.values['failure']}:{f.values['subject']}:r{round}",
                case_id=case_id, round=round, scope="portfolio", agent=self.name, rule_id=None,
                fact_ids=[f.fact_id], verdict="concern", confidence="probable",
                subject=f"{f.values['failure']}:{f.values['subject']}", subject_refs=f.values["subject_refs"],
                run_refs=run_refs,
                run_refs_by_case=hits if isinstance(hits, dict) else {},
                narrative=f.statement))
        return out

    async def review(self, dossier: LoadedDossier, ruleset: Ruleset | None = None, *,
                     evidence: EvidencePack | None = None, model=None,
                     portfolio: list[LoadedDossier] | None = None, round: int = 1,
                     prompts: dict | None = None, narrate: bool = True,
                     **_ignored) -> SpecialistReview:
        facts = self.run(dossier, ruleset, evidence=evidence, portfolio=portfolio)
        # Narrates like the peers do. The sweep itself stays model-free: what
        # it found is arithmetic over every submission on the ledger, and the
        # call only puts that in the officer's language.
        return await narrated(
            SpecialistReview(facts=facts, assessments=self.assess(facts, ruleset, dossier, round=round)),
            self.name, dossier, model=model, prompts=prompts, narrate=narrate)
