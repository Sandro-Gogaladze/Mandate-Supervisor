# Phase 14 — Facts and Assessments (migration-plan.md Phase 1)

Status: complete. Every deterministic checker returns `list[Fact]`; agents turn
facts into `Assessment`s (`agents/assess.py`); `Finding` is a projection of an
Assessment. The four check modules — `kya_checks` (28 checkers), `mandate_checks`
(10), `control_checks` (15), `provenance_checks` (3) — are migrated and run
against the two dossiers. 188 tests, up from 117; `scripts/verify_dossier.py`
unchanged and passing, still importing nothing from `agents/`.

## 1. The contract

A checker returns exactly one fact per rule per scope unit. Rule outcomes are
`breach` / `satisfied` / `absent`; judged rules get a `measurement` carrying the
evidence their reasoning pass will decide over. `absent` must say why:

| reason | meaning | rolls up into a data-gap finding? |
|---|---|---|
| `missing_block` | the firm did not submit the evidence | **yes** |
| `insufficient_history` | submitted, but too thin to support the rule | **yes** |
| `out_of_scope` | the rule does not apply to this run or case shape | no |
| `rule_draft` | the rule is not active in this ruleset version | no |
| `no_registry_record` | the regulator's own register has no entry to check against | no — the regulator's gap, not the firm's |
| `awaiting_peers` | the rule consumes another specialist's output, not yet supplied | no |

The last two are additions to the plan's four. `no_registry_record` replaced the
five registry-backed rules' silent `None`; `awaiting_peers` is what `CTL-EFF-01`
says when Control Assurance runs before the peers, which the old contract
could not distinguish from "the peers found nothing".

A gap-naming reason (`missing_block`, `insufficient_history`,
`no_registry_record`, `awaiting_peers`) must fill `Fact.missing` with the block,
field or register entry — `kya_credential.revocation_checked_at`,
`registry:agents[AGT-KST-SHOP-01]`. Enforced in the schema, because "could not
evaluate" without saying why is not a supervisory fact; it is what the console's
`AbsentNotice` renders.

Facts carry `run_ref`. Ids are deterministic — `<case>:<rule>[:<run>]` — so a
retried node reproduces them and the state reducer dedups.

## 2. Scope is a property of the rule

Decided by what the rule's answer depends on, not by which book it is in.

