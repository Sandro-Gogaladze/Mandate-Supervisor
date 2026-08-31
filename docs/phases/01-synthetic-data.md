# Phase 1 — Synthetic Data

Status: complete. Corpus content authored by hand (this doc + `data/`); Pydantic schemas (`schemas/`), the loader/validator (`data/loader.py`), and real Ed25519 signing (`scripts/sign_corpus.py`) are all built and tested (`tests/`). See §5a below for where the real files diverged from this spec.

## 1. What this data is standing in for

In the real workflow (concept note §2), a firm's payment-agent operation sends Mandate Supervisor a **routine submission**: the AP2 mandate chain for a specific agent decision (Intent → Cart → Payment) plus that agent's recent **transaction history**. Nothing here is live — no real rails, no real firms, no real people. Every firm, agent, human principal, vendor, and issuer below is fictional, built to be internally consistent across the corpus rather than randomized per-record, because the case officer persona this is designed for reads a submission as a story (who authorized what, who this agent actually paid, does the pattern match), not as a spreadsheet of independent rows.

**Who consumes this and how:**
- **Ingestion** (deterministic, no LLM) reads a case, verifies the hash chain and signatures, and normalizes it. This corpus is what ingestion's tests run against.
- **Mandate, KYA, Log, Drift agents** each read the normalized case + active ruleset and emit findings. Every case below is built around a specific finding one or more of these agents should surface — this corpus *is* the ground truth for the eval harness (PLAN item 16: per-agent precision/recall against labelled data).
- **A human case officer**, eventually, reads the same submission through the dashboard. Realism matters here specifically because a case that looks obviously synthetic (round numbers, generic "Vendor A" names, uniform time gaps) won't exercise the same judgment a real submission would, and won't demo convincingly either.

## 2. Schema

This is the field-level shape the corpus follows. It is *not* a Pydantic file — `schemas/` (later work) will formalize this into typed models; this is the reference those models should match.

### 2.1 Common signature envelope

Every mandate object ends with:

```
"signature": {
  "alg": "Ed25519",
  "signer_key_id": "did:key:z6Mk...",       // whoever is attesting this object (human, agent, or merchant key)
  "signed_payload_hash": "sha256:<hex>",     // hash of this object's own canonical content, minus the signature block itself
  "value": "<placeholder — see §5>",
  "signed_at": "<ISO8601>"
}
```

Downstream mandates additionally carry a **chain link** back to the mandate they're built on:

```
"chain_link": {
  "prev_mandate_id": "...",
  "prev_mandate_hash": "sha256:<hex>"   // must equal prev mandate's own signed_payload_hash — this equality is what ingestion checks
}
```

A case is chain-broken when `chain_link.prev_mandate_hash` does not equal the referenced mandate's actual `signed_payload_hash` — i.e. the downstream mandate was built against content that has since changed, or was never the content it claims.

### 2.2 Intent Mandate

The human's up-front delegation. One per agent per authorization period (can outlive many Cart/Payment mandates underneath it).

| Field | Notes |
|---|---|
| `intent_mandate_id` | |
| `protocol_version` | `"ap2/1.2"` throughout this corpus |
| `issued_at`, `expires_at` | |
| `principal` | `{name, role, principal_id, org}` — the human who authorized this |
| `agent` | `{agent_id, agent_name, operator_firm, model_version}` |
| `natural_language_intent` | The actual prompt/instruction the human gave the agent, verbatim. This is the thing the Cart's `agent_attestation.reasoning` gets semantically checked against. |
| `authorization_scope.purpose_category` | Enum-ish label, e.g. `"office_supplies_procurement"` |
| `authorization_scope.max_transaction_amount` / `.max_cumulative_amount` / `.currency` | Hard caps |
| `authorization_scope.valid_from` / `.valid_until` | |
| `authorization_scope.allowed_merchant_categories` | MCC list |
| `authorization_scope.allowed_counterparties` | Optional named allowlist (not all mandates use one) |
| `authorization_scope.geographic_scope` | |
| `authorization_scope.human_presence_required` | `false` = agent may act without per-transaction confirmation, within scope |
| `consent` | `{method, timestamp, device_id}` — how the human actually gave this consent |
| `signature` | envelope, signer = principal's key |

### 2.3 Cart Mandate

