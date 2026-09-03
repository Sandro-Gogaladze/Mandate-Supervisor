# Mandate Supervisor — the whole thing

Self-contained. Read this and you know what the product is, what is built, what
is not, what was decided and why, and what to build next.

**Supersedes `architecture-v3.md`**, which predates the authorisation reframe
and still describes a case-based system. Where the two disagree, this is right.

Depth lives in: `coverage-model.md` (the 73 failures + the data contract),
`kya-ruleset.md` (the 57 rules), `data-and-agents.md` (rule→agent map),
`synthetic-data-spec.md` (corpus design), `migration-plan.md` (build order).

---

# 1 · What the product is

A regulator-side tool that decides **whether one AI payment agent should be
authorised to operate**, on evidence of what it actually did.

An operator that wants to run an agent submits a **dossier**: the agent's
identity, the mandate it operated under, its controls, and the runs it executed.
A supervisor reviews it and reaches one of four dispositions. Then the same for
the next agent, at the next company.

**The unit of regulatory decision is one agent.** That is why the corpus is one
operator, one agent, many runs — it is one authorisation dossier, not a sample
of a market.

## 1.1 · Why this is a real regime, not an invented one

| Precedent | What it requires |
|---|---|
| **MiFID II RTS 6** | Investment firms must test algorithms in a non-live environment before deployment, self-certify, and retain records the regulator can demand. **The closest analogue: an algorithm that moves money, tested before it is allowed to.** |
| **EMV / PCI PTS** | Defined test suites, run by the vendor, results submitted for approval. Payments already certifies by testing |
| **EU AI Act** | Conformity assessment before market placement |
| **SR 11-7 / ECB TRIM** | Supervisors review the *validation*, not just the filed policy |

The pitch is not "we invented agent approval." It is: **payments already approves
things by testing them, and nobody has said what the test looks like for an AI
payment agent.**

## 1.2 · Who submits, and why it has to be them

Agent operators are not regulated entities anywhere. The obligation attaches to
someone inside the perimeter.

```
NBG ──authorises the agent──▶ Institution (bank/PSP)   ← regulated. SUBMITS.
                                    │ sponsors
                                    ▼
                              Operator (not regulated)
                                    └── Agent  ← the subject of the decision
```

**Where the institution gets data it does not natively hold:** its own API. The
agentic-checkout product requires the run record as a condition of processing.
A commercial condition, already how PSP onboarding works. The data exists
because the product demands it.

## 1.3 · AP2, and why each run is its own chain

AP2 has three mandates and two flows:

| Flow | Intent Mandate is | Who signs the Cart |
|---|---|---|
| **Human-present** (e-commerce shopping) | created *for this shopping task* | the shopper, on exact items and price |
| Human-not-present (standing delegation) | signed in advance with conditions | nobody at purchase time |

**We model human-present.** The shopper says *"white running shoes under $120"*;
that becomes the Intent Mandate for that task. So the mandate lives **on the
run**, and every run is a complete self-contained chain.

This is load-bearing, not cosmetic. Checking a cart against a three-month
envelope is nearly vacuous — almost anything passes. Checking it against *"vitamin
c serum, around $50"* is not. **F49 only becomes a real test in this shape.**

---

# 2 · The data

## 2.1 · Submitted vs regulator-held

The dividing line: **anything an operator could shade in its own favour lives
regulator-side.**

```
SUBMITTED (the dossier directory)        HELD BY THE REGULATOR (data/registry/)
─────────────────────────────────        ──────────────────────────────────────
dossier.json    what runs share          institutions.json  who may submit
runs/*.json     one AP2 chain each       operators.json     who may operate
transactions.json  the ledger            agents.json        WHICH AGENTS EXIST ←
ground_truth.json  eval only             merchants.json     who was really paid
                                         tools.json         authorised servers
                                         model_blocklist.json  barred models
                                         issuers.json       credential issuers
                                         keystore.json      public keys
```

The operator *declares* which model it used (`self_attested_by`); whether that
model is **blocked**, whether that prompt release was **approved**, and who
**owns** the merchant are facts the regulator keeps. `agents.json` does not exist
in any jurisdiction — **it is the policy proposal.**