| | run-level (one fact per run) | dossier-level (one fact) |
|---|---|---|
| **KYA** | `ACC-02` `TEC-01` `TEC-03` `TEC-04` `REG-05` (read the run's Intent) · `LIF-01` `REG-01` `REG-04` (hold *at time of use*) | the other 20 — credential, chain, register, series |
| **Mandate** | all 10 | — |
| **Provenance** | all 3 | — |
| **Controls** | `DIS-01..04` `EFF-01` `EFF-02` `EFF-04` | `REP-01..04` `EFF-03` `LOG-01..03` |

"Time of use" is the run's `started_at`; "as of" for the staleness rules
(`ISS-04`, `LIF-05`) is `submitted_at`. Neither is wall-clock now — a review
replayed from the ledger reaches the same facts. A credential that expires
mid-window now breaches on the runs after it and is satisfied on the runs
before, which a single dossier-level answer could not say.

Per-run scope makes the fact table larger than a findings list: 1,433 facts for
Kestrel, 594 for Halcyon. That is the design — the run list needs a per-run
answer to show the clean majority as clean, the eval needs per-run true
negatives, and the reasoning pass reads a summary of the table, not the table.

## 3. What the dispatcher guarantees

`agents/facts.py::evaluate_ruleset()` walks the book in order: retired →
nothing; draft → one `absent/rule_draft`; active and listed as handled elsewhere
(ingestion's 8 cryptographic/chain rules, Provenance's 3 in KYA's book) →
nothing; active with a checker → facts; active, computable, no checker →
`NotImplementedError`. A judged rule may register a measurement producer and is
otherwise left to its reasoning pass. Duplicate fact ids raise.
`tests/test_fact_contract.py` asserts, over both dossiers, that every rule in
every book is accounted for by exactly one module, and that no checker is
registered for a rule type that does not exist — which is how the orphan
`consent_method_allowlist` checker was found (a checker for a rule that was never
in the book; deleted).

## 4. Assessments

`floor_assessments()` — one `breach` assessment per breached rule, citing every
breach fact and every run, severity at the ruleset floor, `scope="run"` when it
names runs (the schema rejects a run-scoped assessment naming none). Grouping
per rule rather than per fact is what lets a whole-dossier review make one
checkable claim — "the cap was breached on runs 43 and 48" — instead of two.

**One piece of context the floor applies itself, because it is mechanical.** A
breach on a run the firm's own blocking control stopped before any payment
(`outcome == "blocked"`) is assessed `explained`, not `breach`. Kestrel's
RUN-2026-0722-0030 is the case: a $770 cart against a $400 cap, `KST-CTL-001`
triggered, nothing paid. The corpus narrative calls it "the operator's own
budget control working correctly" and ground truth calls the run clean. The
*fact* stays a breach — the agent did build that cart, and how often it does is
supervisory information — but pricing it as a breach would score an agent worse
for having a control that works. `explained` is what that verdict exists for.
The reasoning pass may supersede it; an injection the cap control happened to
stop is not explained, and the floor does not pretend to know.

`data_gap_assessments()` — one `concern` per missing or too-thin block, naming
the rules it disabled and how many runs each touched. Nothing else absent rolls
up; a draft rule or an unfilled register is not the firm's gap.

`project_finding()` — an Assessment as a `Finding`, same id, `severity_weight`
= assessed severity × confidence for a breach and `None` for anything that does
not score. Everything that still consumes findings (scoring, the ledger, the
report) reads this view; no agent mints a Finding directly.

## 5. What the corpus exposed this time

- **`MND-CAP-05` was wrong for this data.** It summed the calendar month of
  `Payment.authorized_at`, a reading inherited from a standing corporate mandate
  with a monthly budget. On every run in both dossiers `max_cumulative_amount`
  equals `max_transaction_amount` — the mandate is one shopping task — so a
  monthly sum breached all 70 runs. The cap is a property of the mandate, so
  the rule now bounds the settled spend drawn on one `intent_mandate_id`, as of
  each run. That reading catches the F50 double draw (RUN-0048 on
  IM-KST-0817-0047: 48 + 64 = 112 against a cap of 70) and is the only rule
  that does until F50's own rule lands in Phase 3. It also duplicates `CAP-01`
  on the over-cap run — on a single-task mandate a cart over the per-transaction
  cap is over the cumulative cap by construction — which is the `same_event`
  case the Phase 6 synthesizer is designed to mark. Rule bumped to v2,
  `mandate.json` to v2026.3; the rule *type* keeps its name so registrations
  resolve.
- **Four rules declared `computable` and were not.** `MND-SEM-01` (prompt
  playback), `LOG-STR-01`, `LOG-CON-01`, `LOG-VEL-01` and `DRIFT-BHV-01` are all
  LLM-evaluated — their own descriptions say so — but `evaluation` defaulted to
  `computable`, and the dispatcher's loud-failure guarantee reads that field.
  Now `judged`; `log.json` v2026.3, `drift.json` v2026.2. `MND-SEM-01`'s
  `check()` records the shopper's sentence and the cart as a measurement, so the
  reasoning pass's assessment has a fact to cite.
- **`ACC-02`'s scope holds on the dossier.** Every run in both dossiers has a
  consumer principal, so the rule is `out_of_scope` on all 70 — visibly, rather
  than as 70 silent `None`s.
- **A held control was invisible.** `CTL-DIS-01/04` and `EFF-04` used to skip a
  run with no payment. A blocked run is the strongest evidence a blocking
  control is real; `DIS-04` now records "KST-CTL-001 rejected the action and no
  payment was authorised — the control held" as a `satisfied` fact.

## 6. One decision taken outside the plan's letter

The plan sequences the return-contract change (Phase 1) before moving the
input shape to the dossier (Phases 2–3). `kya_checks` and `mandate_checks` took
a `CaseBundle`, and no `CaseBundle` corpus exists any more — a checker migrated
on that input could not have been run against any data, and Phase 3 would have
rewritten its input anyway, which is exactly the double write Phase 1 exists to
avoid. They now take a `LoadedDossier`. Nothing of Phase 3's substance was
pulled forward: no `usage`/F50 rule, no `merchant.region`/F48, no per-line-item
LLM call, no `REG-03` context widening, no `change_log` for Drift.

## 7. What this phase does not do

- Ingestion's 8 cryptographic and chain-link rules (`KYA-IDN-01/02/03`,
  `ACC-03`, `ISS-01/02`, `MND-CHN-01/02`) still mint `Finding`s directly from the
  raw case dict in `ingestion/verify.py`. Phase 2 rewrites ingestion for the
  dossier and moves them onto the contract; until then they are the 8 rules with
  no fact, listed as handled elsewhere.
- `agents/kya.py` and `agents/mandate.py` still call the checkers with a
  `CaseBundle` inside `run()`. Both are dead paths (their tests are parked) and
  Phase 3 rewrites them; the call sites are commented.
- `CTL-EFF-01`'s peers are still keyed by coverage-model failure id, as the
  ground truth is. Control Assurance's agent (Phase 4) will fill them from peer
  assessments; the rule → failure mapping belongs with the rulebooks.
- Log and Drift are untouched beyond the `evaluation` correction.
- No eval. The contract test asserts the planted computable defects are found
  and the clean runs are clean at the assessment level; precision/recall is
  Phase 10.

## 8. Numbers

| | Kestrel (50 runs) | Halcyon (20 runs) |
|---|---|---|
| facts | 1,433 | 594 |
| breach facts | 15 | 2 |
| floor assessments | 11 breach + 1 explained | 2 breach |
| data-gap assessments | 0 | 0 |
| rules with a fact | 62 of 70 (8 are ingestion's) | 62 of 70 |
| planted computable defects found | 12 of 12 (F42 F44 F33 F36 F37 F21 F71×3 F72 F32-cart) | 2 of 2 (F44 F71) |
| breach facts on clean runs | 1, the contained one, named in the test | 0 |
