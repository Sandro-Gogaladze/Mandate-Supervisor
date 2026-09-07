# The supervision model

Who submits what, what gets checked, and what the decision means. This is the
regulatory substance of the system; [architecture.md](architecture.md) covers
how it runs.

---

## 1 · The regulatory act

The unit of supervision is **one agent**, not one firm and not one transaction.

That choice matters. A firm-level assessment averages away exactly the signal
that counts — two agents at the same institution can behave completely
differently. A transaction-level alert answers "was this payment anomalous?",
which is fraud monitoring and already exists. The question here is
**"was this agent's decision within what it was authorised to do?"**, and the
output is an authorisation decision about the agent.

### Who is obliged

```
NBG ──authorises the agent──▶ Institution (bank / PSP)   ← regulated. SUBMITS.
                                    │ sponsors
                                    ▼
                              Operator (not regulated)
                                    └── Agent  ← the subject of the decision
```

Agent operators are not regulated entities in any jurisdiction, so an obligation
cannot attach to them. It attaches to the bank or PSP that sponsors the agent.

The obvious objection — *how does an institution obtain run-level data it does
not natively hold?* — has a commercial answer rather than a regulatory wish: it
requires the run record as a **condition of the agentic-checkout product**, the
same way PSP onboarding conditions already work. The data exists because the
product demands it.

### The four dispositions

Computed by `pipeline/authorisation.py` from `registry/authorisation.json`.

| Disposition | When |
|---|---|
| `refuse` | A hard gate tripped, **or** weighed risk per run ≥ `refusal_weight_per_run` |
| `incomplete-submission` | Adequacy failed — too few runs, evidence too old, or rule coverage below threshold |
| `monitor` | Weighed risk above the monitor threshold, or unresolved concerns exist |
| `authorise` | None of the above |

Order matters: **hard gates precede adequacy, and adequacy precedes judgement.**
A refusal for acting on injected content is not something a pile of clean runs
should be able to outvote, and an inadequate submission must not be quietly
authorised because nothing bad was found in evidence that was never there.

Four rules are gates, each naming the failure it represents:

| Rule | Failure |
|---|---|
| `INJ-ACT-01` | F32 — the agent acted on injected content |
| `KYA-ACC-03` | F8 — a required authority signature is invalid |
| `MND-USE-01` | F50 — a single-use mandate was used again |
| `CTL-DIS-04` | F73 — a blocking control rejected the action but payment proceeded |

Clean runs reduce **non-gated** risk only. That asymmetry is deliberate: volume
of good behaviour is evidence about judgement, never about integrity.

**The system recommends; the human decides.** A named officer signs one of the
four, and the decision is bound by hash to the exact recommendation reviewed —
a signature on a specific set of findings, not on a case that has since moved.

> The policy is versioned as a prototype (`2026.09.prototype.1`), which means
> calibrating it against a real supervised population is a **data change, not a
> code change** — a new version of one JSON file, swept against the corpus and
> promoted like any other policy edit.

`AuthorisationRecommendation` carries a `limitations` list alongside the
decision, so whatever a given policy version cannot yet establish travels with
the recommendation instead of being lost between the system and the officer.

The recommendation also carries `policy_digest`, `recommendation_digest` and
`evidence_digest`, plus `rule_coverage`, `rules_exercised`, `active_rules`,
`clean_runs` and `unresolved_assessments` — so a decision can be re-derived, and
a signature binds to the exact evidence and policy version behind it.

---

Every filed dossier becomes one case on the record, reviewable once its checks
have passed:

![The case queue](images/02-cases.png)

## 2 · What is submitted

A **dossier** — one agent, one review period, in one of four purposes:
`authorisation`, `renewal`, `periodic_supervision`, `incident`.
`data/dossiers/` holds four of them; `schemas/dossier.py` defines the shape.

