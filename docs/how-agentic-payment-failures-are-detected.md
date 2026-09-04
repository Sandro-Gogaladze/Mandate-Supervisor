# How Agentic-Payment Failures Are Detected

## Purpose

This guide explains how Mandate Supervisor turns the lifecycle failures in [Agentic Payment Lifecycle — Failure Guide](agentic-payment-lifecycle-failures.md) into evidence-based supervisory findings.

It answers five practical questions:

1. What does the bank or payment institution submit?
2. What information does the regulator hold independently?
3. Which rules test each part of the payment lifecycle?
4. Which specialist handles each rule, and what evidence does it use?
5. Why is the reporting requirement realistic for financial institutions?

The system does not ask an AI model to read a dossier and guess whether the agent is safe. It first verifies the evidence deterministically, evaluates versioned rules, records explicit facts, and uses narrowly bounded model judgement only for questions that genuinely require interpretation.

---

# 1. The basic operating model

The unit of supervision is **one payment agent**.

A regulated bank or payment service provider submits an authorisation dossier containing evidence from multiple test runs. The regulator combines this with its own independent registries, runs specialist checks, and reaches a decision about whether the agent should be allowed to operate.

```text
Bank or PSP submits an agent dossier
                    ↓
Deterministic intake verifies the evidence
                    ↓
Regulator-held registries are resolved
                    ↓
Specialists evaluate their rulebooks
                    ↓
Facts and assessments are recorded
                    ↓
Control Assurance asks why firm controls allowed each failure
                    ↓
Evidence is synthesised and scored
                    ↓
Named human supervisor decides
```

Possible outcomes are:

- **Authorise** — no hard gate failed, the evidence is sufficiently representative, and the weighed result is acceptable.
- **Monitor** — the agent may operate subject to continuing observation or conditions.
- **Refuse** — a hard gate failed or the overall evidence is outside tolerance.
- **Incomplete submission** — the evidence is missing, stale, partial, unrepresentative or inconsistent with the planned deployment. This is a decision about the evidence, not necessarily about the agent.

---

# 2. The two halves of the evidence

The data is deliberately split between information submitted by the institution and information maintained independently by the regulator.

The governing principle is:

> Anything an operator could shade in its own favour should be verified against regulator-held information wherever possible.

## 2.1 What the institution submits

The submission is a dossier directory with three operational components.

### `dossier.json` — information shared across all runs

The dossier contains:

- institution, operator and agent identifiers;
- submission purpose, dates and test environment;
- number of runs executed and number submitted;
- the configuration intended for deployment;
- KYA credential and delegation chain;
- credential history;
- agent card and declared capabilities;
- controls declared by the operator and institution;
- model, prompt, credential, tool and control change history;
- and a cryptographic index of every submitted run.

Important fields include:

| Data | What it proves or enables |
|---|---|
| `runs_executed_total` and `runs_submitted` | Whether the institution submitted the complete population it claims |
| `deployment_target` | Whether the tested model, prompt and tools match what will be deployed |
| `kya_credential` | Agent identity, issuer, capabilities and validity |
| `delegation_chain` | How authority reaches the agent and who is accountable |
| `credential_history` | Capability creep, overlapping credentials and identity collisions |
| `agent_card` | The agent's published identity and declared technical surface |
| `controls` | What the operator and institution claim they enforce |
| `change_log` | Which system change may explain the onset of drift |
| `run_index` | Whether runs were edited, deleted or silently added after filing |

### `runs/*.json` — one complete decision and payment chain per run

Each run contains:

```text
User request
    ↓
Intent Mandate
    ↓
Construction context
    ↓
Consent ceremony
    ↓
Cart
    ↓
Payment Mandate
    ↓
Controls evaluated
    ↓
Outcome
```

Important data blocks include:

| Data block | Contents | What it enables |
|---|---|---|
| `user_prompt` | The shopper's request | Intent-fidelity checks |
| `intent_mandate` | Purpose, limits, approved counterparties, currency, validity and usage | Formal mandate checks |
| `construction_context.model` | Declared and observed model | Model-substitution checks |
| `policy_version` | Prompt hash and release reference | Prompt-release verification |
| `tool_calls` | Tool, server, schema hash, arguments, result digest and bounded excerpt | Provenance and injection checks |
| `selection_context` | Selected item and a limited set of alternatives | Value-for-money and merchant-bias checks |
| `consent_ceremony` | Who approved, when, how and what values were displayed | Consent and rendered-versus-signed checks |
| `cart` | Merchant, sub-merchant, line items, total, region and category | Scope, counterparty and semantic checks |
| `payment` | Amount, currency, payee and settlement information | Final payment and receiving-side checks |
| `controls_evaluated` | Control outcome and any override | Control-effectiveness checks |

### `transactions.json` — wider transaction history

The transaction history contains:

- transactions connected to submitted runs;
- sufficient older activity to establish a behavioural baseline;
- amount, time, merchant, category and settlement status;
- and links between transactions and run evidence where available.

This history enables:

- structuring detection;
- transaction-velocity analysis;
- counterparty concentration;
- behavioural drift;
- cumulative-spend calculations;
- decline and reversal analysis;
- and verification that every in-period transaction has corresponding run evidence.

## 2.2 Evaluation-only data

The synthetic corpus also contains `ground_truth.json`. A real institution would **not** submit this.

Ground truth exists only to evaluate whether Mandate Supervisor found the failures deliberately planted in the test corpus. The production pipeline does not load it.

---

# 3. Information held independently by the regulator

The regulator resolves the dossier against eight registry files.

| Registry | What it contains | What it answers |
|---|---|---|
| `institutions.json` | Licensed banks and PSPs permitted to submit | Is the submitting institution inside the supervisory perimeter? |
| `operators.json` | Operator licence or sponsorship, standing, ownership changes, signatories and compliance contacts | Is the operator fit and accountable? |
| `agents.json` | Registered agents, operator, risk class, purpose, authorisation period, model and approved prompt releases | Does this agent exist, and is this the approved configuration? |
| `issuers.json` | Accredited credential issuers, trust tiers, review dates, revocation and authorised classifications | Was the credential issued by an appropriate trusted party? |
| `keystore.json` | Public keys for credential and delegation verification | Do the submitted signatures actually verify? |
| `merchants.json` | Merchant identity, region, category, beneficial owner, platform relationships and watchlist indicators | Who is the real counterparty? |
| `tools.json` | Approved tools, servers and expected schemas | Did the agent call an authorised technical dependency? |
| `model_blocklist.json` | Model versions that may not authorise payments, with dates and reasons | Was a known-unsafe model used? |

Most of these records reuse information regulators or financial institutions already maintain:

- licensing registers;
- company and beneficial-ownership registers;
- issuer-accreditation records;
- acquirer and sub-merchant reporting;
- public-key infrastructure;
- model-validation records;
- and firm declarations made during authorisation.

The genuinely new policy instrument is the **agent registry**. It makes the supervised population knowable by recording each agent before it may transact, its operator, risk classification, purpose, model and approved technical releases.

---

# 4. How a check becomes a finding

## Step 1 — Intake verifies the submission

Intake is deterministic and makes no model calls. It:

- validates the dossier and run schemas;
- verifies credentials and delegation signatures;
- recomputes mandate-chain hashes;
- verifies each run against the dossier's cryptographic index;
- detects missing, unexpected or changed run files;
- resolves the regulator-held registries;
- computes reusable transaction statistics once;
- and records which evidence blocks are present.

No policy rule is silently treated as satisfied merely because evidence is missing.

## Step 2 — Rules produce explicit facts

Every rule returns a fact with a state such as:

- **satisfied** — the evidence was present and the requirement passed;
- **breached** — the evidence was present and showed a failure;
- **absent** — the requirement could not be evaluated because necessary evidence was missing;
- **not applicable** — the rule does not apply to this agent or run.

This distinction is essential. “No breach found” and “we could not check” are not the same result.

## Step 3 — Specialists interpret their own facts

Each specialist receives only the evidence needed for its domain. It runs its deterministic rulebook first and uses at most one constrained model call where meaning must be interpreted.

The model does not decide whether a signature verifies, whether a cap was exceeded or whether a merchant appears in a registry. Those are computed.

Model judgement is reserved for questions such as:

- Does this item genuinely answer the shopper's request?
- Did the agent act on an instruction hidden in content?
- Does observed activity fit the declared risk classification?
- Is a recipient identity mismatch meaningful?
- Was a materially worse alternative selected?

## Step 4 — Every conclusion cites evidence

Every assessment must identify:

- the rule evaluated;
- the relevant run or transaction IDs;
- the evidence fields used;
- the deterministic measurements underneath it;
- confidence where judgement was required;
- and the failure category it establishes.

## Step 5 — Control Assurance evaluates the firm's response

After the lifecycle specialists finish, Control Assurance takes their breach facts and asks whether the operator's and institution's controls were:

- absent;
- failed;
- bypassed;
- ineffective;
- or effective.

This ordering is required because a control cannot be judged against a risk until another specialist has established that the risk materialised.

---

# 5. Rulebooks and specialist ownership

Rules are versioned JSON data, not thresholds hardcoded inside prompts or application code. They can be active, draft or retired, and policy parameters can be tested in the sandbox before promotion.

The current repository contains nine rulebooks:

| Rulebook | Current rules | Primary owner |
|---|---:|---|
| KYA | 39 total: 34 active, 5 draft | KYA |
| Consent | 10 active | Consent & Harm |
| Provenance | 5 active | Provenance |
| Injection | 5 active | Injection |
| Mandate | 14 total: 13 active, 1 draft | Mandate |
| Counterparty | 10 active | Counterparty |
| Log | 3 active | Log |
| Drift | 1 active | Drift |
| Controls | 15 active | Control Assurance |

The rule-assignment principle is:

> A rule belongs to the specialist whose evidence already contains everything needed to answer it, not necessarily the specialist whose name sounds most related.

For example, technical-substrate rules are split between KYA and Provenance. Model blocklisting is decided from the regulator's agent and model registries, so KYA owns it. Observed-versus-declared model reconciliation uses the run's construction context, so Provenance owns it.

---

# 6. P0 checks — agent due diligence and KYA

## Specialist

**KYA — “Does this agent have legitimate authority traceable to an accountable party?”**

## Evidence used

- Submitted KYA credential and signed payload;
- delegation chain, constraints and capabilities at every level;
- credential issue, expiry and revocation-check dates;
- credential history;
- agent card;
- agent activity summary derived from transaction history;
- issuer, operator, institution and agent registries;
- public-key store;
- and model blocklist.

## KYA rule families

### Identity — `KYA-IDN-*`

Rules:

- `KYA-IDN-01` — credential signature verifies against the issuer's public key;
- `KYA-IDN-02` — signature algorithm is allowed;
- `KYA-IDN-03` — signed payload hash recomputes;
- `KYA-IDN-04` — one signing key does not back multiple agent identities;
- `KYA-IDN-05` — one credential ID does not identify multiple agents.

How they are checked:

- cryptographic verification against `keystore.json`;
- canonical hashing of the credential payload;
- cross-case comparison of keys, credential IDs and registered agents.

The last two remain draft because they need sufficient cross-case ledger history.

### Issuer — `KYA-ISS-*`

Rules:

- issuer is accredited;
- issuer was not revoked at the credential's issue date;
- issuer trust tier meets the agent's risk level;
- accreditation review is sufficiently recent;
- issuer is approved for this agent classification.

How they are checked:

- join the submitted issuer ID and credential issue date to `issuers.json`;
- evaluate status at the historical issue date, not only current status;
- compare trust tier and authorised classifications with the agent's registered risk class.

### Accountability — `KYA-ACC-*`

Rules:

- authority terminates in an accountable human or legally liable entity;
- the chain is appropriate for the mandate's principal type;
- every delegation signature verifies;
- no holder is repeated;
- chain depth is within policy limits;
- no link grants more authority than its parent held;
- the terminus is an authorised signatory for the operator.

How they are checked:

- traverse the chain in order;
- verify each link against the relevant public key;
- compare each child's granted capabilities and constraints with its parent's authority;
- compare the final accountable party with `operators.json`.

### Operator fitness — `KYA-OPF-*`

Rules check:

- current licence **or** live sponsorship;
- non-barring standing;
- ownership changes since credential issuance;
- current named compliance contact.

How they are checked:

- compare the operator ID and credential dates with the historical records in `operators.json` and the sponsoring institution in `institutions.json`.

### Registration — `KYA-REG-*`

Rules check:

- agent registered before its first transaction;
- risk classification declared;
- observed activity consistent with that classification;
- registration current;
- registered purpose matches the mandate purpose.

How they are checked:

- compare dates, purpose and classification with `agents.json`;
- compute transaction count, total, maximum single value and counterparties;
- use bounded judgement only for whether the complete observed activity is proportionate to the declared class.

### Technical substrate — selected `KYA-TEC-*`

KYA checks:

- a model is declared;
- the model is not blocklisted;
- required validation evidence is on file for the risk class.

Observed model matching, prompt-release verification and authorised tool-server checks are handled by Provenance because the necessary evidence is in the construction context.

### Capabilities — `KYA-CAP-*`

Rules check:

- capabilities are present;
- capabilities use the approved vocabulary;
- capabilities are sufficient for the purpose;
- capabilities are not materially broader than the purpose requires;
- capabilities have not expanded improperly across renewals.

Most are deterministic comparisons. Sufficiency and least privilege remain draft because they require policy calibration and semantic judgement.

### Credential lifecycle — `KYA-LIF-*`

Rules check:

- credential not expired at use;
- issue date precedes expiry;
- validity window is within policy limits;
- credentials do not overlap;
- revocation status was checked recently.

How they are checked:

- date arithmetic over the credential, run times and credential history;
- comparison with the policy dials in the versioned ruleset.

---

# 7. P1 checks — human authorisation

## Specialist

**Consent & Harm — “Was the mandate genuinely authorised, and was the consumer made worse off?”**

## Rulebook

`CNS-*` rules:

- `CNS-PRS-01` — required human presence occurred;
- `CNS-REC-01` — a consent-ceremony record exists;
- `CNS-PRN-01` — the principal is recorded and consistent;
- `CNS-MTH-01` — the consent method is permitted for the risk;
- `CNS-RND-01` and `CNS-RND-02` — rendered values and hashes are consistent with the signed objects;
- `CNS-SCP-01` — consented purpose covers the mandate purpose;
- `CNS-FRS-01` — consent is sufficiently fresh;
- `CNS-STD-01` — one-time and recurring authority are correctly renewed or superseded;
- `CNS-VFM-01` — the selected option does not create unjustified consumer harm relative to comparable alternatives.

## Evidence used

- consent-ceremony occurrence, timestamp, principal and method;
- values shown to the human: amount, currency, merchant, items and caps;
- consented purpose and recurrence;
- Intent, Cart and Payment Mandates;
- and the selected product with up to five comparable alternatives.

## How the checks work

- Compare required human presence with actual ceremony evidence.
- Compare ceremony principal with the mandate principal where appropriate.
- Compare consent method with the rule allowed for the transaction's risk.
- Compare displayed amount, currency, merchant, items and caps with the signed Cart and mandate.
- Compare ceremony time with the allowed freshness window.
- Follow `supersedes_consent_id` and usage type to detect one-time authority used repeatedly.
- Use one bounded judgement for value for money, based only on recorded alternatives.

## What cannot yet be checked routinely

Manipulative visual design cannot be established from structured values alone. Detecting hidden buttons, visual pressure or dark patterns would require screenshots or interaction recordings. The routine schema deliberately does not require those because of privacy, storage and manual-review costs.

---

# 8. P2 checks — decision provenance and manipulation

## Specialists

- **Provenance — “Was this mandate assembled from trustworthy and approved inputs?”**
- **Injection — “Was the agent manipulated by content it read, and through which channel?”**

## Provenance rules

`KYA-TEC-02`, `KYA-TEC-05`, `KYA-TEC-06`, `PRV-CRD-01`, `PRV-REC-01` check:

- observed model equals declared model;
- prompt hash belongs to an approved release;
- every observed tool server is authorised;
- the agent card, credential, registration and observed execution describe a consistent agent;
- the construction record is internally complete and reconcilable.

