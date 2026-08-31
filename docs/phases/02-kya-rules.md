# Phase 2 — KYA Rules

Status: complete. Rule vocabulary (`schemas/ruleset.py`) and the first ruleset (`registry/rulesets/kya.json`) are built and tested (`tests/test_ruleset.py`).

## 1. Scope: what KYA rules are, and aren't

KYA owns credential signature/issuer trust and the delegation chain back to a human (CLAUDE.md). It does **not** own:

- Mandate scope (amounts, counterparties, geography, purpose) — that's the Mandate agent, even though both use the word "scope." KYA checks whether a *credential* attests broad-enough capabilities to exist at all; Mandate checks whether *this specific decision* stayed inside what the Intent actually authorized.
- Velocity/structuring/counterparty-cluster patterns — Log agent.
- Behavioral drift over time — Drift agent.
- Prompt-injection defenses — an ingestion/ Mandate-layer guarantee (deterministic ingestion, injection-heuristic flag), not a per-credential check.
- Consumer disclosure, liability allocation, cross-protocol interoperability — real regulatory-policy concerns, but nothing in a credential or transaction log lets an agent computationally check them. Concept-note material, not registry content.

A broader brainstorm covering all of the above (mirroring the five KYC/AML pillars: identification, verification, mandate/scope, ongoing monitoring, recordkeeping) exists in conversation history; this doc keeps only the KYA-scoped slice that actually became code.

## 2. Rule vocabulary shape

`schemas/ruleset.py`. Each `Rule` is `{rule_id, type, version, status, effective_from, severity_weight, finding_type, description, notes, params}` — flat fields, matching PLAN item 2's "type, params, severity_weight" literally rather than nesting `type` inside `params`.

`type` is a big `Literal` of 23 rule-type strings rather than 23 boilerplate subclasses, because most rule types (17 of 23) take no configurable params at all. The 6 that do (`issuer_min_trust_level`, `credential_not_expired`, `credential_min_validity_window`, `signature_algorithm_allowlist`, `delegation_chain_max_depth`, `capability_vocabulary_allowlist`) get a real typed params model, looked up by `type` and validated by a `model_validator` on `Rule` — `typed_params(rule)` hands back the validated object. `Ruleset` additionally rejects duplicate `rule_id`s.

`severity_weight` (0.0–1.0) is there for PLAN item 11's pure weighted-factor scoring function to consume directly — no scoring logic exists yet, this just makes sure the data it'll need is already shaped right.

`finding_type` is what ties a rule to a `Finding` a KYA agent would eventually emit — chosen to match the corpus's own eval ground truth where it already existed (`issuer_not_in_trust_registry`, `delegation_chain_no_human_terminus` in `data/corpus_manifest.json`), so the ruleset and the labelled corpus agree by construction rather than by coincidence.

## 3. registry/ package

`registry/loader.py`: `load_kya_ruleset()`, `active_rules()`, `rules_by_finding_type()`. Loading only — diff and human-gated draft→active→retired promotion are PLAN item 14 (registry promotion + policy sandbox), deliberately not built here.

## 4. The first ruleset: 18 active, 15 draft

Every **active** rule is checkable against data that already exists (schema fields + `data/registry/issuers.json` + the real Ed25519 signing from Phase 1). Every **draft** rule is a real rule that's blocked on something concrete — a missing firms registry, a missing agent-classification schema field, a missing cross-case key-usage index — recorded in that rule's `notes`, not left as a vague "future work" bucket. This split is itself a demonstration of why the registry needs active/draft/retired status at all: some rules are correctly designed before their supporting data exists.

Params for the data-derived rules (`KYA-CAP-01`'s capability vocabulary, `KYA-CON-01`'s consent-method allowlist, and the corpus's observed issuer trust levels/accreditation dates informing `KYA-ISS-03`/`KYA-ISS-04`) were pulled from actually scanning all 7 case files, not guessed — see `tests/test_ruleset.py`. Three rules (`KYA-ISS-03`, `KYA-ISS-04`, `KYA-CON-01`) are active but currently have "no bite": every value in the corpus already passes them (all issuers `primary`/`recognized`, all recently accredited, every case uses `in_app_biometric` consent). That's intentional — they're there so a future case that *doesn't* fit the pattern has somewhere to land, not dead weight; `tests/test_ruleset.py::test_new_active_rules_have_no_bite_on_the_current_corpus` checks this claim is actually true rather than just asserted.

| Category | Active | Draft | Blocked on |
|---|---|---|---|
| Issuer trust (A) | 4 | 0 | — |
| Credential lifecycle (B) | 3 | 1 | re-issuance history not in corpus (`KYA-CRD-04`) |
| Cryptographic integrity (C) | 3 | 0 | — |
| Delegation chain (D) | 5 | 2 | agent registry (`KYA-DEL-06`), firms registry (`KYA-DEL-07`) |
| Capability hygiene (E) | 2 | 2 | purpose→capability mapping table (`KYA-CAP-03`), re-issuance history (`KYA-CAP-04`) |
| Consent provenance (F) | 1 | 0 | — |
| Structural anomaly | 0 | 2 | corpus-wide/registry-wide index (`KYA-SEC-01`, `KYA-SEC-02`) |
| Operator firm (G) | 0 | 4 | a firms registry doesn't exist yet (`KYA-OPF-01/02/03/04`) |
| Agent identity (H) | 0 | 4 | schema fields for classification/model-version-on-credential, a model-version blocklist registry, and an agent registry ("registration" is currently conflated with "having a credential") (`KYA-AGT-01/02/03/04`) |

## 5. Known limitation: batch supervision, not real-time revocation

`KYA-ISS-02` checks issuer status **as of the credential's `issued_at`** against the registry snapshot available at supervision time — this is correct for catching "issued after revocation," but it is not live revocation checking. This system runs on routine batch submissions, not live rail access (a fixed architecture decision — CLAUDE.md, concept note §2/§4), so a revocation that happens *between* a credential's issuance and when it's actually used only gets caught the next time a case involving that agent is submitted for supervision, not the moment it happens. Worth being explicit about this rather than letting "real-time revocation checking, not a stale list" (a phrase from the broader KYA-standard brainstorm this phase is scoped down from) read as a claim this system doesn't actually make.

## 6. What this phase does *not* do

- No KYA **agent** implementation — this is rules-as-data only. `agents/kya.py` (PLAN item 5) is what actually evaluates a case against these rules and emits `Finding`s.
- No promotion workflow — draft rules stay draft until PLAN item 14 builds draft→active human sign-off.
- No firms registry, no agent-classification schema field, no cross-case key-usage index, no model-version blocklist registry — each draft rule's `notes` says exactly what's missing.