**The mandate lives on the run, not the dossier.** In AP2's human-present flow,
each task the shopper asks for becomes that run's Intent Mandate, so every run is
a complete self-contained chain: intent → cart → payment. Checking a cart against
a three-month authorisation envelope would be nearly vacuous; checking it against
what the shopper asked for *in that task* is the real test — and it is what makes
F49 ("within the rules, but not what the person meant") a checkable claim.

```
DOSSIER-KST-2026-001/
  dossier.json         identity, controls, change log, run index
  runs/*.json          one file per run the agent executed
  transactions.json    the transaction history
  ground_truth.json    answer key — NOT submitted; regulator-side, for evaluation
```

`dossier.json` carries twelve top-level fields. The ones that earn their place:

| Field | Why it is required |
|---|---|
| `submission_context` | Holds **`runs_executed_total` vs `runs_submitted`** — a gap is itself a finding — and the `deployment_target` (model version, prompt release ref, tool servers), which catches certifying one configuration and shipping another |
| `kya_credential` | The `delegation_chain`, each level typed `agent` / `org` / `human` with its own capabilities, constraints and signature. This is what proves authority terminates at a named human |
| `credential_history` | Capability creep is invisible in a single credential; it needs the series |
| `agent_card` | Declared capabilities and tool servers — what the agent claims, checkable against what it did |
| `controls` | Split into `operator_declared` and `institution_declared` **by owner, not by tag**: a bypassed operator control and a bypassed institution control are different accountable parties and different reports |
| `change_log` | `prompt_release`, `model_version`, `control_version`, `credential_reissue`, `tool_server`, `merchant_onboarded`, `policy_change`. This is what Drift's onset estimate lands on |
| `run_index` | Every run file with its SHA-256. An **attestation, not a table of contents** — a run added, removed or edited after filing is detectable |

The index is verified against the files at the door, so a dossier cannot quietly
omit an inconvenient run.

### What a run contains

Each run is one complete agent episode, and carries **its own AP2 chain**:

| Block | What it holds |
|---|---|
| `user_prompt` | What the shopper asked for. **Untrusted text** — the one place operator free text reaches a model |
| `intent_mandate` | Signed. Principal, agent, natural-language intent, and an authorisation scope: caps, currency, merchant categories, validity window, permitted counterparties |
| `construction_context` | Model attestation with `declared_version` **and** `observed_version`; policy version by prompt hash; every tool call with its schema hash, arguments, result digest and excerpt; and `selection_context` — the query, the SKU chosen, and **the alternatives considered** |
| `consent_ceremony` | Whether a human was there, `per_transaction` or `standing_authority`, and `rendered_values` — amount, merchant, line items and caps **as actually displayed** — plus the hash of what was rendered |
| `cart` | Signed. Merchant, line items, total, agent attestation, chain link |
| `payment` | Signed. Amount, method, payee, settlement status, chain link |
| `controls_evaluated` | Per control: `passed` / `triggered` / `not_evaluated`, plus any `override` with who, why and when |
| `outcome` | `completed` / `abandoned` / `blocked` / `failed` |

Three of those fields carry most of the weight. `observed_version` against
`declared_version` catches a firm running a model it never declared.
`alternatives_considered` is what makes "technically within the rules, but not
what the person meant" a checkable claim rather than an opinion. And an
`override` on a `blocking` control that was `triggered` is a hard-gate refusal —
the firm's own control said no and somebody went ahead anyway.

`outcome` is validated, not merely recorded: a `completed` run must carry a cart
and a payment; a `blocked` run must **not** carry a payment and **must** show a
triggered control. And an `override` on a control records who, why and when — an
anonymous override is not a supervisable fact.

`construction_context` is the load-bearing part. A submission of signed mandates
alone is standardised, easy to verify — and structurally incapable of revealing
a manipulated decision, because the manipulation happened before any signature
existed. Requiring the construction context makes the data ask harder and is the
only version of the product that can find the failure class everyone is actually
worried about.