## 2.2 · Shapes

```jsonc
// dossier.json — everything the runs share
{
  "dossier_id", "submission_purpose",          // authorisation | renewal | ...
  "institution_id", "operator_id", "agent_id",
  "submission_context": {
    "submitted_at", "executed_from", "executed_to", "environment",
    "runs_executed_total", "runs_submitted",   // the gap is S2
    "deployment_target": { "model_version", "prompt_release_ref", "tool_servers" }
  },                                           // vs the runs = S3
  "kya_credential": { ..., "revocation_checked_at",
    "delegation_chain": [{ "level", "holder_id", "holder_type", "name",
                           "granted_capabilities", "constraints", "signature" }] },
  "credential_history": [ ... ],               // F20-F23 need the series
  "agent_card": { "url", "card_hash", "declared_capabilities",
                  "declared_tool_servers", "signature" },
  "controls": { "operator_declared": [...], "institution_declared": [...] },
  "change_log": [{ "at", "kind", "ref", "detail" }],   // what Drift's onset lands on
  "run_index": [{ "run_id", "file", "sha256" }]        // an ATTESTATION
}

// runs/RUN-*.json — one complete AP2 chain
{
  "run_id", "dossier_id", "environment", "started_at", "ended_at", "trigger",
  "user_prompt",                               // UNTRUSTED. the injection surface
  "intent_mandate": { ..., "authorization_scope": { ..., "usage" } },
  "construction_context": {
    "model": { "declared_version", "observed_version", "provider", "self_attested_by" },
    "policy_version": { "prompt_hash", "release_ref" },
    "tool_calls": [{ "sequence", "tool_name", "server_id", "tool_schema_hash",
                     "arguments", "result_digest", "result_excerpt" }],
    "selection_context": { "query", "selected_sku", "alternatives_considered" }  // max 5
  },
  "consent_ceremony": { "occurred", "ceremony_scope", "rendered_values", ... },
  "cart": { "merchant": { ..., "region", "sub_merchant" }, "line_items", ... },
  "payment": { "payment_method", "payee", ... },   // payee = where money WENT
  "controls_evaluated": [{ "control_id", "outcome", "override" }],
  "outcome"                                    // completed|abandoned|blocked|failed
}
```

## 2.3 · Design points that are easy to get wrong

- **`run_index` is an attestation, not a table of contents.** It carries a
  content digest per run, so a run edited, deleted or slipped in after filing is
  detectable — and **S2 becomes structural** rather than resting on a number the
  operator declares about itself. The loader scans the directory *and* the index,
  because two views of "which runs are in this dossier" must not silently
  disagree.
- **`transaction_history` is wider than the runs.** ~45 in-window with `run_ref`,
  ~55 trailing without. Drift needs 30+ for a baseline/comparison split; runs
  alone would leave a third of the rulebook `absent`. A transaction with no
  `run_ref` **inside** the window is itself a finding.
- **`result_digest` is correlation, NOT detection.** A hash proves bytes arrived
  intact; it cannot reveal an injection. `result_excerpt` (capped ~2000 chars)
  is what closes the retrieved-material channel of F32. Once one firm's excerpt
  has been read, the same digest elsewhere identifies the same payload for free —
  that is F69.
- **`granted_capabilities` per delegation level.** Without it a chain is a list
  of names and **F11 is undetectable** — there is nothing to compare a child
  against its parent.
- **`usage`** (single_use / recurring). Without it F50 has no baseline to violate.
- **`ground_truth.json` is a separate file** so withholding it from the pipeline
  is *not opening a file*, never a `model_copy` someone forgets.

## 2.4 · The corpus

| | |
|---|---|
| `DOSSIER-KST-2026-001` | Kestrel Commerce shopping agent · **50 runs** · 102 transactions · 21 planted · 37 clean |
| `DOSSIER-HAL-2026-001` | Halcyon Retail Agents · **20 runs** · 52 transactions · 5 planted · 17 clean |

Both hand-authored (source in `data/authored/`), signed with real Ed25519,
211 signatures verifying, hash chains intact.

Halcyon exists for what is only visible **across** dossiers. Its merchant set
overlaps Kestrel's — which is ordinary, and must stay ordinary, or a cross-firm
signal means nothing.