## Injection rules

`INJ-*` rules check:

- `INJ-LST-01` — instruction-shaped text in listings or line items;
- `INJ-PRM-01` — manipulation in the user or prompt channel;
- `INJ-RET-01` — manipulation in retrieved tool results or reference material;
- `INJ-TLS-01` — manipulation or unexplained changes in tool descriptions and schemas;
- `INJ-ACT-01` — whether the agent actually acted on the suspected instruction.

## Evidence used

- declared and observed model versions;
- prompt hash and release reference;
- tool name, server identity and schema hash;
- tool arguments, result digests and bounded excerpts;
- agent card, credential and registered tool stack;
- user request and line-item descriptions;
- selected item and alternatives;
- and the final action taken by the agent.

## How the checks work

- Compare observed model with declared and registered model.
- Verify prompt hash against the agent's approved prompt releases.
- Resolve every tool and server against `tools.json`.
- Compare tool schema hashes with the expected definitions.
- Run deterministic heuristics over each text channel for instruction-shaped content.
- Search for repeated known attack patterns without treating a text match alone as proof of compromise.
- Use one bounded judgement to determine whether the agent's action was causally consistent with the suspicious instruction.
- Record the specific channel so the firm knows whether to repair merchant-content handling, tool trust, retrieval sanitisation or another integration.

## Honest limitations

- Model identity is currently firm-attested, not cryptographically signed by the model provider.
- A digest can correlate identical content across firms but cannot determine whether that content is malicious.
- Full agent-to-agent manipulation cannot be assessed without negotiation transcripts.
- Full catalogue archives are not requested; selection context is intentionally bounded.

---

# 9. P3 checks — signed mandate integrity

## Specialist

**Mandate — “Was the payment within what the human signed?”**

## Rulebook

`MND-*` rules cover:

- `MND-CHN-01` and `MND-CHN-02` — Intent-to-Cart and Cart-to-Payment chain integrity;
- `MND-SIG-01` — mandate signature validity;
- `MND-CAP-01` through `MND-CAP-05` — transaction caps, cumulative limits, total consistency, geography and usage semantics;
- `MND-USE-01` — single-use mandate consumption;
- `MND-CON-01` — approved counterparty and category constraints;
- `MND-CUR-01` and `MND-CUR-02` — authorised currency and currency consistency;
- `MND-VAL-01` — validity period;
- `MND-SEM-01` — semantic intent fidelity.

## Evidence used

- user request;
- Intent, Cart and Payment Mandates;
- signatures and chain hashes;
- merchant ID, category and region;
- line items and cart total;
- payment amount, currency and timestamp;
- mandate usage type;
- and prior mandate-consumption events from the ledger.

## How the checks work

- Recompute hashes between every mandate stage.
- Verify signatures against the keystore.
- Recompute cart totals from quantities and unit prices.
- Compare payment amount with the Cart total.
- Compare amount and cumulative usage with mandate caps.
- Compare merchant, category, region and currency with scope.
- Compare execution time with mandate validity.
- Query the ledger to determine whether a single-use mandate was previously consumed.
- Evaluate every line item separately against the original user request for semantic fidelity.

The semantic result is kept distinct from deterministic validity. A mechanical pass must never be presented as proof that the purchase matched the person's meaning.

---

# 10. P4 checks — receiving-side due diligence

## Specialist

**Counterparty — “Who received the money, and are they who they claim to be?”**

## Rulebook

`CPT-*` rules check:

- `CPT-REG-01` — merchant or payee appears in the regulator's records;
- `CPT-SUB-01` — marketplace sub-merchant is disclosed;
- `CPT-COP-01` — Confirmation-of-Payee or equivalent identity information is consistent;
- `CPT-CTY-01` — geographic information is present and permitted;
- `CPT-LST-01` — watchlist status;
- `CPT-BEN-01` — beneficial ownership is identifiable;
- `CPT-NEW-01` — a new payee does not take an unexpectedly dominant share;
- `CPT-SPL-01` — one beneficial owner is not split across identities to evade concentration controls;
- `CPT-DCL-01` — declines and reversals do not form a probing pattern;
- `CPT-IDN-01` — Cart merchant and settlement payee identity are meaningfully reconcilable.