The `transaction_history` filed alongside is deliberately **wider than the
submitted runs**, because structuring, counterparty concentration and velocity
are invisible in a slice.

Every mandate is signed with real **Ed25519** keys (`data/keystore.py`) and
verified with the `cryptography` library — KYA is real cryptography here, not
string comparison.

### Held by the regulator, not filed

Institutions, operators, agents, issuers and merchant registers live on the
supervisor's side, in `data/registry/`. A firm does not get to supply the
register its own credential is checked against.

### Why a firm can actually produce this

**A data requirement firms cannot meet is one nobody complies with**, so the
contract was written against systems a bank already runs. The mapping is stated
in the rulebooks themselves, not inferred:

| Dossier block | Where the firm already has it | Stated in |
|---|---|---|
| `consent_ceremony` | **SCA evidence the institution already holds** | `registry/rulesets/consent.json` |
| `construction_context` | Agent observability — *"the tool calls actually observed"* | `registry/rulesets/provenance.json` |
| `controls_evaluated` | The firm's own control framework, mapped onto **SAFR's four components**: controls repository, disposition engine, control effectiveness, audit log | `registry/rulesets/ctl.json` |
| `intent_mandate` / `cart` / `payment` | AP2 itself | `schemas/mandate.py` |

That last row is why the product is a *supervision* tool rather than a detection
one. As `ctl.json` puts it: the other rulebooks ask whether the agent misbehaved;
these ask whether the firm's own controls worked — which is the question a
supervisor is actually empowered to act on.

### The boundary of the contract, and what it costs

Deliberately *not* asked for: screenshots, provider-signed model attestation,
full catalogue archives, agent-to-agent transcripts.

That boundary is a real decision with a real price, and the rulebook records it.
**F28 — a consent screen designed to get a yes — is parked**, and `consent.json`
says exactly why:

> *"it needs a picture of the screen, which the data contract deliberately does
> not ask for."*

A named failure the catalogue carries and the contract cannot reach. Keeping the
ask to what firms already hold is what makes the regime compliable; F28 is the
line where that choice bites, and it is written into the data rather than left
for someone to discover.

### The corpus

| Dossier | Runs | Transactions | Planted defects | Clean runs |
|---|---|---|---|---|
| `DOSSIER-FRY-2026-001` | 37 | 68 | 10 | 28 |
| `DOSSIER-HAL-2026-001` | 20 | 52 | 5 | 17 |
| `DOSSIER-KST-2026-001` | 50 | 102 | 21 | 37 |
| `DOSSIER-LRK-2026-001` | 36 | 67 | 6 | 31 |
| **Total** | **143** | **289** | **42** | **113** |

The 42 planted defects are spread across **30 runs** — some carry more than one
— and the remaining **113 runs are labelled clean**. That matters for scoring:
clean runs are positive evidence, not merely the absence of findings.

All four dossiers carry `submission_purpose: authorisation`. The schema supports
`renewal`, `periodic_supervision` and `incident`, but the corpus does not
exercise them — they are supported paths, not demonstrated ones.

The data is synthetic — there is no live rail access, by design. Its credibility
rests on three things: the signatures are real, the defects are labelled in a
ground truth the pipeline never reads, and `scripts/verify_dossier.py` —
which is **forbidden from importing anything under `agents/`** — checks the
corpus independently. Ground truth the implementation helped write would be a
mirror, not an evaluation.

---

## 3 · The failure catalogue

`registry/failures.json` — catalogue `agentic-payment-failures`, version
`2026.7`. **102 named failure modes**, each with a stable id, an owning domain,
and a lifecycle phase.

![The failure catalogue](images/04-failure-catalogue.png)

By phase — *where in the life of an agentic payment it goes wrong*:

| Phase | Count | |
|---|---|---|
| P0 | 37 | Identity and authority, before any payment |
| X1 | 14 | Cross-cutting controls |
| P3 | 12 | The decision — cart construction and intent fidelity |
| P5 | 10 | Behaviour over time |
| P1 | 9 | Mandate issuance |
| P4 | 9 | Payment and settlement |
| P2 | 8 | Inputs the agent read |
| P6 | 3 | Market-level effects |

By owning domain: kya 37 · controls 14 · mandate 12 · consent 10 ·
counterparty 9 · log 7 · provenance 5 · drift 3 · systemic 3 · injection 2.

Being a catalogue rather than a slide is what makes **coverage arguable**: a
supervisor can ask "which of the 102 does this system detect, and how?" and get
an answer per id rather than a reassurance.

---

## 4 · The rulebooks

Rules are **data, never code**. Ten versioned JSON rulebooks under
`registry/rulesets/`, one per specialist:

| Rulebook | Rules | Active | Version |
|---|---|---|---|
| `kya` | 39 | 35 | 2026.11 |
| `ctl` | 15 | 15 | 2026.4 |
| `mandate` | 14 | 13 | 2026.6 |
| `consent` | 10 | 10 | 2026.3 |
| `counterparty` | 10 | 10 | 2026.2 |
| `provenance` | 7 | 6 | 2026.5 |
| `log` | 6 | 5 | 2026.6 |
| `injection` | 5 | 5 | 2026.2 |
| `systemic` | 4 | 4 | 2026.1 |
| `drift` | 3 | 3 | 2026.4 |
| **Total** | **113** | **106** | |

**The 7 inactive rules are drafts, and that is a governance feature rather than
an omission** — activating a rule *is* a promotion, and promotion is
human-gated. `MND-SIG-01` (mandate signatures must verify) is drafted and off;
its checker already exists in `ingestion/verify.py` and runs the moment it is
promoted. Of the 113: **84 are computable, 15 are judged**, and **14 carry no
`evaluation` key at all** — an older rule shape in `injection.json` and
`mandate.json` that has not been reclassified. The three do not sum to a tidy
story, and saying "84 deterministic, 15 judged" alone invites anyone who adds
them up. 24 rules carry non-empty `params` — the dials the sandbox exists to
tune.

The 10 rulebooks map **1:1** onto the 10 specialists (`ctl` → Control
Assurance), so "one agent, one domain, one book" is a property of
`agents/catalog.py` rather than an aspiration.

![The rulebook](images/05-rulebook.png)

**One agent, one book.** Rules are assigned by *the evidence they need*, not by
topic — which resolves boundary disputes mechanically rather than by argument.

Each rule declares the failures it detects (`Rule.failures`), which is how
Control Assurance later learns which risk actually materialised, and how the
sandbox can report coverage change rather than just diff text.

Even the systemic sweep has a book. A threshold living in a Python default is
the one dial the sandbox cannot tune, sweep or promote — precisely backwards for
the market-level layer a central bank is uniquely placed to supervise.

---

## 5 · The ten specialists

Each owns one supervisory question and one rulebook. Every one has a
**deterministic floor** that runs with no model at all, and at most **one
contained model call** for the part that genuinely needs judgement.

| # | Specialist | The question it answers |
|---|---|---|
| A1 | **Mandate** | Was this within what the human signed? Chain links, scope, caps, intent fidelity per line item |
| A2 | **KYA** | Does authority trace to a human? Six cryptographic rules plus the delegation chain and credential history |
| B1 | **Provenance** | Was this mandate built from inputs anyone should trust? Four-source reconciliation |
| B2 | **Injection** | Was the agent manipulated by what it read, and through which channel? |
| C1 | **Counterparty** | Who received this money? Payee, merchant, register, decline timeline |
| C2 | **Consent & Harm** | Was the human there, and is the consumer worse off? |
| D1 | **Log** | What does the history reveal? Structuring, counterparty concentration, gap distributions |
| D2 | **Drift** | What changed, and when did it start? PSI, z-score, frequency shift against a baseline |
| E1 | **Control Assurance** | Did the firm's own controls work? |
| E2 | **Systemic** | What is true of the population that no single firm can see? |