**Realism targets** (they are not decoration — every rule keyed on the *shape*
of data needs a believable background to detect an anomaly against): Benford on
leading digits, 6–10% round numbers, 8–15% off-hours, 94–98% settled with
declines **clustered**, top counterparty 35–55%.

---

# 3 · The rulebooks

**Rules are data.** Versioned JSON in `registry/rulesets/`, active/draft/retired,
never hardcoded. A **draft** rule is not unfinished — it is one whose *evidence
the submission cannot yet carry*. Promoting it is a data question.

| Book | Rules | State |
|---|---|---|
| `kya.json` v2026.7 | 42 | **37 active**, 5 draft, 2 judged |
| `ctl.json` v2026.1 | 15 | 15 active |
| `mandate.json` v2026.2 | 13 | 12 active |
| `log.json` v2026.2 | 3 | 3 active |
| `drift.json` | 1 | 1 active |
| **`consent.json`** | — | **not written** |
| **`injection.json`** | — | **not written** |
| **`counterparty.json`** | — | **not written** |
| **`provenance.json`** | — | **not written** (its 3 rules live in kya.json today) |

**Nine rulebooks, one per agent** — decided, so the sandbox can tune each domain
independently and one agent maps to one book.

## 3.1 · KYA, the eight families

`IDN` identity is cryptographically sound (5) · `ISS` issuer accredited and
current (5) · `ACC` authority traces to an accountable human (7) · `OPF` operator
fit to run it (4) · `REG` agent declared and classified (5) · `TEC` technical
substrate declared (6) · `CAP` capability proportionality (5) · `LIF` credential
lifecycle (5).

**Ownership is assigned by EVIDENCE, not by topic.** A rule belongs to the agent
whose evidence block already contains what it needs. `TEC` splits across two
agents for this reason: `TEC-01/03/04` from the agent registry (KYA),
`TEC-02/05/06` from `construction_context` (Provenance). Splitting on evidence
also removed a duplication where F37 would have been asserted twice.

**Still draft, and why:** `IDN-04`/`IDN-05` need cross-case ledger history;
`REG-03`, `CAP-03`, `CAP-04` are judgements the sandbox must tune.

## 3.2 · Three rules the corpus proved wrong

Kept here because they are the kind of error that recurs.

- **`ACC-02`** required the chain to terminate in the Intent's signer. True for
  corporate delegation; structurally false for consumer shopping, where the
  shopper signs their own Intent and the chain ends at the *operator's* officer.
  Unscoped it would breach **every consumer purchase ever made.** Now scoped by
  `principal_type`.
- **`OPF-01`** as "must hold a licence" fails every non-bank operator by
  construction — most of this market. Now *licence **or** live sponsorship*.
- **`LOG-STR-01`** threshold sat at $3,000 against an agent whose largest
  transaction is $867. **A dial set beyond an agent's operating range is not a
  lenient rule, it is a rule switched off** — and the eval reads its silence as
  clean behaviour. Now resolved per agent classification.

---

# 4 · The eleven agents

Every one: **a deterministic floor needing no model, plus at most one contained
LLM call.** Determinism establishes facts; agents establish meaning.

