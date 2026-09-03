"""E2 Systemic — the portfolio sweep.

The only specialist whose question cannot be asked of one submission. Everything
else in the roster reviews an agent; this reviews the *population*, and its
findings are properties of the market rather than of any operator in it.

Three failures live here, and each is invisible from inside a single dossier:

  F57  the same payee is being paid by firms that have nothing to do with
       each other
  F67  everyone is running the same model, so one provider incident is a
       correlated failure across the whole population
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


def shared_attack_content(dossiers: list[LoadedDossier]) -> list[PortfolioFinding]:
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
        if len(hits) < 2 or digest not in poisoned:
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


def sweep(dossiers: list[LoadedDossier]) -> list[PortfolioFinding]:
    """The full portfolio sweep. A scheduled run kind, not a per-case one."""
    if len(dossiers) < 2:
        # Honest rather than empty: with one submission there is no portfolio,
        # and reporting nothing would read as "nothing found".
        raise ValueError("a portfolio sweep needs at least two dossiers")
    return [*shared_counterparty_concentration(dossiers),
            *model_monoculture(dossiers),
            *shared_attack_content(dossiers)]
