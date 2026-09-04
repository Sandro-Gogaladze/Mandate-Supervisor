# Phase 17 — The seven new specialists (migration-plan.md Phase 4)

Status: in progress. Written before the code, per CLAUDE.md, from HANDOFF §3
(nine rulebooks), §4 (the eleven agents) and migration-plan Phase 4. The eval
(Phase 10) is deliberately skipped on the user's instruction.

## 1. The four missing rulebooks

Rules are data, and these four books did not exist. Each is designed from the
coverage-model rows the agent owns and from what the two dossiers actually
carry; every rule declares the failure ids it detects (`failures`, a new
optional field on `Rule`), which is what lets Control Assurance learn from its
peers by rule rather than by a hand-kept map, and what an eval will read.

| book | agent | rules | computable | judged |
|---|---|---|---|---|
| `consent.json` | Consent & Harm | 10 | presence (F24), record (F31), principal, method (F27), rendered vs signed (F29), caps shown, scope (F26), freshness (F25), standing vs single-use (F30) | value-for-money (F38) |
| `injection.json` | Injection | 5 | four channels: listing text, the shopper's prompt, retrieved content, tool schema hash | did the agent act, and through which channel (F32, F35) |
| `counterparty.json` | Counterparty | 10 | register (F51), sub-merchant (F52), Confirmation of Payee, country, barring list (F54), identifiable owners (F53), new-payee concentration (F55), split identities (F56) | declines clustering (F58), is this payee what it appears (fronting) |
| `provenance.json` | Provenance | 5 | `KYA-TEC-02/05/06` moved here, plus card-vs-credential | the four-source reconciliation |

Two rules move between books, on the ownership-by-evidence rule:
`MND-SEM-02`, the line-item injection heuristic, becomes `INJ-LST-01` (it is
one of Injection's four channels, and two agents asserting the same line
item is the duplication the principle exists to remove); `KYA-TEC-02/05/06`
leave `kya.json` for `provenance.json`, keeping their ids. `kya.json` goes to
39 rules, `mandate.json` to 14.

F28 (a consent screen designed to get a yes) stays parked: it needs a picture
of the screen, which the data contract deliberately does not ask for.

## 2. Value-for-money is judged, not computed

`selection_context.alternatives_considered` in this corpus are the other
products the catalogue search returned — running shoes as an alternative to a
dutch oven. A rule "a cheaper alternative existed" fires on 48 of 50 Kestrel
runs and means nothing. Whether the cheaper option was *equivalent* is a
judgement; the floor records the selected price against the alternatives as a
measurement per run and the model judges across runs whether the agent
systematically chooses worse. F38's own verifier row already says "judged".

## 3. The agents

All seven conform to the Phase 2 contract (`run` → facts, `assess` → floor
assessments, `review` → one contained model call) and each has an empty tool
set in `AGENT_TOOLS` — schema-constrained output only.

- **Consent & Harm**, **Injection**, **Counterparty**: new check modules and
  one model call each, over dossier-level views like Log's and Drift's.
  Injection's assessment carries the channel as its subject.
- **Provenance**: `provenance_checks.py` gains the card-vs-credential rule and
  reads its own book; the model call reconciles the four sources.
- **Control Assurance**: wraps `control_checks.py`. Its peers are the other
  agents' breach facts, mapped to failure ids through the rules' `failures`
  declarations. Posture — absent / failed / bypassed / ineffective — is
  computable from the CTL facts and is recorded as `ControlPosture`; no model
  call is needed for it, so none is made.
- **Systemic**: wraps the portfolio sweep. Its evidence is many dossiers; the
  graph will hand it every submission on the ledger. Fewer than two is an
  honest absence, not an empty sweep. Its findings are portfolio-scoped
  `concern`s with `subject_refs` — none of F57, F67, F69 is a refusal.
- **Red Team**: on demand, no model. Generates probe runs from the mandate's
  own parameters — a cart one unit over the cap, a merchant outside the
  category, a second draw on a single-use mandate, an injected line item, a
  merchant outside a named region — runs the deterministic floors over them,
  and reports which probes the operator's *declared controls* would have
  addressed and which would have passed unopposed.

## 4. Not in this phase

The skill registry, the round-1 dispatch rule and the graph fan-out to ten
peers plus a sequenced Control Assurance (Phase 5); scoring (Phase 6); the
eval (skipped).

## 5. Numbers

Measured on 2026-09-03 with the fake model (every judged verdict "clean"), so
the assessments below are the floor plus one `clear` per judged rule.

| Agent | Kestrel facts · assessments | Halcyon facts · assessments | Finds |
|---|---|---|---|
| Provenance | 152 · 4 | 62 · 1 | F33, F36, F37 on their runs; card within credential on both |
| Injection | 202 · 6 | 81 · 3 | listing channel on run 25, retrieved channel on runs 40 and 11; one run's calls carry no excerpts (a named gap) |
| Counterparty | 255 · 5 | 105 · 4 | F52 on run 33; F55 pinned to the latest Quickvale run on both; Quickvale's owner unresolved on both (dossier-level) |
| Consent & Harm | 499 · 5 | 200 · 1 | F24 on run 42 (and the missing block named), F29 on run 15; a selection measurement on all 49 / 20 carts |
| Control Assurance | 358 · 3, 5 postures | 148 · 2, 1 posture | fed by the peers' breach facts through `Rule.failures`: EFF-01 on runs 39/42/48, EFF-03, EFF-04; postures effective · bypassed (ops-analyst-11) · ineffective ×3 |
| Systemic | 4 · 3 concerns | same | over the two-dossier portfolio: F57 Quickvale, F67 one model, F69 identical injected content; alone, one fact saying there is no portfolio |
| Red Team | 5 probes · 2 concerns | same | over-cap, out-of-category and mandate-reuse are addressed by declared controls; **injected listing and off-region pass unopposed** at both operators |

No breach fact on any run the ground truth calls clean, on either dossier
(`tests/test_fact_contract.py`). Nine rulebooks, 96 active rules. Assessment
ids never collide across the eleven agents.

**A regression that is honest, not accidental.** The triage graph still
dispatches the four migrated agents only (the fan-out for eleven is Phase 5),
and the line-item injection finding left the Mandate book for Injection's.
Kestrel's triage therefore records 1,089 facts and 11 assessments instead of
1,139 and 12, and scores 3.7 instead of 4.3, until Injection is on the graph.
The tests assert the new numbers and say why.

Suite: 399 tests, all passing. `scripts/verify_dossier.py` still imports
nothing from `agents/` and passes on both dossiers.

## 6. Found along the way

- A test that mutates a registry entry it fetched through `load_merchants()`
  mutates the cached dict every later test reads. Three clean runs grew a
  `sanctioned` flag and the whole suite went red two modules later. The
  context builders now copy the registry; the bug was the test's, not the
  data's — the register carries no barring flag anywhere.
- Neither operator declares a control against listing injection or against
  geography. The Red Team finds it in seconds; nothing else in the pipeline
  would have said so, because both are things that did not happen.

