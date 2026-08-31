# Phase 5 — KYA Agent

Status: complete. `agents/kya.py`, `agents/kya_checks.py`, `agents/kya_reasoning.py`, `agents/llm.py`, tested (`tests/test_kya_agent.py`).

## 1. Two layers, never merged

**Floor — `KYAAgent.run()`.** All 18 active KYA rules, unconditionally, zero LLM involvement. 6 rule types via `ingestion/verify.py` (Phase 3's credential-scoped crypto/issuer checks, reused not duplicated), 12 via the new `agents/kya_checks.py` dispatch table (issuer trust-level/re-accreditation, credential lifecycle, delegation-chain shape, capability hygiene, consent method). This is what `pipeline/graph.py`'s `kya` node calls — the orchestrator's behavior from Phase 4 is unchanged, just fuller.

**Ceiling — `KYAAgent.review()`.** Floor + a free-text reasoning pass (the agentic layer discussed and scoped down in conversation — see §3) + grounded narration. Optional, needs a live `ANTHROPIC_API_KEY` unless disabled or given a fake client.

The two are structurally incompatible on purpose: floor output is `Finding` (always has `rule_id`, always reproducible, feeds scoring/drafting later); ceiling output is `Observation` (never has `rule_id` or `severity_weight` — there's nothing to weight a hunch by). `KYAReview` carries both but never merges them into one list. See §3.

## 2. The floor found something the original ground truth missed

Running the completed floor against the corpus surfaced a third finding on case-004 (`delegation_terminus_principal_mismatch`, `KYA-DEL-05`) that `data/corpus_manifest.json` didn't originally list — because `KYA-DEL-05` didn't exist yet when that manifest was hand-authored in Phase 1. It's not a false positive: case-004's delegation chain terminates at an agent, not a human, so it necessarily can't match the Intent's human principal either — the same underlying defect, correctly caught twice by two independent rules. The manifest was updated to include it (with a note explaining why), rather than suppressing a real finding to keep a now-outdated ground truth looking clean. `tests/test_pipeline.py`'s two provisional tests (`test_run_case_produces_expected_findings_across_the_corpus`, and the renamed `test_ingestion_findings_are_a_subset_of_agent_findings`, previously `..._agree_today`) were updated accordingly — both were explicitly written in Phase 4 anticipating this exact divergence.

## 3. Why the ceiling only reasons in free text — and what that costs

Conversation landed on the safest of three options after weighing them explicitly: free-text reasoning with no code execution, rather than (a) composing checks from safe primitives, or (b) letting the LLM generate and run arbitrary code. Option (b) was rejected outright — it would contradict CLAUDE.md's "tool access is dispatcher-permissioned, not prompt-instructed" guardrail, submitted to judges specifically as a cyber-risk mitigation, and would open a real code-execution surface on a system pitched to a central bank on its security posture.

The cost of the safe choice: an `Observation` isn't evidence in the same sense a `Finding` is. It can't be scored (PLAN item 11 reads `severity_weight` off a rule — there's none here) and it can't be cited by the drafting agent (item 12) the way a `Finding` can, because "every claim must cite a real finding" only holds for things that trace to a reproducible check. `Observation` is designed to make this limitation visible rather than papered over: no `rule_id` field, no `severity_weight` field, not the same type as `Finding` at all. A future dashboard would need to render these in a visibly different, lower-authority way — "the agent additionally noted, unverified" — not alongside verified findings.

## 4. Loud failure on ruleset/code drift

`run_policy_checks()` raises `NotImplementedError` if an active rule's `type` has no registered checker, rather than silently producing fewer findings than the ruleset claims to enforce. `tests/test_kya_agent.py::test_coverage_gap_raises_loudly_not_silently_skipped` fabricates exactly this situation and confirms it's caught. This matters for when item 14 (draft→active promotion) eventually activates one of the 15 currently-draft KYA rules: if nobody's written a checker for it yet, the system should fail hard, not quietly under-enforce.

## 5. The reference-date decision

`credential_not_expired` and `issuer_reaccreditation_not_stale` both need an "as of" date. Using wall-clock `datetime.now()` was rejected: this is a batch-supervision system meant to be replayable from the ledger (concept note: "every run replayable"), so re-running the same case next month shouldn't produce a different verdict. `build_policy_context()` uses the case's own `Payment.authorized_at` instead — the point in time the submission itself represents.

## 6. LLM plumbing — testable without a live key

`agents/llm.py::get_client()` raises `LLMUnavailable` with a clear message if `ANTHROPIC_API_KEY` isn't set (confirmed: it isn't, in this environment). Every LLM-calling function (`reason_about_case`, `narrate_findings`) takes `client` as a parameter rather than constructing one internally, so `tests/test_kya_agent.py` exercises prompt construction and response parsing against a small duck-typed fake (`_FakeClient`/`_FakeMessages`, keyed by tool name so one fake can stand in for both the reasoning and narration calls within one `review()` run) — no network, no key, still real coverage of the actual code path up to the API boundary. Both calls force `tool_choice` to a specific tool (`record_observations` / `write_narration`) so output is always schema-constrained, never free prose to regex-parse — the same output discipline CLAUDE.md requires for the one place raw firm text reaches an LLM (Mandate's `prompt_playback` subcheck), applied here even though credential data isn't raw firm text.

## 7. What this phase does *not* do

- **No live LLM call has ever been made.** Everything ceiling/narration-related is verified against a fake client. The scaffolding is real and correct up to the network boundary; whether the actual model output is *good* (useful observations, well-written narration) is untested and untestable without a key.
- **`pipeline/graph.py` is unchanged.** The orchestrator still only calls `KYAAgent.run()` (the floor) — `review()`, `Observation`, and narration are not wired into `SupervisionState` or the graph at all. This is deliberate: wiring them in would force every pipeline run to need a live API key, which nothing in Phase 4's skeleton required. Where the ceiling's output actually surfaces (a new state key? a dashboard-only side channel?) is an open question for whenever this gets wired up, not decided here.
- **No fuzzy issuer/holder-name-similarity primitive was built.** That was one candidate ceiling capability discussed but not chosen — the ceiling is free-text reasoning only, no code tools at all (see §3).
- Mandate/Log/Drift agents are untouched — still the same partial/stub state as Phase 4 left them.
