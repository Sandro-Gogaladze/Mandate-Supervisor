# Phase 4 — Orchestrator + Agent Interface Skeleton

Status: complete. `agents/`, `pipeline/`, tested (`tests/test_agents.py`, `tests/test_pipeline.py`).

## 1. What "skeleton" means here, concretely

PLAN item 4 is scoped to "can at least invoke all four specialists" — not the propose-enforce dispatch or the escalation loop (both PLAN item 9), and not the full Mandate/KYA rule evaluation (PLAN items 5/6) or any Log/Drift logic (items 7/8, which haven't started at all). Two consequences worth being explicit about:

- **Fan-out is fixed, not dynamic.** The graph always invokes all four specialists via plain parallel edges from `ingest`. `Send()` (CLAUDE.md's chosen mechanism for dynamic fan-out) isn't used yet because there's nothing dynamic to fan out over — the set of specialists to run only becomes variable once item 9's LLM-proposed `DispatchPlan` + deterministic floor exists. Using `Send()` now would be machinery with nothing to drive it.
- **KYA/Mandate nodes are partial, not fake.** They're real: `agents/kya.py`/`agents/mandate.py` wrap the exact deterministic checks `ingestion/verify.py` already implements (Phase 3), just re-run against a ruleset the *orchestrator* chooses rather than the ruleset baked in at ingestion time. Log/Drift (`agents/log.py`/`agents/drift.py`) are genuine stubs — no ruleset file, no logic, return `[]` unconditionally — because nothing for those domains exists yet, not because this phase is cutting a corner.

## 2. Why the common contract takes a ruleset as an argument

PLAN item 4's contract is "typed case + ruleset in, `Finding[]` out." The obvious shortcut — have each agent load its own active ruleset internally — would make CLAUDE.md's policy sandbox mode (PLAN item 14: "runs this same pipeline in an isolated environment against an editable, draft copy of the rules registry... only the ruleset changes, never the agents") impossible without touching agent code later. Passing the ruleset in means sandbox mode, when it's built, just calls `KYAAgent().run(case, draft_ruleset)` instead of `KYAAgent().run(case, active_ruleset)` — nothing about the agent changes.

This is also why `ingestion/verify.py` grew two new public functions this phase — `verify_credential_with_ruleset()` / `verify_chain_links_with_ruleset()` — instead of agents calling the existing ingestion-time `VerificationContext` directly, which has the active ruleset's rules baked in at construction. And why `IngestedCase` (Phase 3) grew a `raw` field: an agent re-verifying against a *different* ruleset still needs the raw, unstripped case dict to recompute hashes against, and `normalize_case()` had been discarding it.

## 3. `ingestion_findings` vs. `findings` — two different things, kept visibly separate

`SupervisionState` has both. `ingestion_findings` is what `normalize_case()` already computed during Phase 3's gate check, carried through for inspection. `findings` (the `operator.add`-reduced accumulator) is what the four specialist *nodes* independently produce. They agree on every case today, because the Mandate/KYA nodes currently re-run against the same active rulesets ingestion used — but that's a fact about today's wiring, not a guaranteed invariant, and `tests/test_pipeline.py::test_ingestion_findings_and_agent_findings_agree_today` is named and commented accordingly so a future divergence (e.g. sandbox mode evaluating a draft ruleset) doesn't read as a regression.

Merging them into one list would have been simpler but wrong: it would silently launder "the gate already caught this" and "the dispatched specialist caught this" into one indistinguishable thing, right before item 9 needs that distinction to build escalation logic on top of.

## 4. What this phase does *not* do

- No propose-enforce dispatch, no escalation loop, no `Send()` — PLAN item 9.
- No checkpointer wired up — CLAUDE.md specs a SQLite checkpointer as "disposable resume plumbing," but nothing here needs mid-run resumability yet; `build_graph()` compiles in-memory only.
- No `interrupt()` human gates — PLAN item 13.
- KYA agent still only does what Phase 3's ingestion already did (credential-scoped signature/issuer). Delegation-chain shape, capabilities, consent — all still open, PLAN item 5.
- Mandate agent still only does chain-integrity. Scope/cap/counterparty checks and the LLM semantic subcheck — PLAN item 6.
- Log/Drift agents do nothing at all — PLAN items 7/8.
