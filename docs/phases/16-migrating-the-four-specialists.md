# Phase 16 — Migrating the four specialists (migration-plan.md Phase 3)

Status: complete. Written before the code, per CLAUDE.md, from HANDOFF §4
(the agents), §5.1 (review scope) and migration-plan Phase 3; §7 and §8 were
filled in after. 343 tests; `collect_ignore` is empty.

Phase 2 already moved the four specialists' floors and KYA/Log/Drift's model
calls onto the dossier. What this phase adds is the substance the plan lists:

## 1. Mandate

- **`MND-SEM-01` becomes one whole-dossier, run-citing call.** The model is
  shown every run that reached a cart — the shopper's signed sentence, the
  merchant, the line items (merchant text delimited as untrusted), the total
  and the agent's own attestation (also untrusted) — and returns a verdict
  per run. Code validates every `run_id` against the runs it was shown:
  an invented id is dropped and logged, a run the model did not judge is an
  `inconclusive` assessment, every judged-consistent run rolls into one
  `clear` assessment citing its runs, and every mismatch is its own `breach`
  citing the run and the measurement fact the floor recorded for it. This
  is F49, the only source of it, and the reason the mandate lives on the run.
- **F50 — `MND-USE-01 single_use_mandate_not_reused`**, active. Per run: a
  single-use Intent whose `uses_consumed` exceeds `max_uses`, or whose
  `intent_mandate_id` an earlier run already drew on, is a breach. HANDOFF
  §6.2 lists it as a hard gate; the weight is 0.9 pending Phase 6.
- **F48 — `MND-CAP-04`** promoted from draft. Its blocker ("Merchant has no
  region field") is gone: every cart in the corpus carries `region`.
  `GLOBAL` scope is satisfied by any region; a named region must match; a
  cart with no region is `absent/missing_block`.

## 2. KYA

- **`REG-03`'s evidence widening.** KYA's view gains an `activity_summary`
  — count, total, largest single, distinct counterparties, in-window count,
  MCCs — computed from the transaction history the submission already
  carries (a `compose_context` change, no new firm data), plus the
  register's classification and declared purpose. The floor records it as
  a measurement behind `REG-03`, so the judgement has a fact to cite.
- When `REG-03` is active (it is draft; the sandbox promotes it), the
  ceiling's tool gains a `classification_fit` verdict that becomes a
  `breach`/`clear` assessment. When draft, the tool does not ask.

## 3. Log

- **F55's signal is a measurement.** `LOG-CON-01#new_payee_share`: each
  counterparty's share of the latest month, whether the register first saw
  it inside the review window, and the rule's `new_payee_min_share_pct`
  dial (20, from the verifier, now in `log.json` where a dial belongs). The
  verdict stays the model's — LOG-CON-01 is judged — but the number that
  makes "a brand-new recipient is suddenly getting most of the money"
  visible is now in front of it, and the critic can check it was quoted.

## 4. Drift

- **`change_log` as the onset.** `drift_stats.change_points()` evaluates the
  baseline statistics before and after each dated `change_log` event:
  amount shift, counterparty-mix PSI, MCC-mix PSI, counts. The model names
  the event the onset lands on (`onset_event_ref`); code validates the ref
  against the log — an invented ref becomes `null` — and the assessment
  carries it as its subject and an evidence ref. F65 is "something specific
  changed it", and now the answer is a `change_log` entry, not a date.

## 5. Prompts

The specialist bodies are data (`registry/prompts/*.json`) and still
described one case with one mandate. Rewritten for the dossier: Mandate's
entirely (new tool, per-run verdicts, run ids mandatory); KYA's, Log's and
Drift's for the widened evidence and the new fields; the dispatcher's for a
dossier of runs. Versions bumped to 2026.2.

## 6. The gate, honestly stated

The plan's gate is "all planted computable defects found by agents on the
graph". With four agents on the graph, that is the four agents' share:

| planted | found by | on the graph |
|---|---|---|
| F42 cap · F44 category · F50 reuse · F32 (line-item channel) | Mandate floor | yes |
| F21 credential overlap | KYA floor | yes |
| F49 not what was asked | Mandate's model call | only with a live model |
| F55 new payee | Log's model call, over the new measurement | only with a live model |
| F24 F29 · F33 F36 F37 F19 · F52 · F71 F72 · F32 (retrieved-content channel) | Consent · Provenance · Counterparty · Control Assurance · Injection | Phase 4 |

## 7. Numbers

| | Kestrel | Halcyon |
|---|---|---|
| facts on the triage graph | 1,139 (was 1,038) | 480 (was 439) |
| assessments with the fake model | 12: 6 breach, 1 explained, 5 clear | 6: 1 breach, 5 clear |
| breaches | `KYA-LIF-04` · `MND-CAP-01` `MND-CAP-02` `MND-CAP-05` `MND-USE-01` `MND-SEM-02` | `MND-CAP-02` |
| `MND-SEM-01` | one `clear` citing 49 runs and 49 measurements (fake-consistent) | one `clear` citing 20 |
| score (Phase 6 replaces it) | 4.3 (3.4 + `MND-USE-01` at 0.9) | 0.7 |
| the fidelity payload | 49 runs, 45 KB, both untrusted channels fenced | 20 runs |

## 8. What this phase exposed

- **Halcyon's `change_log` names Kestrel's prompt release** —
  `kestrel-shop-v2.4.1 -> v2.5.0` on 2026-07-20, in a dossier whose runs
  executed on `halcyon-buy-v1.8.2` and `v1.9.0`. A corpus slip in
  `data/authored/`, not a code problem; it does not change any finding
  today (the onset lands on `MER-QVC-8801` in both dossiers), but a Drift
  onset naming a release the agent never ran would be wrong, so it should
  be corrected before the eval.
- **`MND-CAP-04` is live but exercised nowhere.** Every scope in the corpus
  is `GLOBAL`. A run with a named region and a merchant elsewhere would
  make it a demonstrated rule; the test constructs one, the corpus does not.
- **`MND-USE-01` and `MND-CAP-05` now both fire on run 48.** The double
  draw breaches the reuse rule and, because both draws settled, the
  cumulative cap. Two rules, one event — the Phase 6 synthesizer's
  `same_event` case again.
- **Supersession is per rule, not per assessment.** A whole-dossier judged
  call re-decides every run of its rule; round 2's answers replace round 1's
  for that rule wholesale, so a round-1 breach on a run that round 2 finds
  consistent does not survive next to round 2's `clear`. `supersedes` on an
  assessment is the audit pointer; `agents/assess.py::superseded_ids` is the
  rule.
