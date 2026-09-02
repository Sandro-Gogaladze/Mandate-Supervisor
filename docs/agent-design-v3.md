# Agent design v3 — from primitive verdicts to supervisory judgment

Extends `docs/architecture-v2.md`. That document fixed the **shape** of the system: who talks to
whom, what is recorded, where guarantees live. It deliberately froze the detection layer (§17: *"the
detection layer does not move"*). This document moves it.

Status: **proposed**. Written 2026-09-02 against `feat/orchestrator-led-supervision` @ `77f8cdb`,
after a full live run of every agent against the real API.

---

# Part I — What the agents actually do today

Read honestly, agent by agent: what evidence goes in, what reasoning happens, what comes out, and
where it is thin. Every defect below is observed in code or in a live run, not inferred.

## 1 · Mandate

| | |
|---|---|
| **Deterministic floor** | 12 active rules — chain-hash integrity, per-transaction cap, MCC scope, counterparty allowlist, monthly cumulative cap, payment/cart amount consistency, currency ×2, validity window, injection heuristic |
| **LLM sees** | `natural_language_intent`, `purpose_category`, `cart_agent_reasoning`, `cart_total`, `cart_line_items[]` — **five fields** ([mandate_reasoning.py](agents/mandate_reasoning.py) `structured_view`) |
| **LLM emits** | `{consistent: bool, quoted_evidence: str, explanation: str}` |
| **Becomes** | at most one `Finding`, id hardcoded `{case}-SEM-001` |

**Defects.**

- **The semantic check is blind to the scope it is judging against.** It never sees
  `max_transaction_amount`, `allowed_merchant_categories`, `allowed_counterparties`,
  `geographic_scope`, `human_presence_required`, the merchant record, the payment, or the validity
  window. It is asked "does this cart match what the human asked for" while being shown only the
  prose intent — not the machine-readable scope that expresses the same thing more precisely.
- **It cannot see the floor's own findings.** On CASE-2026-002 the floor had already established
  cap-exceeded, category-out-of-scope and counterparty-not-approved. The semantic check re-derived
  the same conclusion from scratch and emitted a fourth finding that largely restates them. Three
  detectors agreeing is valuable; a fourth detector *not knowing* the other three exist is waste.
- **One boolean for a whole cart.** A cart with twelve line items and one smuggled entry yields
  `consistent: false` plus a single quote. Which item? The prose says. Nothing structured does.
- **Cardinality capped at one.** `finding_id=f"{case_id}-SEM-001"` — two distinct semantic problems
  in one cart can never both be findings.
- **Injection provenance is conflated with scope mismatch.** On case-007 the real defect is *the
  agent's attestation cites merchant text as its authority*. That is a different failure from "the
  cart contains something out of scope," and it is the failure the concept note's red-teaming
  citation is about. It currently rides inside `cart_reasoning_semantic_mismatch`.

## 2 · KYA

| | |
|---|---|
| **Deterministic floor** | 18 active rules — Ed25519 signature, payload hash, algorithm allowlist, delegation-entry signatures, issuer trust/revocation, credential lifecycle, delegation shape → human terminus, capabilities, consent method |
| **LLM sees** | issuer name + id, capabilities, delegation chain (level/type/id/name), purpose category, and the *types* already flagged — **five fields** ([kya_reasoning.py](agents/kya_reasoning.py) `structured_view`) |
| **LLM emits** | `{observations: [{note, cited_field}]}` — never a Finding |
| **Second call** | `narrate_findings()` → prose |

**Defects.**

- **15 of 33 rules are `draft` and inert** — every one blocked on a registry that does not exist:
  operator-firm standing and ownership, agent pre-registration and classification, model-version
  pinning and blocklist, credential rotation history, prior-issuance capability creep. KYA is the
  concept note's headline capability and **45% of its rule vocabulary has never run.** This is the
  single largest business gap in the system, and it is a *data* problem, not a model problem.
- **The ceiling is asked to detect impersonation without being shown who is real.** The prompt asks
  it to spot "an issuer or delegation-chain holder name that closely resembles a real trusted name."
  It is never given the issuer trust registry. It is being asked to compare against a list it cannot
  see.
- **It cannot see dates, signatures, firm, agent id, or model version** — so "anything else
  structurally unusual" is scoped to five fields it has already been told were checked.
- **`narration` is a paid LLM call whose output nothing reads.** `KYAAgent.review()` produces it,
  `KYAReview.narration` stores it, and [pipeline/graph.py](pipeline/graph.py)'s `_kya_node` returns
  only `findings` and `observations`. It never reaches the ledger, the report, or the UI. One
  discarded model call per triage.

## 3 · Log

| | |
|---|---|
| **LLM sees** | purpose category, approved-counterparty count, reporting threshold, candidate structuring clusters, per-counterparty breakdown, velocity stats, amount stats, hourly distribution, transaction count — genuinely good pandas evidence |
| **LLM emits** | three fixed verdicts (`structuring`, `concentration`, `velocity`), each `{anomalous, explanation, cited_evidence}`, plus free `other_observations` |
| **Becomes** | at most 3 Findings, ids `{case}-STR-001` / `-CON-001` / `-VEL-001` |

**Defects.**

- **Three booleans is a coarse output for a pattern detector.** Two independent structuring clusters
  in one history collapse into one finding. Cardinality is hardcoded at `-001` per category.
- **Evidence is prose.** `cited_evidence: "cluster sum 8700.0 vs threshold 3000.0"` is a string. The
  UI cannot link to those transactions; the critic can only regex numbers out of it; the report
  cannot cite them.
- **A fixed three-category taxonomy demotes real findings.** The prompt itself names five more
  patterns worth attention — round-amount clustering, amounts just under an implied boundary,
  steadily escalating size, off-hours clustering, a new counterparty taking large share — and routes
  every one of them to `Observation`, i.e. **unscored and uncitable**. Real signal is structurally
  demoted because no rule exists for it.
- **It cannot test its own hypothesis.** The 24-hour window comes from the ruleset. If a cluster
  looks like structuring at 24h but not at 12h, the model cannot check; only the investigator has
  `recompute_stats`.

## 4 · Drift

| | |
|---|---|
| **LLM sees** | baseline/comparison split, amount z-score, frequency shift, counterparty PSI, MCC PSI, and both mix breakdowns — good evidence, well explained in the prompt |
| **LLM emits** | **one** verdict `{anomalous, explanation, cited_evidence}` + observations |
| **Becomes** | at most one Finding, `{case}-BHV-001`, weight 0.6 |

**Defects.**

- **One boolean for four independent signals.** The corpus's own ground truth originally named three
  drift *types* — `avg_amount_drift`, `frequency_drift`, `counterparty_concentration_shift`.
  Stage 0 "fixed" the mismatch by **collapsing the ground truth to match the code** rather than
  building the rules. The corpus was right and the implementation was thin; the correction went the
  wrong way.
- **It answers "has it drifted" but not "since when."** The supervisory question about a slowly
  decaying agent is *when did this start* — that is what scopes a firm's remediation and a
  regulator's look-back period. No change-point detection exists.
- **Calibration failure, structurally caused.** One rule at 0.6 against a 0.75 `review` floor means
  **the case built to demonstrate drift detection scores `clear` — "No scored findings of
  consequence."** Three dimension rules at ~0.4 each would sum to 1.2 and land correctly. The
  miscalibration is a symptom of the single-boolean design, not a number that needs bumping.
- **Fixed baseline.** First-N-days vs the rest. No seasonality, no officer-selectable window.

## 5 · Orchestrator — dispatch (triage)

| | |
|---|---|
| **LLM sees** | `{firm, purpose_category, transaction_count}` — **three fields** ([pipeline/dispatch.py](pipeline/dispatch.py) `_case_summary`) |
| **LLM emits** | four booleans + reasoning |
| **Then** | `enforce_floor()` forces Mandate+KYA true, Log true if `tx > 0`, Drift true if `tx >= 30` |

**Defect: the decision is theatre.** Mandate and KYA are forced. Log and Drift are decided by the
floor from `transaction_count` — the same integer the model is given. The prompt even says so:
*"your real decision is about Log and Drift."* On the live CASE-2026-007 run the model produced
genuinely good prose about why 7 transactions is too thin for Drift — and the deterministic floor had
already reached the identical conclusion from the identical number. **We are paying for a reasoning
string that decides nothing.** Either give this call a real decision space or delete it.

## 6 · Orchestrator — session (the case room)

Structurally the strongest agent: output schema is a routing decision, invented skills are dropped,
degradation to `reply` is safe. Two real gaps:

- **No conversation history.** Each officer message is an independent run
  (`architecture-v2.md` Stage 8: *"in-thread conversational history deferred"*). The officer cannot
  say "and the other one?" — there is no anaphora, no follow-up, no memory of what was just asked.
  For a product whose central metaphor is *a conversation with a workforce*, this is the biggest
  behavioural gap in the system.
- **No sequencing.** It can dispatch a set in parallel, but cannot express "ask the investigator
  first, then send Mandate what it finds" — the exact two-step the architecture document's own
  worked example (§8, steps 5–7) describes.

## 7 · Critic

Checks that decimals and integers ≥ 100 appearing in a subagent's output also appear in its dispatch
context. Scoped to Log, Drift, and one Mandate finding type.

- **It cannot check anything but numbers** — not quoted strings, transaction ids, dates, or whether
  the claim follows from the evidence at all.
- **It flags legitimate arithmetic.** A model that correctly sums three context amounts produces a
  number absent from the context and is marked unquoted.

## 8 · Synthesizer

Good design, two live defects:

- **The list guard is missing.** `for entry in result.get("correlations", [])` — when the model
  returned `correlations` as a JSON *string* on the live CASE-2026-002 run, it iterated character by
  character: **1,217 warning lines, every correlation silently dropped.** `agents/llm.py` already has
  `parse_observations()` for exactly this failure class; the synthesizer does not use it.
- **No dedup.** [ledger/projection.py](ledger/projection.py) uses the dedup reducers for findings and
  observations but plain `.append()` for correlations. Re-triage doubles them.
- **It sees only summaries** — not `details`, not evidence — so a `causal` claim rests on prose.

## 9 · Drafting

Well contained (structured input only, mechanically checked). But **it writes the wrong document.**
The concept note promises a *supervisory query*: something sent to a firm. What it produces is an
internal summary — no addressee, no specific questions, no response deadline, no regulatory basis,
no ordering by severity, no recommended action.

## 10 · Cross-cutting

- **No confidence anywhere.** Every LLM verdict is a hard boolean. "Almost certainly structuring" and
  "arguably structuring" produce identical findings at identical weight.
- **No structured evidence.** `Finding.details` is a free dict; `cited_evidence` is prose. Nothing
  downstream can resolve a finding to the rows that caused it.
- **Positional ids cap cardinality** at one finding per rule per case.
- **Specialists cannot ask for more.** Only the investigator has tools. A specialist missing one
  field guesses.
- **No memory across submissions.** `get_counterparty_profile` reaches across the ledger — but only
  the investigator can call it. No specialist knows this is the same firm's third submission. For a
  product whose thesis is *continuous* supervision, every case is still judged in isolation.
- **None of it is measured.** No eval harness exists, so no claim in this section can currently be
  quantified.

---

# Part II — What each agent should be

For each: the supervisory function in business terms, then the technical change.

## 11 · Mandate — the authorisation adjudicator

**Business.** Mandate answers the question the AP2 chain exists to make answerable: *was this
specific payment authorised by this specific human, and can we prove it?* It owns three separable
sub-questions — chain integrity (cryptographic), declared-scope compliance (mechanical), and
intent fidelity (semantic). Only the third needs a model, and today it is the weakest of the three
precisely because it is starved of the other two's context.

**Technical.**

1. **Feed it the scope and the floor's verdicts.** The semantic view gains
   `authorization_scope` in full, the merchant record, `human_presence_required`, and
   `already_established_findings` (type + summary, as KYA's ceiling already receives). The prompt
   changes from "judge afresh" to "judge intent fidelity *given* what the mechanical rules already
   established, and say explicitly where you corroborate or diverge from them."
2. **Adjudicate per line item.** Output becomes
   `{line_items: [{sku, within_intent: bool, confidence, rationale, evidence_refs}], cart_level: {...}}`.
   Each out-of-intent item yields its own Finding with `subject = sku`. This removes the `-001` cap
   and makes case-007's smuggled gift card a finding in its own right.
3. **Split injection provenance into its own rule.** New `MND-SEM-03
   attestation_cites_untrusted_source` (weight 0.9): *the agent's own attestation cites
   merchant-authored text as authorisation*. That is the red-teaming failure the concept note is
   built on, and it deserves to be named on the record rather than folded into a scope mismatch.
4. **Promote `MND-CAP-04` (geographic scope)** by adding `Merchant.region` — a one-field schema
   change that unblocks a rule the concept note explicitly promises.

## 12 · KYA — agent due diligence, not signature checking

**Business.** KYA is the regulatory innovation in this submission: the claim that an autonomous payer
needs an identity and an accountability chain the way a customer needs KYC. Today it verifies
cryptography excellently and performs almost no *diligence* — because diligence needs registries, and
the registries don't exist. **Fixing this is mostly a data exercise with no model work at all, and it
is the highest business return in this plan.**

**Technical.**

1. **Build three registries**, same rules-as-data pattern as `registry/rulesets/`:
   - `data/registry/firms.json` — operator firm id, licence status, standing, beneficial ownership
     as-of dates, compliance contact.
   - `data/registry/agents.json` — pre-registered agent ids, declared classification, pinned model
     versions, model-version blocklist.
   - **Credential history is derivable from the ledger already** — every prior `case_submitted` for
     the same `agent_id` gives issuance dates, capabilities, and signer keys over time.
2. **This promotes 11 of the 15 draft rules** — `KYA-OPF-01..04`, `KYA-AGT-01..04`, `KYA-CRD-04`,
   `KYA-CAP-04`, `KYA-SEC-02`. KYA goes from 18 to 29 active rules, and from "the signature checker"
   to "the agent due-diligence function."
3. **Give the ceiling the issuer registry** (names, trust levels, accreditation dates) so
   typosquatting detection becomes possible rather than rhetorical. Add `get_issuer_registry()` and
   `get_credential_history(agent_id)` as KYA-scoped tools.
4. **Retire or wire `narrate_findings`.** Either delete the call, or record it as
   `narration_recorded` and use it as the KYA section of the report. Do not keep paying for output
   nobody reads.

## 13 · Log — pattern instances, not category booleans

**Business.** Log is the AML/conduct surface. A supervisor does not want "concentration: true"; they
want *this counterparty, these seven transactions, this share, this window* — a case they can act on.

**Technical.**

1. **Output a list of detections**, not three booleans:
   `detections: [{category, subject, transaction_ids[], confidence, rationale, evidence_refs}]`.
   N findings, one per detected instance, `subject`-scoped ids.
2. **Promote two patterns from observation to rule** — `LOG-RND-01 round_amount_clustering` and
   `LOG-OFH-01 off_hours_activity`. Both are already named in the prompt, both are supported by the
   evidence the agent already receives (`amount_stats`, `hourly_distribution`), and both are
   currently demoted to unscored. Keep the open-observation tail for genuinely novel patterns.
3. **Give it `recompute_stats`** (bounded, 3 calls) so it can test a cluster at a second window
   before committing. A structuring verdict that survives 12h *and* 24h is a different quality of
   evidence from one that only holds at the ruleset default — and it can say so via `confidence`.

## 14 · Drift — dimensions and onset

**Business.** Drift is the "no single transaction breaks a rule" detector. Its supervisory value is
not the binary; it is **which dimension moved and when**, because that is what scopes a look-back.

**Technical.**

1. **Three rules, restoring the corpus's original ground truth** — `DRIFT-AMT-01` (transaction size),
   `DRIFT-FRQ-01` (frequency), `DRIFT-MIX-01` (counterparty/category mix), ~0.4 each. Each gets its
   own verdict, confidence and evidence. **This fixes the case-006 calibration failure structurally:
   three dimensions firing sum to ~1.2 → `review`, instead of one 0.6 → `clear`.**
2. **Add onset detection.** A simple CUSUM or binary-segmentation change point over the amount and
   frequency series, computed deterministically in `drift_stats.py`, handed to the model as evidence.
   The finding then carries `onset_estimate` — *"the shift begins around 2026-07-11"* — which is the
   answer a supervisor actually needs.
3. **Officer-selectable baseline**, exposed as a directive parameter, so "compare against the first
   month" and "compare against last quarter" are both askable.

## 15 · Orchestrator — give the dispatch a real decision, and the session a memory

**Dispatch.** Today it decides nothing. Give it a decision space that a deterministic floor cannot
compute:

1. **Depth, not just presence.** `{skill, depth: "standard" | "deep"}`. `deep` enables the
   open-ended tail and a larger tool budget. Now the model is trading cost against expected yield —
   a real judgment.
2. **A recorded hypothesis.** `expected_concerns: [{skill, hypothesis}]` written to
   `dispatch_planned`. This turns dispatch reasoning from decoration into a **measurable artifact**:
   the eval harness can later score whether the orchestrator anticipated what was actually found.
3. **Prior-case context.** Feed it the ledger's history for this `firm_id` / `agent_id` — prior
   findings, prior tiers, prior decisions. A firm's third submission should not be triaged like its
   first. This is what makes "continuous supervision" more than a slogan, and the ledger already
   holds everything needed.

**Session.**

4. **Conversation history.** Pass the last N `question_asked` / `orchestrator_replied` /
   `investigation_completed` events into `record_summary()`. Cheap, and it is the difference between
   a chat and a form.
5. **Sequenced plans.** Allow `plan: [{step, targets, instruction}]` executed in order, so
   investigate-then-adjudicate works as one officer request.

## 16 · Critic — check evidence, not digits

Extend from number-matching to **reference resolution**: every `evidence_refs` entry must resolve
against the dispatched context — the transaction id exists in the rows sent, the field path exists in
the object sent, the statistic name exists in the computed block. That is a real grounding check and
it becomes possible the moment Finding v2 lands. Keep numeric checking, but allow values derivable by
sum/mean/count over the context's own numbers, which removes the current false-positive class.

## 17 · Synthesizer and Drafting

**Synthesizer** — fix the list guard via a shared helper (four lines); dedup by
`(relationship, frozenset(finding_ids))` in the projection; feed it `details` and `evidence_refs` so
`causal` rests on evidence.

**Drafting** — add a second output mode, `supervisory_query`, alongside the internal summary:
addressee, per-finding specific questions, response deadline, regulatory basis, severity-ordered.
Grounding extends naturally — *every question must cite a finding*. This is the document the concept
note actually promises, and it is a strong closing beat in a demo: the officer signs something that
goes to a firm, not a memo that goes in a drawer.

---

# Part III — Cross-cutting foundations

These are prerequisites. Almost every improvement in Part II depends on one of them.

## 18 · Finding v2

```python
class EvidenceRef(BaseModel):
    kind: Literal["transaction", "line_item", "credential_field", "statistic", "rule"]
    ref: str        # "TXN-2026-0142" | "cart.line_items[0]" | "counterparty_mix_psi"
    value: Any      # the value as the agent saw it — what the critic checks

class Finding(BaseModel):
    finding_id: str          # {case}-{AGENT}-{RULE}-{nnn}, from a real counter
    case_id: str
    agent: FindingAgent
    type: str
    rule_id: str | None
    severity_weight: float | None
    confidence: Literal["certain", "probable", "possible"] = "certain"
    subject: str | None      # the transaction / sku / counterparty this is about
    summary: str
    evidence_refs: list[EvidenceRef] = []
    details: dict[str, Any] = {}
```

- **Deterministic rules are always `certain`** — enforced in code, not convention. Only model-judged
  findings may be `probable` or `possible`.
- **Scoring multiplies by a confidence factor from `registry/scoring.json`** (e.g. 1.0 / 0.7 / 0.4).
  Rules-as-data, sandbox-able, and it keeps `score_findings()` a pure function.
- **`subject` + a real counter** removes every `-001` cardinality cap at once.
- Backward compatible: both new fields default, so nothing in the ledger's history breaks.

## 19 · The evidence-request protocol

Extend `AGENT_TOOLS` — the permission map is already enforced at both bind and execute, so this
costs no new machinery:

| Agent | Tools | Budget |
|---|---|---|
| mandate | `get_rule`, `get_transaction` | 3 |
| kya | `get_issuer_registry`, `get_credential_history`, `get_rule` | 3 |
| log | `recompute_stats`, `get_rule` | 3 |
| drift | `recompute_stats`, `get_counterparty_profile` | 3 |
| investigator | unchanged | 8 |

The evidence floor is unchanged: tools **add**, exactly as the orchestrator's extra blocks do. Every
call is recorded as a `ToolCallRecord` on the dispatch, so "what did this agent look at" stays
answerable. No tool returns `line_items[].description`; the injection surface stays closed.

## 20 · Scoring: compounding, not just addition

Two known miscalibrations (case-006 drift → `clear`, case-003 broken chain → `review`) share a cause:
score is a flat sum with no notion of *compounding*. Add to `scoring.json`:

- **Confidence weighting** (§18).
- **A compounding factor** when ≥2 independent agents fire — precisely the situation the synthesizer
  already detects and the concept note calls out as most serious. Correlated findings from
  independent detectors is the strongest evidence the system can produce and currently scores the
  same as two unrelated ones.
- **A floor per rule class** — a cryptographic chain break is categorically an `escalate`, whatever
  else is or is not present. Encode it as data, not as a bumped weight.

## 21 · The eval harness comes first

Nothing above is currently measurable. Build the harness **before** the improvements so every change
is scored, not asserted. It is now a ledger query:

- Per-agent precision/recall against `data/corpus_manifest.json`.
- False-positive rate on case-001, the clean control.
- **A calibration report**: does the computed tier match what the label implies? This is what would
  have surfaced case-006 automatically.
- **Confidence calibration**: of findings marked `probable`, what fraction match ground truth?
- Adversarial: the hostile-prompt suite already exists; add "does a `deep` dispatch find more than a
  `standard` one" as a regression on §15.1.

One caveat to state in the harness's own README: several `expected_findings` in the manifest have
been revised to match implementation behaviour (case-004, case-005, case-006, case-007). The numbers
it produces measure agreement with a ground truth the implementation helped write. That is worth one
honest sentence rather than a discovered asterisk.

---

# Part IV — The plan

Strict dependency order. Each stage lands green before the next.

## Stage 0 — Fix-first *(~0.5d)*

Small, known, blocking nothing but embarrassing if they ship.

- [ ] Synthesizer list guard — reuse the `parse_observations` pattern; a non-list `correlations`
      must log once and return `[]`, not iterate a string (observed: 1,217 log lines, all
      correlations dropped).
- [ ] Correlation dedup in `project_case()` by `(relationship, frozenset(finding_ids))`.
- [ ] `run_failed` event + `try/except` around each run body; emit AG-UI `RUN_ERROR` so a mid-run
      failure surfaces to the officer instead of the stream silently ending.
- [ ] Delete `data/uploads.py` and its 10 tests (dead since uploads went to the ledger), or route
      uploads back through it. Fix the `"1 events on record"` summary fallback.
- [ ] Investigator missing from the Overview roster, sidebar, and the "four specialist review
      agents" copy.
- [ ] Pin LangGraph or register the five msgpack types before the checkpointer deprecation lands.

## Stage 1 — Eval harness *(~1d)* — **the forcing function**

- [ ] Per-agent P/R, FP rate, calibration report, confidence calibration (§21).
- [ ] `make eval` producing a single scorecard, committed as the baseline every later stage is
      measured against.

## Stage 2 — Finding v2 + scoring *(~1d)*

- [ ] `EvidenceRef`, `confidence`, `subject`, real id counters (§18).
- [ ] Confidence weighting + compounding + per-class floors in `scoring.json` (§20).
- [ ] Re-run the harness: case-006 and case-003 calibration must move without any weight being
      hand-tuned.

## Stage 3 — KYA registries *(~1d)* — **highest business return**

- [ ] `firms.json`, `agents.json`; credential history from the ledger.
- [ ] Promote 11 draft rules → 29 active. Checkers for each.
- [ ] Issuer registry into the ceiling's view; KYA tools.
- [ ] Retire or wire `narration`.

## Stage 4 — Per-instance specialist outputs *(~1.5d)*

- [ ] Mandate: per-line-item adjudication, scope + floor findings in view, `MND-SEM-03`,
      `Merchant.region` → `MND-CAP-04`.
- [ ] Log: `detections[]`, `LOG-RND-01`, `LOG-OFH-01`.
- [ ] Drift: three dimension rules, onset detection, selectable baseline.

## Stage 5 — Evidence-request tools + Critic v2 *(~1d)*

- [ ] Specialist tool sets and budgets (§19); `ToolCallRecord` on every dispatch.
- [ ] Critic checks `evidence_refs` resolution; derived-number allowance (§16).

## Stage 6 — Orchestrator *(~1d)*

- [ ] Dispatch: depth, recorded hypothesis, prior-case context from the ledger.
- [ ] Session: conversation history, sequenced plans.

## Stage 7 — Supervisory query *(~0.5d)*

- [ ] Second drafting mode with addressee, questions, deadline, regulatory basis; grounding extended
      to questions.

> **Cut line after Stage 4.** Stages 0–4 deliver the substance: measurable agents, calibrated
> scoring, a real KYA, and specialists that produce actionable per-instance findings. Stages 5–7 are
> upgrade. If build time is short, cut from the bottom — and cut Stage 7 before Stage 6.

## 22 · What this does not change

The architecture. Orchestrator-worker, the two output tiers, the evidence floor, the ledger, the
human gate, deterministic ingestion, guarantees-in-code-not-prompts — all unchanged. Every proposal
here either adds a field, adds a registry, adds a rule, or widens a view. **No guarantee in
`architecture-v2.md` §5 is weakened by anything in this document**, and each stage should be checked
against that table before it lands.

## 23 · Considered and rejected

- **Letting specialists write their own rules.** Ends rules-as-data. The whole registry premise is
  that a human promotes a rule; an agent that mints one at runtime makes the ruleset unreviewable.
- **An LLM critic.** A second model judging the first hallucinates alongside it. Reference resolution
  is mechanical and therefore trustworthy.
- **Merging Log and Drift.** They answer different questions over different windows — Log is
  within-history pattern, Drift is across-window change. One agent would blur both prompts.
- **Raising `DRIFT-BHV-01` from 0.6 to 0.8 to fix case-006.** Treats the symptom. The design defect
  is one boolean for four signals; splitting the rule fixes the score as a side effect and improves
  the finding at the same time.
- **Giving specialists unrestricted tool access.** The bounded, domain-scoped map is what makes
  "dispatcher-permissioned, not prompt-instructed" true. An open tool surface would make it a slogan
  again.