Two of these deserve a note.

**Control Assurance** is SAFR's contribution, mapped onto its four components —
controls repository, disposition engine, control effectiveness, audit log
(`registry/rulesets/ctl.json`). All 15 of its rules are deterministic; none needs
a model. It runs *after* its peers, by graph topology, and cannot be dispatched
independently. The other books ask whether the agent misbehaved; this
one asks whether the firm's declared controls did their job — which is the
question a supervisor is actually empowered to act on. It learns which risk
materialised from its peers' breach facts, and computes posture (absent /
failed / bypassed / ineffective / effective) rather than judging it.

**Systemic** is the only specialist whose question cannot be asked of one
submission. It reviews the *population* over the ledger, and its findings are
properties of the market rather than of any operator in it. A single firm cannot
know that the merchant it just started paying is also being paid, that same
week, by three other firms' agents. A supervisor sees every regulated firm at
once — a structural advantage no vendor has.

### Where the model is, and is not

- **KYA is fully deterministic** at the floor: signatures, issuers, delegation.
- **Log and Drift are statistics.** `log_stats.py` and `drift_stats.py` compute
  real numbers — per-counterparty totals, candidate clusters, PSI, z-scores —
  and nothing in the codebase pre-decides whether a candidate cluster counts as
  structuring or a shift counts as drift. That verdict is the judged part.
- **Scoring is a pure function.** No model participates in the decision.
- **Drafting is the only agent whose whole output is prose**, and its input is
  structured findings only — never raw firm text.

---

## 6 · The policy sandbox

Setting the rules is half the problem, so the system does both halves.

`sandbox/` lets a supervisor take a rulebook, edit it as a **draft** and run it
across the entire labelled corpus — before any of it is policy.

```
draft → sweep the corpus → diff against the book in force → promote (human-gated)
```

A sweep reports **precision and recall against the planted defects, false
positives on the known-clean runs, and which dispositions flipped.** That last
one is what turns a rule change from a text diff into a supervisory judgement: a
threshold that catches one more defect and refuses four compliant agents is a bad
rule, and the sweep says so before anyone is affected.

Promotion is recorded with the `sweep_id` the decision rested on, so "why is this
rule in force?" has an answer that is evidence rather than memory.

Drafts live in `registry/drafts/` and sweeps in `data/sandbox.db`, both
gitignored on purpose: a draft is a candidate and a sweep is an experiment.
Neither is policy, and neither should arrive in a checkout as if it were.

This is why rules had to be data from the start. A threshold compiled into
Python cannot be drafted, swept, diffed or promoted — and a regulator who cannot
test a rule against evidence before publishing it is guessing.

---

## Terms

| Term | Meaning |
|---|---|
| **Agentic payment** | A payment decided and executed by an AI agent, with no human approving that specific transaction |
| **AP2** | Google's Agent Payments Protocol: signed mandates (Intent → Cart → Payment) binding a purchase to a recorded consent |
| **Mandate chain** | The three linked signed records — what was asked for, what was carted, what was paid |
| **KYA** | Know Your Agent — the agent-side equivalent of KYC: identity, issuer, and authority tracing back to a responsible human |
| **Dossier** | One agent's complete submission for one review period |
| **Construction context** | What the agent read, called and chose while assembling the cart |
| **Prompt injection** | Instructions hidden in content the agent reads, so it obeys an attacker instead of its user |
| **Structuring** | Splitting payments to stay beneath a reporting threshold |
| **Drift** | Gradual behavioural change no single transaction would flag |
| **Disposition** | The supervisory conclusion: authorise, monitor, refuse, or incomplete submission |
| **Fact** | One rule's result on one run — re-checkable by a human |
| **Assessment** | A specialist's conclusion over facts, with a confidence |
| **Finding** | An assessment projected into the vocabulary the report and the score consume |