| | Agent | Question it owns | Failures | Deterministic floor | The LLM call |
|---|---|---|---|---|---|
| A1 | **Mandate** | Within what the human signed? | F39–F50 | 12 `MND-*`: caps, scope, chain links, currency, window, usage | **Per-line-item intent fidelity** — does this cart answer *this shopper's sentence*? The only source of F49 |
| A2 | **KYA** | Authority traceable to a human? | F1–F23 | 37 `KYA-*` + credential-series pass | Near-name issuer resemblance; whether observed activity fits the declared classification (`REG-03`) |
| B1 | **Provenance** | Inputs anyone should trust? | F33, F36, F37 | `TEC-02/05/06` | Reconcile four sources that should agree: agent card · credential · registry · observed tool calls |
| B2 | **Injection** | Manipulated by what it read — **which channel**? | F32, F35 | regex triage over 4 text channels + `tool_schema_hash` | Did the agent **act** on it, and through which channel. Output carries `channel` because the supervisory question is where sanitisation leaks |
| C1 | **Counterparty** | Who received this money? | F51–F58 | payee vs merchant registry, sub-merchant, concentration stats | Is this payee what it appears to be — name/account mismatch, fronting |
| C2 | **Consent & Harm** | Was the human there; is the consumer worse off? | F24–F31, F38 | `rendered_values` vs cart, ceremony scope, supersession | **Value-for-money against `selection_context`** — the detectable signature of merchant-bias tuning |
| D1 | **Log** | What does this history reveal? | F59–F64, F66 | pandas: structuring, velocity, roundness, off-hours, concentration | Narrate already-computed numbers; judge whether a cluster is benign |
| D2 | **Drift** | What changed, **and when did it start**? | F65 | baseline/comparison split, change-point detection | Which `change_log` event sits at the onset boundary |
| E1 | **Control Assurance** | Did the firm's own controls work? | F70–F73 | 15 `CTL-*` | Classify posture: **absent / failed / bypassed / ineffective**. This is what makes it a supervision tool rather than a detection tool |
| E2 | **Systemic** | What is true across the portfolio? | F57, F67, F69 | shared-payee, monoculture, shared-digest sweeps | Is this concentration meaningful or ordinary popularity |
| E3 | **Red Team** | Does it hold up when pushed? | on demand | generates cases from the mandate's own parameters | — |

Support agents unchanged: Orchestrator · Investigator · Critic · Synthesizer ·
Drafting · Grounding.

**Two ordering constraints that are not negotiable:**

1. **Control Assurance runs AFTER the peer fan-out**, not inside it. `CTL-EFF-01`
   asks whether a control that *should* have triggered did — which means knowing
   the risk materialised, which is somebody else's finding. There is a test
   asserting it stays silent when given no peer findings.
2. **Agents never talk to each other.** A specialist that needs more evidence
   uses its tools; a question needing a different specialist is the officer's
   next round. Iteration replaces recursion.

---

# 5 · The pipeline

```
INTAKE — code only, zero model calls
  verify every signature and chain · verify the run index against file digests
  resolve all six registries · compute shared statistics ONCE
  note which submission blocks are present
  ─────────────────────────────────────────────► the EVIDENCE PACK
  No rules evaluated here. Rules belong to agents.
        │
        ▼
ORCHESTRATOR — 1 call
  round 1: dispatch every agent whose evidence block is present.
           Nothing to decide — a first pass is comprehensive by design;
           the deterministic floor is a backstop, not the driver.
  round 2+: judge the officer's question against every fact round 1 produced,
           NARROW THE CONTEXT to the runs it concerns, dispatch what is relevant
        │
        ├──► mandate    ├──► counterparty  ├──► log
        ├──► kya        ├──► consent       ├──► drift
        ├──► provenance ├──► injection     └──► hunter
        │
        │  EACH AGENT, ONE PASS:  1 check() its rules → FACTS
        │                         2 reason over its facts
        │                         3 hunt in its own domain
        │                         → assessments + observations
        ▼
  control assurance (consumes the peers' findings)
        ▼
SYNTHESIS — sequential
  critic (deterministic) → synthesizer → score
        ▼
OFFICER reads the case room ──► asks ──► ROUND 2 ──┐
        └──────────► REPORT ⇄ GROUNDING ──► HUMAN GATE ◄┘
```

## 5.1 · Review scope — DECIDED

**Round 1 is whole-dossier per agent.** Each specialist gets one LLM call over
the entire dossier and produces **one coherent account of that agent's behaviour
across all runs, citing specific runs**.

**Round 2 is narrowed by the orchestrator.** When the officer wants depth on one
run, the orchestrator composes a context containing *only* that run and
dispatches only the relevant specialists.

Why this shape:

- **The LLM reasons over FACTS, not raw runs.** The deterministic floor runs
  per run first and produces a compact fact table. So "the whole dossier" is 50
  runs' worth of *facts*, not 50 JSON files — which is what makes one call
  viable and directly answers the context-loss objection.
- **Cross-run failures stay possible.** F55, F59–F66, F65 are properties of the
  *set*. Asked per run they produce the same answer 50 times or 50 partial ones.
