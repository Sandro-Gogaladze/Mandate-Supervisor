# Build Plan

Durable, cross-session checklist — update this at the start/end of every chat, since a session's own task list does not carry over to a new one. Order matches how we're actually building it (see `CLAUDE.md` for the full rationale behind each decision referenced here).

Mark items `[x]` as they're finished, and jot a one-line note (file paths, what's left, blockers) so the next chat — even a fresh one with no memory of this one — knows exactly where things stand.

> **Where the build actually is (2026-09-03):** items 1–13 below describe the
> v2 case-based pipeline, which the authorisation reframe superseded. The live
> plan is `docs/migration-plan.md` (read `docs/HANDOFF.md` first). Phases 1–4
> (Facts and Assessments; the dossier through the graph; the four specialists
> migrated; the seven new specialists) are **done** — `docs/phases/14-*.md`
> through `17-*.md`. No test module is parked. The eval (migration-plan
> Phase 10) is skipped for now on explicit direction. **Next: Phase 5** —
> skills registry, dispatcher floor and `Send()` fan-out for all eleven
> agents; until then the triage graph runs the four migrated ones.
>
> **2026-09-03, later:** Phase 5 landed (eight peers, Control Assurance
> sequenced after, all eleven dispatchable, authorisation policy, dossier API,
> console additions). Then: the case room was rebuilt as a Claude-style
> transcript (`dashboard/src/components/CaseChat.tsx`) — user requests on the
> right, one assistant turn per run made of specialist steps, each with the
> model's own working streamed as a collapsible "Thinking" block (the leading
> `reasoning` field every recording tool now requires — this model returns no
> thinking text), verdicts in plain language, briefing and rule results one
> level down; "New chat" hides earlier activity behind a sequence number
> without touching the ledger; the map moved to a collapsible right panel.
> The specialist-progress stream no longer ships facts (8 MB per triage →
> counts and a sequence range), the map keeps measured nodes so they no
> longer vanish mid-run, the per-specialist model-call cap is 900 s (120 s
> timed out Injection and Consent on a 50-run dossier), and Drift degrades a
> malformed verdict to inconclusive instead of raising. 408 tests.
>
> **2026-09-04:** one orchestrator, skills-driven. The separate `dispatch`
> node and the propose-enforce floor are gone (`pipeline/dispatch.py`
> deleted): a first pass and a later question are the same run through one
> review graph (`pipeline/graph.py::build_review_graph`; `run_triage` and
> `run_investigation` remain as callers). The orchestrator (prompt
> `ORCHESTRATOR`, `registry/prompts/orchestrator.json`) is given the request
> — on a first pass a fixed sentence plus the intake statistics — and
> answers by dispatching skills with a briefing each, replying from the
> record, or asking for the report. Coverage on a first pass is asked for by
> the prompt and RECORDED (`DispatchPlan.not_dispatched`), not enforced —
> CLAUDE.md's propose-enforce row no longer describes the code. Control
> Assurance runs after the peers by topology and cannot be dispatched. The
> chat shows the orchestrator's working, the skills it used and its message;
> a specialist's briefing sits in its own "What it was given" drawer; the
> composer is locked until the orchestrator comes back. Every recording tool
> requires a leading `reasoning` field; Log and Consent degrade a malformed
> reply to inconclusive like Drift. 403 tests.
> Later the same day: the orchestrator no longer receives intake statistics
> (completeness is intake's job at submission); tool calls in the console are
> attributed to agents by tool name, not by stream position, and a replayed
> call start is not a new row; the composer greys out while the orchestrator
> is away and carries no status sentences.
> **2026-09-04, prompt caching:** every model call now sends its system
> prompt and its briefing as cache-marked blocks (`agents/llm.py`:
> `system_message()`, `briefing_message()`, `message_text()`,
> `log_cache_usage()`) — one breakpoint after tools+system, one after the
> composed context. A repeat call whose bytes match up to a breakpoint (the
> same dossier reviewed again inside five minutes, a demo re-run, the
> investigator's tool loop, a dev iteration) reads that prefix at ~10% of the
> input price. Verified live: second identical KYA call read 2,902 cached
> tokens, wrote 0. Deliberately unchanged: escalation and reviewer addenda
> still append to the SYSTEM prompt (instructions reach an agent through the
> system turn, evidence through the human turn — those rounds miss the cache
> and that is the right trade), and the orchestrator's payload carries no
> breakpoint (the request and the record change every turn). Caching is
> input-side only and this pipeline's cost is dominated by thinking output;
> see the note in `agents/llm.py`. 410 tests.
> **2026-09-04, deterministic first pass:** the initial comprehensive
> review no longer spends an orchestrator call rediscovering a fixed fan-out.
> `agents/orchestrator.py::first_pass_decision()` selects all eight governed
> review skills in registry order; Control Assurance still follows by graph
> topology. The accepted plan remains ledger-recorded. Later officer requests
> still use the model router. Specialist judgments remain model-backed and
> retain the Anthropic prompt-cache breakpoints above.
> **2026-09-04, failure instances + KYA evidence contract:** the stable
> F1--F73 vocabulary now lives in `registry/failures.json` and every
> implemented rule declares the catalogue failures it detects. A typed
> `FailureOccurrence` is projected from each non-clear rule assessment and
> ledger-recorded with the exact failure name/version, rule/version,
> assessment, facts, evidence refs and affected execution runs; contained
> attempts remain distinct from executed detections. Case/run projections,
> the API and Results panel expose these instances. KYA's canonical context
> is now a typed whole-dossier evidence bundle: full rule inventory, indexed
> outcomes, full breach/gap/measurement facts, relevant regulator records,
> credential series and per-run identity evidence. It deliberately excludes
> ground truth and other specialists' raw domain data.
> Follow-up: the same deterministic `evidence_contract` now wraps Mandate,
> Consent, Provenance, Injection, Counterparty, Log and Drift while preserving
> each prompt's established domain fields. Control Assurance records peer
> breach facts plus declared/executed controls; Systemic records bounded
> portfolio evidence.
> Submitted text inside common facts is delimited before prompting, clean
> results are compressed, and tests prohibit ground truth. Systemic's
> F57/F67/F69 now project to typed portfolio occurrences without inventing a
> per-firm rulebook.
> Correctness audit follow-up: broad judged rules no longer over-project all
> failures in their thematic area (`CPT-IDN-01`, `PRV-REC-01`), and the subject
> agent's own card-integrity check no longer claims F34 (counterparty discovery
> verification, for which the current schema has no evidence). Assessments can
> explicitly narrow a multi-failure rule via `failure_ids`; Injection uses this
> to separate per-run F32 from aggregate F35. Consent and Provenance now receive
> complete per-run domain slices. Log and Drift receive a compact transaction
> index and anomalous verdicts must return valid transaction ids, which are
> projected to exact run refs; missing/invented ids become inconclusive. F65 is
> only projected when a real change-log onset is named. Open Log hunts for
> F62/F63/F64/F66 now produce typed, unscored candidate observations with exact
> transaction/run refs. Systemic F57/F69 occurrences also carry the underlying
> run refs, paired by dossier in `run_refs_by_case`. Injection triage rules no
> longer claim F32 before the judged acted-on-injection result; Control
> Assurance now consumes precise peer assessments as well as deterministic
> peer facts. Tests lock these boundaries.
>
> No streaming, by decision: the orchestrator is one plain model call, the
> console collects a tool call's argument JSON and shows its `reasoning`
> (as "Thought for 12s"), the skills it named and its message once the call
> has ended. The custom `orchestrator_tool_args` event, RAW-event parsing,
> partial-JSON rendering and the per-tool-name dedupe workarounds are gone.
> The API's AG-UI agents no longer echo RAW events and drop the dossier,
> evidence pack, facts, prompts and dispatch contexts from state snapshots —
> one question was sending 30 MB to the browser (18 MB RAW, 12 MB in four
> snapshots) and choking the page.

## 1 · Synthetic data
- [x] Schema spec written by hand — `docs/phases/01-synthetic-data.md`
- [x] Corpus covering all seven scenario labels: compliant, mandate_breaching, broken_chain, synthetic_identity, structuring, drift, prompt_injection — hand-authored in `data/cases/*.json`, indexed in `data/corpus_manifest.json`, shared issuer trust list in `data/registry/issuers.json`
- [x] Pydantic schemas for Intent/Cart/Payment mandates + transaction log — `schemas/` (`common.py`, `mandate.py`, `kya.py`, `transaction.py`, `case.py`), `extra="forbid"` throughout so drift from the wire format fails loud
- [x] Loader/validator — `data/loader.py`: `load_labeled_case()` (eval use), `load_case_for_pipeline()` (strips `label`/`narrative`), `validate_corpus()` (schema + manifest cross-check). Also strips nested `_*_note` QA annotations found in the corpus (not in the original phase-doc spec — added once real files surfaced them; see note below)
- [x] Real Ed25519 signing for every mandate — `scripts/sign_corpus.py`, run once; mints one keypair per `signer_key_id` (25 across the corpus), signs each object's real canonical-content hash, writes public keys to `data/registry/keystore.json`, private keys never persisted. Self-verifies on every run; case-003's chain-hash mismatch is deliberately re-introduced after signing so the `broken_chain` finding survives
- [x] Tests — `tests/test_schemas.py`, `tests/test_loader.py`, `tests/test_signing.py` (15 passing, incl. a tamper test proving a flipped field actually breaks Ed25519 verification, not just placeholder-string comparison)
- Notes: 7 cases, one per label, hand-crafted (not randomized) for narrative coherence and clean per-agent ground truth — see the phase doc for the full design rationale and per-case field guide. Two schema deltas found against real files, not anticipated in the phase doc: `authorization_scope.counterparty_policy` (optional, explains an intentionally-empty allowlist) and nested `_*_note` fields (QA annotations at the exact defect location, stripped by the loader same as `label`/`narrative`). Project scaffolding added: `uv`-managed, Python 3.12, pydantic v2, cryptography, pytest (`pyproject.toml`, `.venv`, `uv.lock`).

## 2 · KYA rules
- [x] Rule vocabulary defined (type, params, severity_weight) — `schemas/ruleset.py`, 33 rule types, typed params for the 8 that take config, flat fields per PLAN wording
- [x] First ruleset JSON — `registry/rulesets/kya.json`, loaded via `registry/loader.py`. 18 active (issuer trust, credential lifecycle, crypto integrity, full delegation-chain family, capability hygiene, consent provenance), 15 draft (each blocked on a specific missing registry/schema piece, recorded in its own `notes` — not built here, see `docs/phases/02-kya-rules.md` §4)
- [x] Tests — `tests/test_ruleset.py` (9 tests, 24 total in suite); confirms both existing KYA ground-truth finding types in `data/corpus_manifest.json` trace to a real active rule, the capability/consent-method allowlists and re-accreditation-freshness rule were derived from scanning the real corpus (not guessed), and that the 3 "no bite yet" active rules genuinely have no bite on the current corpus rather than just claiming to
- Notes: full design brainstorm (mirroring KYC/AML's five pillars, scoped down to what KYA specifically owns vs. Mandate/Log/Drift/registry-governance/concept-note) is in `docs/phases/02-kya-rules.md` §1. Ran a self-audit against both brainstorms after first pass and found real gaps (duplicate-credential-id check, firm-ownership-change rule, re-accreditation freshness, issue-date ordering, consent-method allowlist, batch-vs-real-time revocation caveat) — all now closed, see §4-5 of the phase doc. Next dependency: `agents/kya.py` (section 5) is what actually evaluates a case against this ruleset — nothing evaluates it yet, this is rules-as-data only.

## 3 · Ingestion & validation
- [x] Signature verification against issuer registry — `ingestion/verify.py::verify_credential()`. Credential-scoped only (KYA-SIG-01/02/03, KYA-DEL-04, KYA-ISS-01/02 from `registry/rulesets/kya.json`); delegation-shape/capability/consent rules deliberately left for the KYA agent (item 5) — see `docs/phases/03-ingestion.md` §1
- [x] Cart→Intent and Payment→Cart hash-chain verification — `ingestion/verify.py::verify_chain_links()`, against a new minimal `registry/rulesets/mandate.json` (2 rules, chain-integrity only — Mandate's scope/cap rules are item 6)
- [x] Normalization into internal schema — `ingestion/normalize.py::normalize_case()` / `normalize_corpus()`, returns `IngestedCase{case, findings}`; verifies against the raw (QA-note-including) file since that's what was actually signed, normalizes separately via the existing stripped loader
- [x] Graceful handling of a broken chain (produces a finding, doesn't crash) — new `schemas/finding.py::Finding`. Every check failure becomes a `Finding`, never an exception; a real crash (malformed base64 in a signature raising `binascii.Error`) was found and fixed via `tests/test_ingestion.py`
- [x] Tests — `tests/test_ingestion.py` (9 tests, 33 total in suite); confirms exact expected findings per case (case-003 → 1 mandate finding, case-004 → 1 kya finding, everything else clean), tamper tests for both signature and chain-link corruption, and an unknown-signer-key case that must fail gracefully rather than `KeyError`
- Notes: `payment_amount_inconsistent_with_cart` (case-003's *other* expected finding) is intentionally not caught here — it's value-consistency, not hash-chain integrity, and belongs to Mandate agent (item 6). Full design + scope boundary in `docs/phases/03-ingestion.md`. Next dependency: PLAN item 4 (orchestrator) is what actually calls `normalize_case()` per submission — nothing does yet outside tests.

## 4 · Orchestrator + agent interface skeleton
- [x] Common agent contract: typed case + ruleset in, `Finding[]` out — `agents/base.py::SpecialistAgent` Protocol. Ruleset passed in (not loaded internally by each agent) specifically so policy sandbox mode (item 14) can later swap in a draft ruleset without touching agent code — see `docs/phases/04-orchestrator-skeleton.md` §2
- [x] LangGraph state shape defined — `pipeline/state.py::SupervisionState`. `ingestion_findings` (Phase 3's gate check) kept separate from `findings` (the `operator.add`-reduced specialist-node output) — same list today, not guaranteed to stay that way, see phase doc §3
- [x] First-pass orchestrator (can at least invoke all four specialists) — `pipeline/graph.py::build_graph()`/`run_case()`. Fixed fan-out (plain parallel edges, all four always run) since nothing dynamic exists yet to justify `Send()` — that's item 9. `agents/kya.py`/`agents/mandate.py` are partial (wrap Phase 3's ingestion checks, now ruleset-swappable); `agents/log.py`/`agents/drift.py` are true stubs, return `[]`
- [x] Tests — `tests/test_agents.py` (6), `tests/test_pipeline.py` (6), 45 total in suite. Confirms the graph's actual compiled node set (`get_graph().nodes`) is all five nodes, not just that it runs without error
- Notes: `langgraph>=1.2.11` added as a dependency. Full design reasoning (why ruleset-swappable, why two separate finding lists, what "skeleton" deliberately excludes) in `docs/phases/04-orchestrator-skeleton.md`. Next dependency: PLAN item 5 (KYA agent) and item 6 (Mandate agent) extend `agents/kya.py`/`agents/mandate.py` in place rather than replace them; items 7/8 replace the Log/Drift stubs entirely once a ruleset exists for each domain.

## 5 · KYA agent
- [x] Deterministic checks implemented, tested against corpus — `agents/kya.py::KYAAgent.run()`, all 18 active KYA rules (6 crypto via `ingestion/verify.py` + 12 new policy checks in `agents/kya_checks.py`). Matches full corpus ground truth exactly (case-004 → 3 findings, everything else clean) — ground truth itself updated, see notes
- [x] Agentic ceiling (beyond the plan's original scope, added per conversation) — `agents/kya.py::KYAAgent.review()`: free-text reasoning (`agents/kya_reasoning.py::reason_about_case()`, produces `Observation`, never merged with `Finding`) + grounded narration (`narrate_findings()`). Needs a live `ANTHROPIC_API_KEY` (not set in this environment) unless a fake client is injected — `agents/llm.py::get_client()` raises `LLMUnavailable` clearly rather than a bare auth error
- [x] Tests — `tests/test_kya_agent.py` (10 tests, 55 total in suite). Includes a coverage-gap test (fabricates an active rule with no checker, confirms `NotImplementedError` not a silent skip) and full reasoning/narration mocking via a fake Anthropic client — no live LLM call has ever actually been made, see `docs/phases/05-kya-agent.md` §7
- Notes: completing the floor surfaced a finding (`delegation_terminus_principal_mismatch`, `KYA-DEL-05`) on case-004 that predates the rule and wasn't in the original hand-authored `data/corpus_manifest.json` — added to the manifest as genuine ground truth, not suppressed; `tests/test_pipeline.py`'s two provisional Phase-4 tests updated accordingly (the "ingestion findings == agent findings" test is now correctly "ingestion findings ⊆ agent findings", exactly the divergence that test's docstring anticipated). `pipeline/graph.py` deliberately untouched — orchestrator still only calls the floor (`run()`), not `review()`; wiring the ceiling into `SupervisionState` is an open question, not decided here. Full design reasoning, including why free-text-only was chosen over two riskier ceiling designs, in `docs/phases/05-kya-agent.md`.

## 6 · Mandate agent
- [x] Deterministic core (scope/cap/chain-integrity) — `agents/mandate.py::MandateAgent.run()`, 10 new active rules (`agents/mandate_checks.py`, including the deterministic injection heuristic `MND-SEM-02`) + the 2 chain rules from Phase 3. Matches full corpus ground truth (case-002 → 3 findings, case-003 → 2, case-007 → 2, everything else clean)
- [x] LLM semantic subcheck (prompt_playback vs. Cart), delimited + schema-constrained + heuristic-flagged — `agents/mandate_reasoning.py::check_cart_reasoning_matches_intent()`, `MND-SEM-01` promoted to active. Only reachable via `MandateAgent.review()`, merged into the same `Finding` list `run()` produces (unlike KYA's separate `Observation` type — see `docs/phases/06-mandate-agent.md` §7 for why that's the right call here, not an inconsistency). Verified **live** against the real API: case-007 now produces all three of its expected findings exactly, case-001 stays clean
- [x] Tests — `tests/test_mandate_agent.py` (6), `tests/test_mandate_reasoning.py` (8), 70 total in suite. Includes a test locking the "month" interpretation of `max_cumulative_amount` to case-001's own reasoning text (₾1,748.10, matched to the cent), the same coverage-gap discipline as KYA, and full prompt/response mocking for the LLM subcheck (delimiter markers, thinking config, draft-rule skip, disabled-flag skip)
- Notes: two ground-truth corrections in `data/corpus_manifest.json`: case-007's `category_out_of_scope` was wrong (the smuggled item is legitimately within the cart's merchant MCC — corrected to `cart_reasoning_semantic_mismatch`, which the semantic subcheck now actually produces). Documented: `MND-CAP-01` (per-transaction cap) incidentally catches part of case-007's injection attack already, as a pure numeric side effect, independent of both the heuristic and the semantic check — three independent signals converge on the same case. `MND-CAP-04` (geographic scope) stays draft — real schema gap (`Merchant` has no region field). Shared LLM plumbing (`ModelDidNotCallTool`, `extract_tool_input()`) moved from `agents/kya_reasoning.py` into `agents/llm.py` this phase so `agents/mandate_reasoning.py` could use it without an awkward kya→mandate import. Full design reasoning in `docs/phases/06-mandate-agent.md`.

## 7 · Log agent
- [x] Structuring detector, counterparty concentration, thresholds from ruleset — `agents/log.py::LogAgent`. **Revised twice**: first pass gave structuring a hardcoded deterministic rule; per explicit direction ("no deterministic part, it should do everything on its own"), that was removed — all three rules (`LOG-STR-01`/`LOG-CON-01`/`LOG-VEL-01`) are now LLM-judged in one call (`agents/log_reasoning.py`), given real pandas-computed evidence (`agents/log_stats.py`: candidate clusters, per-counterparty breakdown, velocity/amount stats) but no pre-decided verdict. Concentration judged relative to the mandate's own approved-counterparty count, not an absolute % (case-003/007 both show legitimate high concentration — confirmed no false positive, live)
- [x] High-thinking-effort, well-instructed LLM anomaly pass, per explicit direction — full taxonomy + grounding requirements in `agents/log_reasoning.py::SYSTEM_PROMPT` (quoted in full in `docs/phases/07-log-agent.md` §2). Open-ended findings beyond the three named categories surface as `Observation` (unscored, shared type moved out of `agents/kya_reasoning.py` into `schemas/observation.py` this phase)
- [x] Tests — `tests/test_log_agent.py` (5, now covers `log_stats.py` + confirms `run()` is a no-op), `tests/test_log_reasoning.py` (10), 85 total in suite. Structuring cluster math (the evidence handed to the model, not a verdict anymore) verified against case-005's exact numbers
- Notes: `run()` (called by the orchestrator) is now a true no-op for Log, same shape as Drift's stub — all real analysis only reachable via `review()`, same pattern already established for KYA's ceiling and Mandate's semantic subcheck. Found and resolved a real dispatch-floor tension — CLAUDE.md's stated "Log+Drift run when history ≥ 30 tx" would starve Log of case-005 (only 16 tx), its own purpose-built test case; the 30-tx floor fits Drift's need for baseline volume, not Log's structuring check — split the floor per-agent, recorded for PLAN item 9 to implement. Verified live (not just mocked), both before and after the revision: case-002's concentration judgment independently corroborated Mandate's `counterparty_not_approved` finding through a completely different mechanism with no cross-agent knowledge fed in; case-007's outlier observation independently flagged the same injected transaction Mandate's cap/heuristic/semantic checks already caught; case-005's live structuring judgment explicitly reasoned about the cluster relative to the account's own mean/std, going beyond what the deleted hardcoded rule ever produced. Full design reasoning in `docs/phases/07-log-agent.md`.

## 8 · Drift agent
- [x] Baseline window, PSI + z-scores, `insufficient_baseline` under 30 tx — `agents/drift.py::DriftAgent`. Built entirely LLM-judged from the start (per the same direction as Log's revision): `agents/drift_stats.py` computes real PSI/z-score/frequency statistics (baseline vs. comparison window split), but no Python threshold decides whether a shift counts as drift — `agents/drift_reasoning.py`'s model call does, given the real numbers as evidence. `insufficient_baseline` (<30 total tx) is the one prerequisite kept outside the model — a row count, not a behavioral judgment — confirmed live on case-001 (24 tx) and case-007 (7 tx)
- [x] Tests — `tests/test_drift_agent.py` (5), `tests/test_drift_reasoning.py` (8), 98 total in suite. PSI/z-score math verified against case-006's exact numbers (baseline mean ₾187.95 → comparison ₾316.51, z=7.15, counterparty PSI 5.86, MCC PSI 2.02) before being trusted
- Notes: this is where CLAUDE.md's "Log+Drift run when history ≥ 30 tx" dispatch floor actually fits — Drift genuinely needs baseline volume, unlike Log's structuring check (see PLAN item 7 notes on the floor split). `run()` (orchestrator-called) is a true no-op, same as Log — all real analysis only via `review()`. Verified live: case-006 produced a well-synthesized finding reasoning across all four signals together, plus two genuinely useful open observations pointing at cross-agent concerns with zero cross-agent context fed in — a new dominant counterparty worth a KYA look, and a new MCC (vehicle maintenance) falling outside the mandate's declared `fleet_fuel_logistics` purpose, a potential Mandate-scope issue the model caught on its own. Full design reasoning in `docs/phases/08-drift-agent.md`.

## 9 · Orchestrating: dispatch + escalation loop
- [x] Propose–enforce dispatch (LLM plan + deterministic floor validator) — `pipeline/dispatch.py`. `enforce_floor()` can only turn a proposed `False` into `True`, never the reverse. Resolves the Log-vs-Drift floor-split tension flagged in both their phase docs: Log's floor is just non-empty history, Drift's reads its own ruleset param (30) rather than duplicating that number — verified live, the model independently reasoned to the same conclusion on a low-tx case
- [x] Dynamic fan-out via conditional edges returning a list of node names — **not literally `Send()`**, noting the deviation honestly: the branch set here is a subset of 4 *fixed* nodes (not a dynamically-generated list of arbitrary items), which `add_conditional_edges` returning `list[str]` handles correctly and more simply; `Send()` would be the right tool for fanning out over an arbitrary generated list, which this isn't. See `docs/phases/09-dispatch-and-escalation.md` §5 if `Send()` is specifically wanted later.
- [x] Escalation loop, capped at 1 extra round — `pipeline/escalation.py` + `pipeline/graph.py`'s `bump_round`/`escalate_check` nodes. Trigger is any unresolved `Observation`; target agent is the observation's own agent by default, or a different named agent if the note references one (regex word-boundary match, not another LLM call). Verified live: Drift's cross-agent observation about a new counterparty correctly escalated to KYA, not Drift itself
- [x] Tests — `tests/test_dispatch.py` (5), `tests/test_escalation.py` (7), `tests/test_pipeline.py` rewritten (8, graph-level integration against one comprehensive fake client covering all 6 tool names in the graph — dispatch, KYA reasoning+narration, Log, Drift, Mandate semantic check). 113 total in suite, runs in ~1.2s with zero live calls
- Notes: every specialist node now calls `.review()` not `.run()` — the orchestrator's default path needs a live key from this phase on, a real behavior change from Phase 4's key-free skeleton. Escalation-round nodes discard `findings` from the second `review()` call and keep only `observations`, to avoid duplicating round-0's deterministic findings without needing a dedup-aware reducer — the real, stated cost is that escalation can never flip a named-rule verdict (e.g. Log's velocity check going from false to true), only narrow/resolve the observation list; documented as a genuine design boundary in `docs/phases/09-dispatch-and-escalation.md` §4, not swept under "revised." A real routing bug (`_route_after_specialists` returning specialist names directly instead of routing through `bump_round` first) was caught immediately by the test suite before this was ever run live — see phase doc §6. First test run of this phase accidentally made live, paid API calls on every `pytest` invocation (no injectable client yet) — fixed by adding `client=` to `build_graph()`, threaded through as closures.

## 10 · UI/UX: live multi-agent view + product shell
- [x] React + Vite + Tailwind + shadcn/ui app shell — `dashboard/`
- [x] React Flow pipeline graph fed by `get_graph()` — `dashboard/src/components/PipelineGraph.tsx`, backed by `api/main.py`'s `/graph`
- [x] CopilotKit/AG-UI integration via hooks (not default chat widgets) — `dashboard/src/components/CaseReview.tsx`; `useCoAgent` for state/running, `agent.subscribe(...)` (not `useCoAgentStateRender`/`useCopilotAction` — see notes) for the live step feed
- Notes: Required rewriting every agent module + `pipeline/graph.py` from the raw `anthropic` SDK to `langchain_anthropic.ChatAnthropic`/async first (CLAUDE.md's live-streaming spec needs `astream_events`, which only instruments the async path) — all 113 existing tests ported to `async def`, one shared `FakeChatModel` (`tests/fakes.py`) replacing five per-file fakes. Three tiers: FastAPI (`api/main.py`, `ag_ui_langgraph`, raw AG-UI SSE at `/agent`) → a ~30-line Node CopilotKit Runtime (`dashboard/server/copilot-runtime.js`, the one non-Python piece, pure protocol translation) → React. Found and fixed 5 real third-party bugs across the CopilotKit/ag-ui stack (Python `clone()` version mismatch, Express route double-mounting hit twice, `useCoAgent().run()` losing its `this` binding, `useCoAgent`'s `initialState` never reaching the first request, root+`/v2` import mixing crashing React) — full detail in `docs/phases/10-ui.md` §4. `useCoAgentStateRender`/`useCopilotAction('*')` only ever fired for runs started through `useCoAgent`'s own (broken) `run()`, so the live feed uses `agent.subscribe({onStepStartedEvent, onToolCallArgsEvent, ...})` directly instead — same underlying AG-UI client, still headless/no chat widget, just not those exact two hook names. Verified live in-browser on two cases including a real escalation-loop run (case-001, round 1 triggered and completed) — zero console errors. Not done: human-approval gate (needs item 13), risk scoring in the UI (item 11), ledger-backed case history (item 15), registry/sandbox UI (item 14), automated frontend tests.

Follow-up design pass (icons/color per agent via `lib/node-meta.tsx` + `lib/scenario-meta.tsx`, indigo accent theme, panel headers, auto-scrolling step feed) surfaced two more real, reproducible bugs, both now fixed — full detail in `docs/phases/10-ui.md` §8: (1) a single malformed LLM tool-call element (`kya_reasoning.py`'s `observations` array — `tool_choice` is `"auto"`, not forced, so schema adherence isn't guaranteed) crashed the graph node → the FastAPI stream → and took the entire Node CopilotKit runtime process down on an unhandled promise rejection, breaking every case review until manually restarted; fixed with a shared `agents/llm.py::parse_observations()` (skips + logs a malformed element instead of crashing, now used by KYA/Log/Drift, covered by new `tests/test_llm.py`) and `process.on('unhandledRejection'/'uncaughtException')` hardening in `copilot-runtime.js`. (2) A React Flow node could get stuck showing "active" after a run finished (traced to LangGraph's retry-on-transient-error policy not always surviving 3 hops of SSE relaying) — fixed by deriving displayed node status from `running` on every render instead of trusting every event arrived. Also fixed a real layout overlap below the `lg:` breakpoint (stacked cards' height floors summed past the viewport). Flagged, not fixed: `log_reasoning.py`/`drift_reasoning.py`/`kya_reasoning.py::narrate_findings`/`mandate_reasoning.py` still do unguarded single-object LLM-output indexing (lower risk than the array case — one bad response only breaks that one case, not fixed live) — `pipeline/dispatch.py`'s `DispatchPlan.model_validate(result)` is the safer pattern to convert them to.

Second design pass, on explicit direction to install and actually use three skills (`frontend-design`, `shadcn`, CopilotKit's AG-UI bundle — `.claude/skills/`, `npx skills add`) and to fix "the pipeline isn't visible" and "how does a user submit a new case" — full detail in `docs/phases/10-ui.md` §9. Replaced the indigo theme with a deliberately-chosen "ink + paper + brass seal" regulatory-terminal palette (Space Grotesk headings, IBM Plex Mono data) instead of a generic default, per `frontend-design`'s own warning against exactly that. Made the pipeline graph the hero: bigger brand-tinted nodes, full-width top row (`lg:flex-[3]`) instead of an even three-way split. Added real case submission — `data/uploads.py` (new), `POST /cases/upload`, `UploadCaseDialog.tsx` — validated against the same `CaseBundle` schema ingestion enforces, merged into `/cases` alongside the corpus with no pipeline-side special-casing; a submitted case has no eval-only label, shown as "awaiting review" instead of a scenario badge. Live verification of the upload path caught two more real bugs, both fixed with tests: reusing an existing sample case file (the dialog's own suggested workflow) failed on internal QA-only fields the corpus strips but uploads didn't (now shared via `data.loader.strip_qa_notes`); and a duplicate-`finding_id` React key warning traced back to the same node-retry behavior from the prior pass, fixed properly at the state layer (`pipeline/state.py`'s `findings`/`observations` now use a dedup-aware reducer instead of plain `operator.add` — the right invariant to land before item 15's ledger builds on top of this accumulation pattern).

Third pass ("too plain, homepage shouldn't be the queue, review page should be better") restructured the app into a real console — full detail in `docs/phases/10-ui.md` §10: collapsible dark-ink sidebar shell (`AppSidebar.tsx`, shadcn `sidebar`; Console nav with live queue-count badge, informational specialist roster in agent colors, a case-officer chip whose status dot is a real `/health` ping), a proper Overview homepage (`Overview.tsx`: dot-grid hero + brass eyebrow, live stat row computed from `/cases`, "review bench" specialist cards sharing new `blurb`s on `NODE_META`, "Next up" preview rows), and a `Live review / Case file` tab pair on the review page — `CaseFilePanel.tsx` renders `/cases/{id}` as a supervisory dossier (the principal's `natural_language_intent` quoted as the lead, authorization scope with caps + counterparty chips, credential with a color-coded delegation chain, Intent→Cart→Payment cards, full transaction table). Verified live: run started, tab switched mid-run and back, run continued (state lives above the Tabs) and completed 5 findings · 5 observations, zero console errors; 132 backend tests + `tsc` clean.

Fourth pass: installed `pbakaus/impeccable` (`.claude/skills/impeccable`, the full plugin skill: SKILL.md + 23-command reference set + a 59-rule mechanical detector) on explicit direction to cut "AI slop," and ran it by its own book — `context.mjs` setup, `craft-floor.md` + `operate.md` loaded before editing, detector run once at the end. Its Refuse list caught five real defaults in our UI, all fixed: the hero's eyebrow/kicker (a ban — deleted, NBG identity folded into the copy), the review-bench same-size icon-card grid (now a dense roster list with hairline dividers), 4px colored severity bars on queue cards/Next-up rows and the case-file quote card's `border-l-4` (badges/tint carry the signal now), the hero's decorative blur blob (deleted), and unthemed browser surfaces (added `::selection`, brand scrollbars, caret/accent-color, `tabular-nums` on tables and mono — craft-floor's "cheapest signal a page was built rather than assembled"). Also swapped the step feed's `animate-bounce` loader dots for staggered pulse after the mechanical detector flagged bounce easing — detector now returns clean on `dashboard/src`.

Fifth pass: pulled `VoltAgent/awesome-design-md` (73 reverse-engineered brand DESIGN.md files) — not a skill, a reference corpus. Installed the four relevant systems (Stripe, Linear, Vercel, Wise) as `docs/design-references/` — deliberately NOT at project root, where a foreign brand's DESIGN.md would hijack this product's identity (impeccable: "refinement preserves; redesign replaces"). Instead ran impeccable's `document` command properly: wrote this project's own root `DESIGN.md` (spec-compliant frontmatter tokens from the real index.css values + the eight canonical sections), codifying the committed world plus two reference-mined upgrades applied in the same pass — a navy-tinted layered elevation system (Stripe's move: shadows tint from the ink hue, never gray-black; implemented as Tailwind v4 `--shadow-*` theme tokens so every existing `shadow-*` utility upgraded in one spot) and a 1px translate press state on all buttons (state feedback, not scale bounce). Detector clean over `dashboard/src` + `DESIGN.md`; `context.mjs` now resolves `designPath: DESIGN.md` as visual authority. PRODUCT.md (impeccable `init` interview) offered, not run.

Sixth pass: full impeccable `critique` run by its book (two isolated sub-agents — a design reviewer with live browser measurement, a detector-evidence agent — synthesized per spec, snapshot persisted to `.impeccable/critique/`, baseline 25/40, verdict "Specific"). User chose the full five-issue fix round + two directional answers; all landed and live-verified (`docs/phases/10-ui.md` §11): **(P0)** queue cards became real `<button>`s — keyboard path + focus ring (page went 2 → 13 focusables); **(P1)** the human gate now commands attention — auto scroll-into-view on arrival + the header button becomes an enabled "Review decision" anchor while holding (was a disabled dead end); **(P1)** pipeline graph got wheel zoom + on-brand zoom/fit controls (kept the wide layout per user choice; found and fixed a real React Flow v12 trap — `fitView()` only queues, consumed by the next node change that a fully-static graph never produces; `fitBounds(getNodesBounds(getNodes()))` sets the viewport directly); **(P1)** CopilotKit's floating `cpk-web-inspector` bubble stripped — the v1-compat wrapper ignores `showDevConsole` for it, the real switch is `enableInspector={false}` (read from the bundled source); **(P1)** the two irreversible moments got ceremony — re-run over existing results asks first (dialog naming the case), the gate restates what's being decided (score · tier · findings count · case id strip), and approve/reject produce receipts (toast + persistent signed-by strip in the report panel; a rejected report says so in place). Per user's answers: seeded ground-truth labels retreated to the Case file tab only ("corpus ground truth" metadata row — queue/overview/review-header are verdict-free so the run is a discovery, not a confirmation), and the gate keeps name-typing as deliberate ceremony. Adjacent minors in touched files: step feed auto-scroll scoped to its own viewport (was dragging the page scroller every event), decision record survives a blocked draft, `aria-pressed` on rerun chips, risk score set in mono per DESIGN.md, queue API failure got a human message + Retry. Detector still clean; tsc clean; verified live end-to-end (run → gate → approve → receipts → re-run confirm).

## 11 · Risk scoring
- [x] Pure weighted-factor function, disposition tiers from config — `pipeline/scoring.py::score_findings()` (sums finding `severity_weight`s per agent + total; Observations excluded *by signature*, not convention), tiers in versioned `registry/scoring.json` via `load_scoring_config()`. A `risk_score` graph node recomputes on every pass through the tail (a reviewer-directed re-analysis can change findings) and feeds the drafting payload — prompt rule 6 makes the report state the tier verbatim, never its own severity arithmetic. `ScoreCard` (tier badge + per-agent factor bars) tops the results panel. 7 unit tests + a graph-level self-consistency assertion. Verified live: case-002 → 3.60 · ESCALATE, report lede opened with it. Full detail in `docs/phases/11-risk-scoring.md`.

## 12 · Report drafting + grounding check
- [x] Drafting node (structured findings only, inline citations) — `agents/drafting.py` + `schemas/report.py`; sections carry `cited_finding_ids`, payload is the structured record only (no raw firm text — key set pinned by test), graph routes `escalate_check`/`bump_round`'s settled exits into a `draft_report` → `grounding_check` tail (`pipeline/graph.py`)
- [x] Grounding validator + regenerate-then-block loop — `agents/grounding.py`, pure Python (no LLM judging an LLM): invented citations, uncited sections, silently-dropped findings, sections-on-a-clean-case, and mishandled observations all fail; validator complaints feed the retry prompt verbatim. Capped at 2 regenerations per CLAUDE.md (its "capped at 2" wins over this file's earlier "regenerate-once" wording), then `report_blocked` — UI withholds the prose entirely, findings stay authoritative
- Notes: done out of order (before item 11, on explicit direction) — the report deliberately states no risk score/tier; scoring slots in later as one more structured input line. `tests/fakes.py` gained callable responses so the pipeline fake draftsman can cite the finding_ids each case actually produces (a static dict can't be grounded for every case). UI: full-width "Supervisory report" card on the review page (`ReportPanel.tsx`) with citation chips, labeled unverified-observations box, grounded/regenerating/blocked status; review tab now scrolls as a normal page. 148 tests. Verified live: case-002 grounded first-try, all 5 findings cited, observations quarantined; blocked path exercised in tests (3 draft calls exactly). Full detail in `docs/phases/12-drafting-grounding.md`.

## 13 · Human review gate
- [x] `interrupt()` at draft-to-send — `human_gate` node after grounding passes; the checkpointer freezes the run and the graph structurally cannot issue anything without a resume. Blocked reports never reach the gate (nothing approvable). The gate node loops on `interrupt()` for invalid payloads / cap-violating reruns — re-interrupts with an `error` field instead of crashing.
- [x] API resolves it from a named reviewer's decision — same AG-UI pipe as everything else, no bespoke endpoint: `emit_interrupt_outcome=True` on the LangGraphAgent terminates the SSE stream with the structured interrupt outcome; the client resumes via `RunAgentInput.resume[]` (`agent.runAgent({resume})`), verified present in both installed SDKs before building. `ReviewerDecision` is typed + named, `decided_at` stamped server-side, decisions accumulate in state (the artifact item 15's ledger will anchor).
- [x] Human-in-the-loop component wired to it — `ReviewGate.tsx` (approve & issue / reject / send-back-with-instructions: textarea + agent target chips, round N of 3, cap notice, server error surfacing) + decision record timeline in `ReportPanel.tsx` (`issued ✓`/`rejected` status).
- Notes: built with the **directed re-analysis loop** folded in (per explicit direction): a `rerun` decision carries a `ReviewerDirective` (instructions + explicit target agents) that fans back out to exactly the named specialists via `REVIEWER_ADDENDUM` (regulator-authored trusted input — the only free text that ever reaches specialist prompts), then score → draft → grounding → gate re-run. A directed pass MAY produce new findings — safe because of the dedup reducer (identical ids drop, changed judgments arrive under new ids); mandate is human-targetable despite never being a machine escalation target. Capped at 3 rounds as belt-and-braces — the human is the real loop bound. `run_case()` now compiles with a per-call MemorySaver and returns at the gate (`__interrupt__` in state). 7 gate tests (pause/approve/reject/rerun/invalid-payload/cap); 161 total. Verified live end-to-end: run → gate held → send-back to Log with a threshold-avoidance question → directed pass + tail re-ran → gate round 1 → approved with comment → issued ✓, both decisions named + timestamped on the record; zero console errors. Full detail in `docs/phases/13-human-gate.md`.

## 14 · Registry promotion + policy sandbox
- [ ] Draft/active/retired versioning, human-gated promotion
- [ ] Sandbox pipeline pointed at draft ruleset, isolated results, diff vs. active
- Notes:

## 15 · The case ledger
- [ ] SQLite append-only events table, hash chain, triggers
- [ ] `verify()` CLI + JSONL export
- [ ] Wired into every already-built agent/node (additive, not a rewrite)
- Notes:

## 16 · Evaluation harness
- [ ] Per-agent precision/recall against labelled corpus
- [ ] False-positive rate on clean control case
- [ ] Adversarial grounding test
- [ ] Injection-context assertion test
- Notes:

## 17 · Deployment & demo rehearsal
- [ ] docker-compose local profile + `make demo`
- [ ] Fly.io mirror, reseeded on boot
- [ ] Five-beat demo script rehearsed from cold start
- Notes:
