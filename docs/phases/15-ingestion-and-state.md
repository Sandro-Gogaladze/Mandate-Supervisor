# Phase 15 — Ingestion and state (migration-plan.md Phase 2)

Status: complete. Written before the code, per CLAUDE.md, from HANDOFF §5
(intake), §9 (decisions) and migration-plan Phase 2; §7 and §8 were filled
in after. 329 tests (from 189); the parked list is down to one module.

## 1. What this phase delivers

The `Dossier` through the graph. Concretely:

- **Intake is code, zero model calls.** `ingestion/normalize.py::normalize_dossier()`
  takes a `LoadedDossier` (the loader has already verified the run index
  against the file digests — a submission that contradicts its own attestation
  never gets this far) and produces an **`EvidencePack`**: every signature and
  chain link verified, all six registries resolved, the shared statistics
  computed once, and which submission blocks are present per run. No rules are
  evaluated here except the eight cryptographic/chain ones the rulebooks assign
  to intake (`KYA-IDN-01/02/03`, `ACC-03`, `ISS-01/02`, `MND-CHN-01/02`), which
  now produce **facts** like everything else — Phase 1's contract, completed.
- **State** (`pipeline/state.py`): `dossier`, `evidence`, `run_scope`, plus
  `facts` and `assessments` under dedup reducers. `case: IngestedCase` and
  `ingestion_findings` are gone. `findings` stays as the projection the
  synthesis tail (critic, synthesizer, score, drafting) still reads.
- **The ledger** records a dossier as one `case_submitted` event carrying the
  submission (dossier.json, the runs, the institution's ledger, and the
  registry-resolved `firm` block the projection and console read), and two new
  event types: `fact_recorded` and `assessment_recorded`, one per fact and per
  assessment. An append costs 0.3 ms, so 1,400 facts is under half a second;
  each fact gets its own seq and actor, as findings do.
- **The `CaseBundle` path is deleted**: `schemas/case.py`, `data/loader.py`,
  `IngestedCase`, `normalize_case*`, the manifest. `agents/context.py`,
  `agents/tools.py`, `agents/investigator.py`, `agents/skills.py`,
  `pipeline/dispatch.py`, `api/main.py`, `ledger/seed.py` and `data/uploads.py`
  move to the dossier.
- **The four specialists run on the graph over the dossier.** Their
  deterministic floors return facts (Phase 1); the graph turns facts into floor
  assessments (`agents/assess.py`) and projects them to findings for the tail.
- **Parked test modules come back** as their subjects land — see §6.

## 2. The EvidencePack

`schemas/evidence.py`. What every agent's briefing can draw on without
recomputing, and what the orchestrator's round-1 rule ("dispatch every agent
whose evidence block is present") will read in Phase 5.

| section | holds |
|---|---|
| `blocks` / `run_blocks` | which optional blocks the submission carries, dossier-level and per run — `consent_ceremony`, `rendered_values`, `selection_context`, `result_excerpt`, `payee`, `sub_merchant`, `usage`, … |
| `integrity` | every Intent/Cart/Payment/credential signature verified, chain links recomputed; failures named |
| `registries` | which of institution / operator / agent / issuer resolved, and the counterparties `merchants.json` does not know |
| `submission` | `runs_submitted` vs `runs_executed_total`, deployment target vs what the runs observed — the raw comparisons behind S2/S3/S4, not the verdicts |
| `counterparties` | per-payee count, total, share, first/last seen, MCCs, registry ownership and flags |
| `timing` / `amounts` | hour and weekday histograms, off-hours share, gap statistics, amount distribution |
| `drift` | the baseline/comparison split and its PSI, z-score and frequency shift, with `sufficient` against the Drift rule's minimum |
| `controls` | evaluations, triggers, overrides, per control, and runs with no evaluation |
| `ingestion_facts` | the eight intake rules as facts, against the active books |

The statistics reuse `agents/log_stats.py` and `agents/drift_stats.py` — pure
pandas, no model — rather than a second implementation.

## 3. Decisions taken in this phase

- **The submission payload inlines the runs.** Phase 7 says runs should be
  referenced by digest rather than inlined; that needs a content-addressed run
  store the ledger does not have yet. For now `case_submitted` carries the
  parsed run dicts; the loader verified the file digests at the door and the
  hash chain protects the payload thereafter. Rebuilding a dossier from the
  ledger re-validates the schema and index membership, not the file digests
  (there are no files). Phase 7 reseeds anyway.
- **A `clear` verdict.** Log's and Drift's rules are judged; when the model
  judges a rule clean there was no vocabulary for it — `explained` means "a
  rule tripped and, in context, it is fine", `inconclusive` means undecided.
  "Evaluated, nothing wrong" is the assessment-level twin of a `satisfied` fact
  and is now `clear`. It does not score. Without it a clean judged rule was
  silence again.
- **KYA, Log and Drift reasoning move to the dossier in this phase; Mandate's
  does not.** Their evidence is dossier-level already (the credential; the
  whole transaction history), so the adaptation is the input view and the
  output type (Finding → Assessment citing measurement facts) — done once.
  Mandate's semantic check is per cart and becomes a whole-dossier,
  run-citing call in Phase 3; until then `MND-SEM-01` has measurements and no
  verdict, visibly.
- **`FactBuilder` moves to `schemas/fact.py`.** Intake mints facts too, and
  ingestion importing from `agents/` is the wrong direction. `agents/facts.py`
  re-exports it.
- **The mandate book has no rule for "the Intent, Cart and Payment signatures
  verify".** `MND-CHN-01/02` check the hash links; nothing checks that the
  signed objects were signed by a key the keystore knows. Intake now verifies
  every signature into `evidence.integrity`, and `MND-SIG-01` is added to
  `mandate.json` as a **draft** rule so the gap is a fact on every case rather
  than an omission — promoting it is the user's call.

## 4. What this phase does not do

- The orchestrator still proposes four specialists and the graph topology is
  unchanged (Phase 5). `run_scope` is plumbed but nothing narrows it yet.
- Scoring is unchanged (Phase 6); it sums the projected findings of the four
  agents.
- Provenance and Control Assurance have checkers but no agent node (Phase 4).
- The console is unchanged (Phase 9); its case-file panel reads the old bundle
  shape.
- Mandate's LLM call, F50/F48 rules, REG-03's context widening and Drift's
  `change_log` onset are Phase 3.

## 5. The gate

The triage graph runs end to end on `DOSSIER-KST-2026-001` with the four
specialists and produces the breach assessments the Phase 1 modules produce
from scripts; the ledger chain verifies; the parked graph, dispatch, skills,
tools, context, upload and orchestrator modules run again.

## 6. Progress bar

Taken off `collect_ignore` in this phase, each rewritten on the dossier
fixture (`tests/corpus.py`): `test_ingestion`, `test_dispatch`, `test_skills`,
`test_tools`, `test_context_composition`, `test_agents`, `test_triage_run`,
`test_drafting_run`, `test_step_stream`, `test_orchestrator`,
`test_investigator`, `test_end_to_end`, `test_uploads`, `test_prompts`,
`test_kya_agent`, `test_log_agent`, `test_log_reasoning`, `test_drift_agent`,
`test_drift_reasoning` — nineteen. Two were deleted because their subject no
longer exists: `test_mandate_agent` (the floor is covered by
`test_mandate_checks`, the contract by `test_agents`) and
`test_finding_id_collision` (ids are `<case>:<rule>[:<run>]` now; the
collision class is structurally impossible and `test_fact_contract` asserts
uniqueness). One stays parked: `test_mandate_reasoning`, Phase 3's.

## 7. Rounds and supersession

A later triage or investigation pass is a new **round** of the same review
(`review_round` in state, derived from the record: one plus the number of
triage/investigation runs already on it). Round 2's assessment of a claim
round 1 already made carries `supersedes`; both stay on the ledger, and the
projection and scoring read only the current one. A directed pass that
re-runs a deterministic floor over an unchanged dossier does not re-record
its facts — the ids are deterministic and the record already has them. This
is what makes "the officer's question changed Log's mind" a ledger fact
with a before and an after, rather than two findings that both count.

## 8. Numbers

| | Kestrel | Halcyon |
|---|---|---|
| intake (signatures, chains, registries, statistics, blocks) | 30 ms · 158 signatures · 96 chain links | 245 ms (first call, registry load) · 68 · 40 |
| triage with the fake model | 0.5 s · 1,038 facts · 10 assessments · 1,067 ledger events | 439 facts · 1 breach |
| breach assessments | `KYA-LIF-04`, `MND-CAP-01`, `MND-CAP-02`, `MND-CAP-05`, `MND-SEM-02` (+ one `explained`) | `MND-CAP-02` |
| judged verdicts | Log 3 `clear`, Drift 1 `clear` (fake model) | same |
| score (Phase 6 replaces it) | 3.4 | 0.7 |

## 9. What the migration exposed

- **The mandate book had no rule for mandate signatures** (§3). `MND-SIG-01`
  is in `mandate.json` as a draft; its checker runs when promoted.
- **A thin history is a data-gap concern, not silence.** Drift below its
  minimum and Log with no history both roll up into one `concern` on the
  case naming `transaction_history` — the first time the pipeline says
  "could not evaluate" about a submission rather than skipping it.
- **The console's case-file panel reads the old bundle shape.** It now shows
  a placeholder for a dossier instead of crashing the review page; the run
  list and run detail are Phase 9.