- **~11 calls per review**, not ~550.
- **Every assessment must cite its runs.** Enforced in the schema — an assessment
  about run-level behaviour that names no run is rejected. Without that, a
  whole-dossier call produces claims nobody can check.

---

# 6 · Scoring and dispositions — DECIDED

## 6.1 · The defect this fixes

Today: sum the severity weights, compare to thresholds. That answers *"is this
case risky."* It cannot answer *"should this agent be authorised":*

```
Dossier A   50 runs · 1 cap breach (0.9)  →  0.9
Dossier B    3 runs · 1 cap breach (0.9)  →  0.9      ← identical
```

A demonstrated 49 correct runs, B demonstrated 2. **A sum-of-weights function
only counts what went wrong and never counts what went right**, so it is
structurally incapable of telling them apart.

## 6.2 · Rule-gated refusals plus weighed judgement

**Hard gates — refuse regardless of score.** A short, explicit, versioned list:

| | |
|---|---|
| `F73` / `CTL-DIS-04` | a blocking control triggered, nobody overrode it, the payment settled anyway |
| `F32` where the agent **acted** | it obeyed an instruction hidden in content it read |
| `F8` | a delegation link is forged |
| `F50` on a single-use mandate | the same authorisation drawn on twice |

These are unarguable. Attaching a number to them would only invite arguing.

**Everything else is weighed:** total severity on one side; **clean-run count and
how much of the mandate's risk surface was exercised** on the other. Forty clean
runs are evidence *for* authorisation and must count as such.

**Four dispositions** (SAFR alignment, and the fourth is the one that was
missing):

| | When |
|---|---|
| **authorise** | no gate tripped, weighed picture clean, coverage adequate |
| **monitor** | neither clean nor actionable — closed to review but under standing watch, next submission auto-triaged against this one. **The right home for F55's concentration and F67's monoculture, neither of which is a refusal.** Adds `case_watched` to the ledger |
| **refuse** | a hard gate, or a weighed picture beyond tolerance |
| **incomplete submission** | S1–S4. Not a verdict on the agent — a verdict on the evidence, and it must not be confused with `refuse` |

## 6.3 · The submission-integrity vocabulary

Not agent failures — the **operator curating the evidence**. No F-numbers.

| | | Cost to check |
|---|---|---|
| **S1** | Unrepresentative submission — runs cluster in a corner of the mandate | measure + judge |
| **S2** | Partial — `runs_submitted` < `runs_executed_total` | one comparison |
| **S3** | Deployment divergence — certified one config, ships another | three fields, **cheapest and most important** |
| **S4** | Stale evidence — runs predate the current release | two dates |

---

# 7 · The console

## 7.1 · Why the conversation is unreadable today

`StepFeed.tsx` has a `formatArgs()` that `JSON.stringify`s whatever it receives
into a `<pre>`; `Conversation.tsx` does the same in three more places. **There is
no renderer per event type** — raw JSON is not a fallback, it is the default
path. **Restyling cannot fix this.**

## 7.2 · What replaces it

- **`AgentTurn`** — one collapsible block per agent in dispatch order, live
  status. Reads like a transcript of eleven specialists working.
- **A renderer per payload type** — `FactCard`, `AssessmentCard`, `AbsentNotice`,
  `ToolCallRow`, `ControlPostureBadge`, `CorrelationLink`,
  `PortfolioFindingCard` — in a registry keyed by type, with a **loud** fallback
  naming any unrendered type, so gaps show in review rather than silently.
- **Evidence cited, never dumped.** `RUN-2026-0811-0043 · cart_total $708.00 ·
  KST-CTL-001`, expanding to the fact and linking to the run.
- **Streaming that means something** — tokens for reasoning, events for facts as
  they land. An agent with four facts still thinking should look like that.
- **`absent` is first-class.** *"Consent ran 7 rules, 5 satisfied, 2 absent — no
  `rendered_values` in this submission"* is a supervisory fact and today renders
  as nothing.

## 7.3 · Navigation

**Run list** (sortable by verdict, **clean ones visibly the majority** — they are
the substance of an authorisation) · **run detail** (one AP2 chain end to end) ·
**portfolio view** · **the disposition** with its factor breakdown at the human
gate.

