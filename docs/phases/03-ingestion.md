# Phase 3 — Ingestion & Validation

Status: complete. `ingestion/verify.py` + `ingestion/normalize.py`, tested (`tests/test_ingestion.py`).

## 1. Scope, and why it's narrower than "run the KYA ruleset"

PLAN item 3 is four bullets: signature verification against the issuer registry, Cart→Intent/Payment→Cart hash-chain verification, normalization, graceful broken-chain handling. It would have been easy to over-deliver here by just running every active KYA rule during ingestion — but CLAUDE.md draws a real line between ingestion ("deliberately not an agent, since the check is deterministic") and the KYA agent (PLAN item 5, dispatched by the Orchestrator, owns the *full* ruleset including delegation-chain shape, capabilities, consent). Blurring that line now would mean PLAN item 5 either duplicates this code or has nothing left to do.

So ingestion evaluates exactly:

- **KYA domain, credential-scoped only**: `KYA-SIG-01/02/03` (alg/signature/hash on the credential itself), `KYA-DEL-04` (each delegation entry's own signature), `KYA-ISS-01/02` (issuer trust + point-in-time revocation). Everything else active in `registry/rulesets/kya.json` — delegation terminus/depth/duplicates, capabilities, consent, the two re-accreditation/consent-allowlist rules — stays with the future KYA agent.
- **Mandate domain, chain-integrity only**: the two rules in the new `registry/rulesets/mandate.json` (`MND-CHN-01`/`02`). Mandate's scope/cap/counterparty checks and the prompt-playback semantic subcheck are PLAN item 6, not touched here.

`ingestion/verify.py` is written so PLAN item 5/6 can *import* `verify_credential`/`verify_chain_links`/`build_verification_context` rather than re-implement signature math — the KYA and Mandate agents' deterministic cores should be thin wrappers that also evaluate the rules ingestion doesn't, not parallel implementations.

## 2. A new, minimal Mandate ruleset

PLAN item 3 needs chain-hash verification to be rules-as-data too (CLAUDE.md cross-cutting rule 1 isn't KYA-specific). `registry/rulesets/mandate.json` has exactly 2 active rules — `cart_chain_link_matches_intent`, `payment_chain_link_matches_cart` — both `finding_type: "chain_hash_mismatch"`, matching `data/corpus_manifest.json`'s ground truth for case-003 exactly. This is *not* the Mandate agent's ruleset (PLAN item 6 will add scope/cap/counterparty rules to the same file, or a sibling one); it exists only to give ingestion's chain check something to cite instead of hardcoding a finding type as a magic string.

`payment_amount_inconsistent_with_cart` — case-003's *other* expected finding — is deliberately **not** covered here. Amount-vs-cart-total consistency isn't hash-chain verification; it's Mandate's job (item 6). Ingestion catches `chain_hash_mismatch` on case-003 and stops there, by design — case-003 won't show as fully diagnosed until item 6 exists.

## 3. Verifying against the raw file, not the QA-note-stripped view

A real bug this phase surfaced: `_*_note` QA annotations (Phase 1) sit *inside* signed objects in the corpus (e.g. `mandate_chain.payment._chain_note`), and `scripts/sign_corpus.py` signed the raw file content — notes included. `data/loader.py`'s existing loaders strip those notes before schema validation. If ingestion recomputed a canonical hash from the *stripped* view, every note-bearing case (003/004/006/007) would show a false hash/signature mismatch that has nothing to do with the actual defect being tested.

Fix: `data/loader.py::load_raw_case_json()` — the file exactly as written, no stripping, no schema validation — is what `ingestion/verify.py` canonicalizes and signs against. Normalization (`ingestion/normalize.py`) separately calls the existing stripped loader for the pipeline-facing `CaseBundle`. Verification and normalization deliberately read the same file two different ways.

## 4. A real crash found and fixed

`tests/test_ingestion.py::test_tampering_a_credential_signature_produces_a_finding_not_a_crash` — feeding a malformed (non-base64) signature value into the original implementation raised `binascii.Error` instead of producing a Finding, which is precisely the failure mode PLAN item 3's fourth bullet exists to prevent. Fixed by catching `ValueError`/`TypeError` around the base64-decode-then-verify step, not just `cryptography`'s `InvalidSignature`. Kept the test in the suite so this can't silently regress.

## 5. What this phase does *not* do

- No delegation-chain shape checks (terminus/depth/duplicates/terminus-matches-principal), no capability/consent rules, no re-accreditation-freshness check — all stay with the KYA agent (PLAN item 5), even though they're active rules in `registry/rulesets/kya.json` already.
- No Mandate scope/cap/counterparty checks, no prompt-playback semantic subcheck — Mandate agent, PLAN item 6.
- No `payment_amount_inconsistent_with_cart` detection on case-003 — see §2.
- No orchestrator wiring — `ingestion/normalize.py::normalize_case()` is what PLAN item 4's Orchestrator will call per case; nothing calls it yet outside tests.