What the agent actually proposes to buy, built against one Intent.

| Field | Notes |
|---|---|
| `cart_mandate_id` | |
| `chain_link` | → Intent Mandate |
| `created_at` | |
| `merchant` | `{merchant_id, name, mcc, country}` |
| `line_items` | `[{sku, description, qty, unit_price}]` — **note:** `description` is merchant-authored free text and is the one field in this whole schema that can carry adversarial content (see Case 007) |
| `cart_total`, `currency` | |
| `agent_attestation.reasoning` | The agent's own natural-language justification for this cart — "prompt playback." This is what the Mandate agent's one LLM subcheck compares against the Intent's `natural_language_intent`. |
| `signature` | envelope; in practice two signers matter — merchant key + agent key — this corpus signs with the agent's key and treats merchant authenticity as covered by the merchant's own registry entry |

### 2.4 Payment Mandate

The actual authorization to move money, built against one Cart.

| Field | Notes |
|---|---|
| `payment_mandate_id` | |
| `chain_link` | → Cart Mandate |
| `authorized_at` | |
| `amount`, `currency` | Must equal Cart's `cart_total`/`currency` when compliant |
| `payment_method` | `{type, instrument_id_masked, issuer}` |
| `settlement_status` | `"settled" \| "declined" \| "reversed"` |
| `signature` | envelope |

### 2.5 KYA Credential

The agent's identity credential — separate from any single mandate chain, checked once per case by the KYA agent.

| Field | Notes |
|---|---|
| `credential_id` | |
| `agent_id`, `agent_name`, `operator_firm` | |
| `issuer` | `{issuer_id, issuer_name}` — cross-referenced against `data/registry/issuers.json` |
| `issued_at`, `expires_at` | |
| `capabilities` | Scopes this credential attests the agent may hold (should be ⊇ what any Intent grants it) |
| `delegation_chain` | Ordered list, index 0 = agent itself, terminating in a named human: `[{level, holder_id, holder_type: "agent"\|"org"\|"human", name, signature}]` |
| `signature` | envelope, issuer's key |

A credential is a **synthetic-identity** finding when: the issuer isn't in the trust registry (or is `revoked`), or the `delegation_chain` doesn't terminate in a `holder_type: "human"` link.

### 2.6 Transaction log entry

The agent's settled payment history — many per case, this is what Log and Drift read.

| Field | Notes |
|---|---|
| `transaction_id` | |
| `timestamp` | |
| `agent_id` | |
| `payment_mandate_ref` | Only populated for the transaction(s) tied to this case's mandate chain; historical entries reference their own (not-included) payment mandates by id only |
| `counterparty_name`, `counterparty_id`, `mcc` | |
| `amount`, `currency` | |
| `status` | |
| `channel` | `"agent_api"` throughout (vs. a human-initiated channel, for contrast if ever needed) |

### 2.7 Case bundle

Each case file (`data/cases/case-XXX-*.json`) bundles one full submission:

```
{
  "case_id": "...",
  "label": "<one of the 7 scenario labels>",
  "firm": {...},
  "narrative": "one paragraph — what a human reviewer should conclude, for our own QA use, not shown to agents",
  "kya_credential": {...},
  "mandate_chain": { "intent": {...}, "cart": {...}, "payment": {...} },
  "transaction_history": [ {...}, ... ]
}
```

`label` and `narrative` are **ground truth for eval only** — real ingested submissions won't carry them; the loader must strip them before a case reaches the pipeline, keeping the labelled corpus separate from what agents actually see.

## 3. The seven scenario labels

One case per label. Each is built so exactly one class of check fails — the point is a clean signal for per-agent precision/recall, not a kitchen-sink case.