## 7.4 · The flowchart

`SupervisionMap` and `PipelineGraph` regenerate from `graph.get_graph()` — never
hand-maintained. Ten parallel peers plus a sequenced Control Assurance will not
fit the current layout. Needs **live node state** (idle · dispatched · running ·
returned-clean · returned-findings) and one click from a node to that agent's turn.

## 7.5 · Submission intake

A dossier is a directory, not a file. `POST /dossiers` takes a zip or streams
runs after `dossier.json`, and **verifies at the door**: every index digest
matches, no run missing, none unlisted, every signature verifies. A submission
failing any of these is **rejected with the reason** — the index is an
attestation, and accepting one that contradicts itself destroys the point.

---

# 8 · What is built, and what is not

## Built and passing (117 tests)

Dossier schema and loader · both dossiers, signed and independently verified ·
six registries · five rulebooks (68 active rules) · KYA 37/42 · all 15 CTL rules
with checkers · Provenance checkers · Systemic sweep with F57/F67/F69 firing ·
the ledger · scoring primitives · the independent verifier.

## Not built

The pipeline still consumes `CaseBundle` and dispatches four specialists.
**27 files** reference the old shape. `Facts`/`Assessments` are designed and used
nowhere. Seven of eleven agents do not exist. Four rulebooks unwritten. `eval/`
does not exist. The console is unchanged.

**22 test modules are parked** in `tests/conftest.py` under `collect_ignore` —
listed by name, not glob, so the missing coverage stays visible and counted.
They cover agents, dispatch, all three graphs, tools and uploads. Their *fixture*
died with the case corpus, not their subject. **Until Phase 2 lands, none of that
has test coverage.**

## Known weaknesses — do not discover these later

- **The corpus exercises 17 of 73 failures (23%).** 68 active rules, 17 distinct
  planted failures — most rules have never fired on anything. They are
  asserted-correct, not demonstrated-correct.
- **`eval/` does not exist.** There is no precision/recall number for anything.
  Build it before the console: a good console makes a plausible-looking pipeline
  extremely convincing.
- **Checkers return `None` for both *satisfied* and *absent*.** Already wrong;
  becomes unfixable once seven more agents are built on the same contract.
- **F49 and F38 are judged, not computable.** No deterministic check can
  reproduce them, and the verifier reports them separately rather than pretending.

---

# 9 · Decisions already made — do not relitigate

| Decision | Why |
|---|---|
| **Authorisation, not transaction monitoring** | The regulatory act is a decision about one agent on submitted evidence |
| **AP2 human-present; mandate lives on the run** | It is what makes F49 a real test |
| **Runs are separate files under one dossier** | They are produced independently; the index attests to them |
| **Round 1 whole-dossier per agent, run-cited; round 2 narrowed** | LLM reasons over facts not raw runs; cross-run failures stay possible; ~11 calls |
| **Rule-gated refusals + weighed judgement, four dispositions** | A sum cannot count clean runs as evidence |
| **Nine rulebooks, one per agent** | One agent, one book; the sandbox tunes each domain independently |
| **Controls split operator/institution** | Different accountable party, different report |
| **Rule ownership by evidence, not topic** | Resolves boundaries mechanically; removed the F37 duplication |
| **No regulator-set test battery (yet)** | MiFID II RTS 6 works the same way. Representativeness becomes a judgement (S1), not a procedure |
| **Legacy case corpus deleted** | One shape, no adapter |
| **`verify_dossier.py` must not import from `agents/`** | Ground truth the implementation helped write is a mirror, not an eval |

---

# 10 · What to build next

`migration-plan.md` has eleven phases with gates. The order that matters:

1. **Facts** — before any new agent, or you write eleven agents twice.
2. **Ingestion + state** — `Dossier` through the graph; unparks the 22 modules.
3. **Migrate the four existing agents.**
4. **Eval** — moved earlier than the plan says, because nothing above can be
   trusted without it.
5. Then the seven new agents, orchestrator, scoring, ledger, API, console.

**Shortest path to a demo:** 1 → 2 → 3 → eval → orchestrator (4 agents) →
scoring → intake → conversation renderer + run list + run detail.
