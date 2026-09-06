# 03 · The data

Detection is downstream of evidence. This document explains what is submitted,
what the regulator holds instead, and why the boundary between the two is the
single most important design decision in the product.

## 1 · The founding rule of the data contract

> **Anything an operator could shade in its own favour lives regulator-side.**

An operator submits what it did. It does not get to supply the yardstick it is
measured against.

```
SUBMITTED (the dossier directory)          HELD BY THE REGULATOR (data/registry/)
─────────────────────────────────          ──────────────────────────────────────
dossier.json      what the runs share      institutions.json    who may submit
runs/RUN-*.json   one AP2 chain each       operators.json       who may operate
transactions.json the wider ledger         agents.json          WHICH AGENTS EXIST ←
ground_truth.json labels — eval only       merchants.json       who was really paid
                                           tools.json           authorised tool servers
                                           model_blocklist.json barred models
                                           issuers.json         accredited credential issuers
                                           keystore.json        public keys
```

The operator *declares* which model it used (`self_attested_by`). Whether that
model is **blocked**, whether that prompt release was **approved**, and who
actually **owns** the merchant that received the money are all facts the
regulator keeps. That is what turns a self-report into something checkable.

**`agents.json` does not exist in any jurisdiction today.** A register of which
AI payment agents exist, who operates them, how they are classified, and what
risk class they carry — that is the policy proposal embedded in the data model.
Everything else in the registry has an obvious precedent; this one is the new
thing being argued for.

## 2 · AP2, and why the mandate lives on the run

AP2 defines three signed mandates — **Intent**, **Cart**, **Payment** — and two
flows:

| Flow | The Intent Mandate is | Who signs the Cart |
|---|---|---|
| **Human-present** (e-commerce shopping) | created *for this one shopping task* | the shopper, on exact items and price |
| Human-not-present (standing delegation) | signed in advance with conditions | nobody, at purchase time |

**We model human-present.** The shopper says *"white running shoes under $120"*
and that sentence becomes the Intent Mandate for that task. So the mandate lives
**on the run**, and every run is a complete, self-contained chain:

```
  user_prompt  →  Intent Mandate  →  Cart Mandate  →  Payment Mandate
   (untrusted)     signed by the     signed by the    signed by the
                   shopper           shopper          agent
                        └── hash-linked ──┴─ hash-linked ─┘
```

This is load-bearing, not cosmetic. Checking a cart against a three-month
spending envelope is nearly vacuous — almost anything passes. Checking it
against *"vitamin C serum, around $50"* is not. The whole class of failure where
**the agent bought something the shopper did not ask for** only becomes a real
test in this shape.

## 3 · What a run contains

One run file is one complete decision, from the sentence a human typed to the
money leaving. Its blocks, and why each exists:

| Block | Contents | Why it must be there |
|---|---|---|
| `user_prompt` | The shopper's own words | **Untrusted.** It is the injection surface, and it is also the only ground truth for what was actually wanted |
| `intent_mandate` | Principal, agent, natural-language intent, `authorization_scope` (caps, currency, categories, counterparties, geography, validity window, `human_presence_required`, `usage`), consent method, signature | This is what "authorised" means for this run |
| `construction_context` | Declared vs **observed** model version, prompt release ref and hash, every tool call with server id, schema hash, arguments, result digest and a capped result excerpt, plus `selection_context` (query, chosen SKU, alternatives considered) | **This is the P2 evidence.** Without it the entire attack surface where the real attacks live is invisible |
| `consent_ceremony` | Whether it occurred, its scope, the **values actually rendered on screen**, a hash of them, what was consented to, and any superseded consent | The only way to check that the human approved *the same thing that got signed* |
| `cart` | Merchant (id, MCC, country, region, sub-merchant), line items, total, currency, the agent's own attestation, hash link to the Intent, signature | The signed artifact |
| `payment` | Amount, payment method, **payee** (settlement account, scheme, country, beneficiary name), settlement status, hash link to the Cart, signature | Where the money actually went — which is not the same question as who the merchant was |
| `controls_evaluated` | Per control: outcome (`passed` / `triggered` / `not_applicable`), and any **override** with who, why and when | The firm's own governance, on the record, checkable |
| `outcome` | completed / abandoned / blocked / failed | Distinguishes "the control worked" from "nothing happened" |

Four fields are worth calling out because they carry more weight than their size
suggests:

- **`observed_version` beside `declared_version`.** One field turns "we use an
  approved model" from an assertion into a check.
- **`rendered_values`.** The consent screen said $54.99; the signed cart says
  $329.00. Nothing else in AP2 can catch that.
- **`granted_capabilities` per delegation level.** Without it a delegation chain
  is just a list of names, and "a child was granted more authority than its
  parent held" is undetectable.
- **`usage`** (`single_use` / `recurring`, `max_uses`, `uses_consumed`). Without
  it, "the same authorisation was drawn on twice" has no baseline to violate.

## 4 · What the dossier adds on top of the runs

`dossier.json` holds everything the runs share:

- **`submission_context`** — the window covered, the environment, the number of
  runs executed *versus* the number submitted, and the **deployment target**:
  the model version, prompt release and tool servers the operator is asking to
  be authorised for. The gap between runs executed and runs submitted is one
  submission-integrity signal; the gap between the deployment target and what
  the runs actually ran on is another, and it is the cheapest and most important
  check in the entire system.
- **`kya_credential`** — the agent's identity credential: issuer, validity
  window, capabilities, revocation check, Ed25519 signature, and the
  **delegation chain** with a signed link per level.
- **`credential_history`** — previous credentials. A single credential cannot
  reveal a renewal that never revoked its predecessor; only the series can.
- **`agent_card`** — the agent's public self-description (declared capabilities,
  declared tool servers) with its hash and signature. It is one of four sources
  that should all agree about what this agent is.
- **`controls`** — split into **`operator_declared`** and
  **`institution_declared`**, because they are different accountable parties and
  a finding against each goes in a different report.
- **`change_log`** — dated events (model repin, prompt release, control change).
  This is what a detected behavioural change gets anchored to.
- **`run_index`** — one entry per run: id, filename, **sha256**.

## 5 · The run index is an attestation, not a table of contents

This is the design point most easily missed. The index carries a content digest
per run, which means:

- A run **edited** after filing is detectable.
- A run **deleted** after filing is detectable.
- A run **slipped in** after filing is detectable.

So "did the operator file everything?" stops resting on a number the operator
declares about itself and becomes structural. The loader deliberately scans
**both** the directory and the index, because two views of "which runs are in
this dossier" must never be allowed to disagree silently. A submission whose
index contradicts its own contents is **rejected at the door**, with the reason
— accepting one would make the attestation meaningless.

## 6 · Why the transaction history is wider than the runs

`transactions.json` is not a duplicate of the runs. It is the agent's payment
ledger, deliberately wider:

- Roughly **45 in-window transactions carrying a `run_ref`** — these correspond
  to submitted runs.
- Roughly **55 trailing transactions with no `run_ref`** — history before the
  submission window.

Two reasons:

1. **Statistics need a baseline.** Detecting behavioural drift requires enough
   history to split into "before" and "after" — at least 30 transactions. The
   submitted runs alone would leave a large part of the rulebook unable to
   evaluate at all.
2. **A transaction with no `run_ref` *inside* the window is itself a finding.**
   The agent paid for something and no run was filed for it.

## 7 · Two things a hash cannot do

Being precise about this is what keeps the system honest:

- **`result_digest` is correlation, not detection.** A hash proves the bytes
  that arrived were intact. It cannot reveal that those bytes contained an
  injected instruction. That is why runs also carry a capped
  **`result_excerpt`** (~2000 characters) — the excerpt is what actually closes
  the retrieved-content channel. And once one firm's excerpt has been read and
  understood, **the same digest appearing at another firm identifies the same
  payload for free** — which is a genuine cross-firm detection that only a
  supervisor can perform.
- **A content index cannot prove that unfiled runs never existed.** It proves
  that what *was* filed is intact and complete against its own attestation.
  Nothing more. The system says exactly this and does not overclaim.

## 8 · Labels are separate, on purpose

`ground_truth.json` holds the planted defects and the labelled-clean runs. It is
a **separate file**, and the pipeline loader simply never opens it. That
omission *is* the isolation mechanism — not a flag, not a filtered copy, not a
model that someone might forget to strip. Additionally, the upload path removes
any `ground_truth.json` from a submitted zip, so a submitted dossier cannot
smuggle in its own answer key.

The same discipline appears in the evaluation harness: the labels are opened
**only after** the production pipeline has returned its result, and the
independent verifier is forbidden from importing anything from `agents/` —
ground truth that the implementation helped write is a mirror, not an
evaluation.