| # | Label | What's wrong | Which agent should catch it |
|---|---|---|---|
| 1 | `compliant` | Nothing — full baseline case, clean chain, clean KYA, transaction history in-scope and stable. Doubles as the **clean control** for false-positive testing (concept note §2, Evaluation). | none (negative control) |
| 2 | `mandate_breaching` | Cart/Payment step outside the Intent's declared scope — wrong merchant category, non-approved counterparty, and over the per-order cap, all at once, while the hash chain itself stays intact | Mandate |
| 3 | `broken_chain` | Payment Mandate's `chain_link.prev_mandate_hash` doesn't match the Cart Mandate's actual `signed_payload_hash` — the cart was altered after the payment was built against it | Mandate (chain-integrity check) |
| 4 | `synthetic_identity` | KYA credential issued by an issuer absent from the trust registry, and its delegation chain terminates in another automated account, never a named human | KYA |
| 5 | `structuring` | Mandate scope and chain are both clean; the transaction history shows one intended payment deliberately split into three same-day, same-counterparty transactions each just under the synthetic AML reporting-flag threshold | Log |
| 6 | `drift` | No single transaction breaches the mandate; over ~10 weeks average transaction size, frequency, and counterparty mix all shift steadily away from the agent's own first-month baseline | Drift |
| 7 | `prompt_injection` | A merchant's product-description field carries embedded instructions; the agent's cart `agent_attestation.reasoning` shows it partly complied, adding an unrelated line item outside intent scope | Mandate (semantic subcheck) + injection-heuristic flag |

Case 5's structuring threshold (`SR-STRUCT-01`, ₾3,000) is a **synthetic ruleset parameter invented for this demo** — not a claim about any actual NBG/AML reporting threshold.

## 4. Corpus world (shared across all cases, for coherence)

- **Currency:** GEL (₾) primarily; a couple of cross-border line items in USD where a case's merchant is international.
- **Firms:** seven fictional Georgian fintechs/operators (Mtkvari Retail Group, Kolkheti Facilities Services, Rioni Hospitality Group, Svaneti Import Co, Sameba Trading LLC, Adjara Coastal Logistics, Guria Home & Garden) — one per case, one agent each.
- **Issuer registry** (`data/registry/issuers.json`): NBG Agent Identity Authority (primary), AP2 Global Trust Consortium (recognized), Kavkasia Credential Services (recognized), Svaneti Digital Trust (**revoked** June 2026), Free Agent Identity Co (**not listed** — used by Case 4).
- **Time window:** transaction histories run roughly June–August 2026, ending close to the corpus's authoring date (2026-08-24).

## 5. What this phase does *not* do

Nothing — see §5a for the two spec deltas found once the schema/loader/signing were actually built against the real files.

## 5a. Deltas found when §2 was formalized into code

- **`authorization_scope.counterparty_policy`** (optional string) — not in the §2.2 field table. Present when `allowed_counterparties` is deliberately empty, explaining why (case-006: `"open_within_category — no fixed vendor allowlist; eligibility is governed by merchant category and geographic scope only"`). Added to `schemas/mandate.py::AuthorizationScope` as `str | None = None`.
- **Nested `_*_note` fields** (`_chain_note`, `_kya_note`, `_delegation_note`, `_content_note`) — QA annotations sprinkled at the exact defect location in cases 003/004/006/007, for human readability while authoring. Same purpose as `label`/`narrative` (§2.7) but at field granularity; a real submission never carries them. `data/loader.py` strips any `_`-prefixed key recursively before schema validation, same as it strips `label`/`narrative`. Schemas stay `extra="forbid"` against the true wire format — they do **not** special-case these fields.
- **Real signing** (`scripts/sign_corpus.py`): one Ed25519 keypair per distinct `signer_key_id` (25 across the corpus), public keys in `data/registry/keystore.json`, private keys never persisted (re-run mints fresh keys and re-signs everything — nothing downstream depends on key stability across runs). `signature.value` is now real base64-encoded Ed25519 signature bytes (no more `ed25519-sig-placeholder:` prefix — the `alg` field already names the algorithm). `signed_payload_hash` is a real 64-hex-char SHA-256 of the object's canonical content (`data/canonical.py`: sorted-key, compact-separator JSON). Case 3's payment→cart `chain_link.prev_mandate_hash` is deliberately recomputed as a *stale* hash (what the cart would have hashed to at the payment's authorized amount) after real signing, so the `broken_chain` finding survives — real signing would otherwise make the declared chain link correct by construction.

## 6. File layout

```
data/
  registry/
    issuers.json              # KYA issuer trust list, shared across all cases
  cases/
    case-001-compliant.json
    case-002-mandate-breaching.json
    case-003-broken-chain.json
    case-004-synthetic-identity.json
    case-005-structuring.json
    case-006-drift.json
    case-007-prompt-injection.json
  corpus_manifest.json         # case_id, label, firm, one-line summary — index for the eval harness
```