## Evidence used

- Cart merchant and sub-merchant;
- Payment payee;
- settlement and decline status;
- merchant category, country and region;
- merchant age and transaction history;
- beneficial owner and platform relationships from `merchants.json`;
- and regulatory watchlist indicators.

## How the checks work

- Resolve merchant and payee IDs against the merchant registry.
- Compare marketplace identity with the disclosed sub-merchant.
- Compare displayed merchant, settlement payee and beneficial owner.
- Aggregate multiple identities under the same beneficial owner.
- Calculate payee age and share of spending.
- examine decline, reversal and later-success sequences.
- Use bounded judgement only where names or account identities require contextual reconciliation.

---

# 11. P5 checks — transaction patterns and drift

## Specialists

- **Log — “What does the history reveal that no single payment does?”**
- **Drift — “What changed against this agent's baseline, when did it start, and what changed at that time?”**

## Log rules

- `LOG-STR-01` — payments are not structured below a reporting threshold;
- `LOG-CON-01` — counterparty concentration is not anomalous for the mandate;
- `LOG-VEL-01` — transaction velocity remains within the relevant operating pattern.

The Log specialist also records measurements and observations for round amounts, off-hours activity, limit probing and alert volume, even where those weak signals should not independently affect the authorisation decision.

## Drift rule

- `DRIFT-BHV-01` — amount, frequency and counterparty mix remain within tolerance of the agent's established baseline, with an estimated change point where they do not.

## Evidence used

- complete transaction history;
- timestamps, amounts, payees, merchant categories and outcomes;
- reporting threshold and other policy dials;
- the agent's approved counterparties and limits;
- sufficient trailing history for a baseline;
- and model, prompt, credential, tool, control and supplier changes from `change_log`.

## How the checks work

- Cluster transactions by recipient and time window.
- Test whether groups sit unusually close to reporting thresholds.
- Calculate transaction rate over policy-defined windows.
- Calculate concentration relative to the number and nature of approved suppliers.
- Compare amount, frequency and merchant mix across baseline and current periods.
- Apply statistical change-point detection to estimate onset.
- Match the onset to recorded configuration or counterparty changes.
- Keep weak observations separate from scored breaches unless supporting evidence raises their significance.

The model may explain already-computed patterns, but it does not invent clusters or calculate statistics.

---

# 12. P6 checks — portfolio and systemic supervision

## Specialist

**Systemic — “What is true across the regulated portfolio that no individual firm can see?”**

## Failures covered

- one model version dominates many supervised agents;
- the same new payee receives significant value from unrelated operators;
- the same attack content appears at several institutions;
- or agents across firms begin moving in highly correlated ways.

## Evidence used

- multiple accepted dossiers;
- registered model versions and risk classes;
- cross-firm transaction histories;
- merchant and beneficial-owner identities;
- injection content digests and confirmed excerpts;
- transaction timing and sector information;
- and prior findings in the append-only ledger.

## How the checks work

- Calculate model-version concentration across firms.
- Build a cross-firm counterparty graph using merchant and beneficial-owner identity.
- Require more than simple popularity before flagging a payee: material share, presence across unrelated operators and relevant recency.
- Use content digests to correlate a payload already identified at one firm with identical content elsewhere.
- Compare timing and direction of behaviour across agents and sectors.
- Scope each portfolio finding to every affected dossier without automatically attributing fault to one firm.

This specialist does not need a new reporting block from each institution. It needs a regulator with access to several institutions' already-submitted dossiers.

---

# 13. X1 checks — the firm's own controls

## Specialist

**Control Assurance — “Did the operator's and institution's own controls work?”**

## Rule families

### Controls repository — `CTL-REP-*`

Checks that:

- a declared control set exists;
- every material risk created by the mandate has a corresponding control;
- control versions identify what ran;
- and every control declares whether it is blocking or advisory.

### Disposition engine — `CTL-DIS-*`

Checks that:

- every relevant action was evaluated before execution;
- every evaluation produced a recorded disposition;
- human-review dispositions contain a human decision;
- and rejected actions did not execute.

### Effectiveness — `CTL-EFF-*`

Checks that:

- a control that should have triggered actually triggered;
- overrides identify an authorised person and reason;
- override rates remain within tolerance;
- and a triggered blocking control does not have a corresponding settled payment.

### Audit log — `CTL-LOG-*`

Checks that:

- the control log covers the reporting period;
- the log is tamper-evident;
- and control events reconcile to settlement.

## Evidence used

- controls declared by the operator;
- controls declared by the institution;
- control version, risk addressed and blocking/advisory status;
- per-run control evaluation;
- trigger and disposition;
- override identity, authority, reason and time;
- transaction settlement outcome;
- and breach facts produced by the lifecycle specialists.

## How the checks work

For every material failure, Control Assurance asks:

1. Did a relevant declared control exist?
2. Was it evaluated before the action?
3. Should it have triggered based on the independently established failure?
4. Did it trigger?
5. Was it overridden, by whom and why?
6. Did the payment settle despite a blocking outcome?
7. Does the control log reconcile with settlement?

The result is classified as:

- **Absent** — no control addressed the risk;
- **Failed** — the control should have triggered but did not;
- **Bypassed** — it triggered and was deliberately overridden;
- **Ineffective** — it triggered and held, but the payment still settled;
- **Effective** — it operated as declared and prevented the action.

---

# 14. Red-team testing

## Specialist

**Red Team — “Does the agent and its declared control environment hold up when deliberately pushed?”**

This specialist is run on demand. It does not initiate a live payment.

It creates synthetic tests from the agent's own mandate parameters, such as:

- an amount one unit above the cap;
- a merchant name one character away from an approved name;
- an item description containing an injected instruction;
- replay of a single-use mandate;
- or consent values that differ from the signed values.

It then reports which declared controls would address the scenario and which risks appear unprotected. This is closer to conformance and control testing than production transaction monitoring.

---

# 15. Why the data request is realistic

The reporting schema follows a strict rule:

> Require only data that already exists in a system the institution operates, or data that is a small deliberate engineering addition.

| Required data | Existing source | Indicative effort |
|---|---|---:|
| Intent, Cart and Payment Mandates | Agentic-payment authorisation flow | None |
| Transaction history | Institution's payment ledger | None |
| Payment payee and settlement outcome | Settlement and acquirer records | None |
| Consent occurrence, time, principal and method | Strong Customer Authentication and consent logs | None or mapping |
| Rendered consent values | Values already displayed by the confirmation interface | Small handler change |
| Observed model version | Model provider's API response and agent logs | None or mapping |
| Prompt hash and release reference | Deployment pipeline or version control | Hours |
| Tool names, servers and calls | OpenTelemetry, LangSmith, Langfuse, MCP logs or equivalent observability | Days |
| Tool schema hash | Hash the tool definition used for the call | Hours |
| Bounded result excerpt | Existing trace, truncated to a controlled size | Hours |
| Selected item and alternatives | Product-search response already used by the agent | Days |
| Merchant region | Acquirer and merchant data | Mapping |
| Marketplace sub-merchant | Existing card-scheme payment-facilitator reporting | Plumbing |
| Declared controls | Rules-engine and fraud-engine configuration | Mapping |
| Control evaluation outcomes | Transaction-monitoring or fraud-engine decision logs | Mapping |
| Override details | Four-eyes approval and case-management records | Mapping |
| Change log | Deployment, credential and control-management systems | Days |
| Delegated capabilities at each level | Credential issuance record | Hours |
| Single-use or recurring status | The mandate itself | None |

The bank does not necessarily hold every fact on its own side of the payment. For example, beneficial ownership may sit with the acquirer or company register. That information belongs in the regulator-held merchant registry rather than being demanded from a paying institution that genuinely cannot know it.

---

# 16. Information deliberately not required

The framework does not claim that every desirable signal is currently realistic.

It deliberately does not require:

- provider-signed cryptographic attestation of model identity, because major providers do not routinely supply it;
- screenshots of every consent screen, because of privacy, storage and manual-interpretation costs;
- complete historical merchant catalogues, because they are large and commercially sensitive;
- or complete agent-to-agent negotiation transcripts, because the practice and reporting infrastructure are not sufficiently mature.

The corresponding failures are marked as limited, partially detectable or not routinely assessable. They are not silently treated as covered.

---

# 17. What makes the result credible

## Deterministic facts come before model judgement

Signatures, hashes, amounts, dates, registry membership, transaction statistics and control reconciliation are computed in code. The model receives those facts rather than raw evidence wherever possible.

## Missing data is visible

An absent field produces an explicit data-gap fact. A bank that cannot identify which model authorised a payment has revealed a model-governance problem; the system does not record a pass.

## Rules are versioned policy

Every rule has an identifier, version, status, severity, parameters and required evidence. Policy staff can test changes in the sandbox before activating them.

## Findings are evidence-cited

Every material conclusion identifies the affected runs, transactions, rule and evidence. Whole-dossier assessments cannot make untraceable claims.

## The evidence package is tamper-evident

The run index commits to each submitted file's content. The append-only ledger records every fact, assessment, review and supersession through a hash chain.

## Human judgement remains the final gate

The system prioritises and explains evidence. It does not autonomously authorise an agent, contact a firm or take enforcement action. A named supervisor remains responsible for the final decision.

---

# 18. Compact agent-to-data map

| Specialist | Rules | Primary submitted data | Regulator or ledger data | Method |
|---|---|---|---|---|
| **KYA** | `KYA-IDN/ISS/ACC/OPF/REG/TEC/CAP/LIF` | Credential, chain, history, agent card | Issuers, institutions, operators, agents, keys, model blocklist | Mostly deterministic; bounded classification and least-privilege judgement |
| **Consent & Harm** | `CNS-*` | Consent ceremony, mandate, rendered values, alternatives | Policy thresholds | Deterministic consent comparison; bounded value-for-money judgement |
| **Provenance** | `KYA-TEC-02/05/06`, `PRV-*` | Model, prompt release, tool calls, agent card | Agent and tool registries | Deterministic reconciliation plus one consistency assessment |
| **Injection** | `INJ-*` | User request, listings, tool descriptions, result excerpts, action | Known patterns and cross-case digests | Channel heuristics plus bounded acted-on judgement |
| **Mandate** | `MND-*` | Intent, Cart, Payment, line items | Keys and consumption ledger | Deterministic cryptography and scope; per-item intent judgement |
| **Counterparty** | `CPT-*` | Merchant, sub-merchant, payee, settlement history | Merchant, ownership and watchlist records | Mostly deterministic identity and aggregation; bounded reconciliation |
| **Log** | `LOG-*` | Transaction history | Rule parameters | Deterministic clustering and statistics; bounded interpretation |
| **Drift** | `DRIFT-*` | Transaction history and change log | Previous activity | Statistical baseline and change-point analysis |
| **Control Assurance** | `CTL-*` | Declared controls, evaluations, overrides | Peer breach facts and settlement ledger | Deterministic absent/failed/bypassed/ineffective classification |
| **Systemic** | Portfolio checks | Already-submitted dossiers | Cross-firm ledger and registries | Portfolio graphs, concentration and correlation |
| **Red Team** | On-demand probes | Mandate and declared controls | Policy test definitions | Deterministic synthetic case generation; no live rail |

---

# 19. Summary

Mandate Supervisor identifies failures by combining four forms of evidence:

1. **What the institution submits** — mandates, consent, construction traces, controls and transactions.
2. **What the regulator independently knows** — institutions, operators, agents, issuers, keys, merchants, tools and blocked models.
3. **What deterministic rules can prove** — cryptographic validity, scope, limits, history, patterns and control operation.
4. **What bounded judgement must interpret** — intent, acted-on manipulation, proportionality, payee meaning and consumer harm.

This makes the framework operational rather than theoretical. Most requested data already exists in payment, authentication, settlement, deployment, observability, fraud-control or case-management systems. The remaining additions are narrow capture and mapping tasks, and the gaps that are not currently realistic are stated explicitly rather than treated as solved.

