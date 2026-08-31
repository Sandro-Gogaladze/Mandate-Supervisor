# Phase 9 — Dispatch + Escalation Loop

Status: complete. `pipeline/dispatch.py`, `pipeline/escalation.py`, `pipeline/graph.py` (rewritten), tested (`tests/test_dispatch.py`, `tests/test_escalation.py`, `tests/test_pipeline.py`). Verified live.

## 1. Two mechanisms, one PLAN item

**Dispatch** replaces Phase 4's "always run all four" with real judgment: `pipeline/dispatch.py::propose_dispatch_plan()` (one LLM call) proposes a `DispatchPlan`; `enforce_floor()` (pure Python) can only ever turn a proposed `False` into `True`, never the reverse — the LLM cannot skip a mandatory specialist. Mandate and KYA are forced unconditionally; Log/Drift are forced only above their own minimum.

**Escalation** re-dispatches a specialist when its `review()` produced an unresolved `Observation` — capped at exactly one extra round (`_MAX_ESCALATION_ROUNDS = 1` in `pipeline/graph.py`).

## 2. Resolving the floor-split tension (Log vs. Drift)

Both Log's and Drift's phase docs flagged this: CLAUDE.md's single stated "Log+Drift run when history ≥ 30 tx" bundles two agents with genuinely different minimums. `enforce_floor()` resolves it by reading each agent's own real threshold instead of hardcoding one number:

- **Log's floor is `tx_count > 0`** — structuring can validly fire on a handful of transactions (case-005's own defect is 3 transactions).
- **Drift's floor is `tx_count >= min_total_transactions`**, read from `DRIFT-BHV-01`'s own ruleset param (default 30) — the *same* value `DriftAgent.review()`'s internal `insufficient_baseline` gate already uses, not a second hardcoded copy of it.

Verified live: case-007 (7 tx) — the model itself reasoned "with only 7 data points, there isn't enough history to reliably characterize a 'normal' baseline... recommend running Log but skipping Drift," independently arriving at the same conclusion the floor's design was built around.

## 3. Escalation's actual trigger and scope

The trigger is exactly "a specialist produced an `Observation`" — that's the whole reason `Observation` exists as a separate, lower-confidence type (Phase 5). `pipeline/escalation.py::target_agent_for()` decides *which* agent re-examines it: the observation's own agent by default, or a different named agent if the note explicitly mentions one — a plain regex word-boundary match, not another LLM classification call, kept deliberately simple and bounded (see that module's docstring for why).

This is the concrete mechanism that closes the gap flagged as "not automated" in `docs/phases/08-drift-agent.md` §5: Drift's live run there produced an observation reading *"this new counterparty... warrants a specific KYA/counterparty verification check"* — with escalation wired up, that sentence now actually does something. Verified live on case-006: Drift's counterparty observation escalated to KYA, and KYA's round-2 output explicitly addressed it ("MER-BEF-005 is a counterparty with zero presence in the baseline mix...").

## 4. Why an escalation round only ever adds to `observations`, never `findings`

A re-dispatched specialist's `review()` internally still calls `run()` first (its full deterministic floor) — calling it a second time would re-emit the exact same deterministic `Finding`s from round 0 a second time, duplicating them in the `operator.add`-reduced state list. Rather than build a dedup-aware reducer, the escalation-round node functions (`pipeline/graph.py`) simply discard the `findings` half of the second `review()` call and keep only `observations`. This has a real, honest consequence worth stating plainly: **an escalation round can never itself produce a new scored `Finding`** — for KYA this was already true by construction (its ceiling has no rule to promote into); for Log/Drift, whose named categories (structuring/concentration/velocity/drift) *are* real rules, this means a round-0 "not anomalous" verdict on one of those categories cannot be flipped to "anomalous" on escalation even if the model's second look would have judged it differently. Escalation only ever narrows or sharpens the `Observation` list. If a future phase wants escalation to be able to flip a named verdict, that needs the dedup-aware reducer this phase deliberately avoided building — noted here as a real design boundary, not silently swept under the "revised" language elsewhere in these docs.

## 5. `run()` vs. `review()` — the graph now needs a live key

Every specialist node in `pipeline/graph.py` calls `.review()`, not `.run()` — this is the real behavior change from Phase 4. Dispatch itself is one more LLM call before any specialist even runs. `build_graph(client=...)` accepts an injectable client specifically so the test suite (`tests/test_pipeline.py`) never makes a live call — the first version of this phase's tests didn't do this and ended up making 5+ real, paid API calls per test case during a normal `pytest` run (58 seconds for a partial run before this was caught and fixed). Every graph-level test now runs against one comprehensive fake client covering all six tool names used anywhere in the graph (dispatch, KYA reasoning + narration, Log, Drift, Mandate's semantic check).

## 6. A real bug the test suite caught immediately

The first implementation of `_route_after_specialists` returned the actual list of specialist names to re-dispatch (e.g. `["kya"]`) directly from the conditional edge that's only supposed to decide *whether* to escalate at all — its declared path map was `{"bump_round", END}`, so LangGraph raised `KeyError: 'kya'` at execution time. Fixed by keeping that decision (escalate at all, yes/no) separate from `bump_round`'s own outgoing edge (which specialists specifically). Left the original bug's traceback context in `_route_after_specialists`'s docstring rather than just quietly fixing it — it's a useful, concrete illustration of why the two routing decisions need to stay on separate edges.

## 7. What this phase does *not* do

- No dedup-aware findings reducer (§4) — escalation cannot flip a named-rule verdict, only resolve/narrow observations.
- No multi-round escalation — hard-capped at 1, per CLAUDE.md's explicit design.
- No wiring into scoring or drafting (PLAN items 11/12) — this phase only decides which specialists run and whether to loop back; what happens to the resulting findings/observations after the graph completes is still open.
- `interrupt()` human gates (PLAN item 13) are unrelated and still not built — escalation here is fully automated within the graph, no human involved in the loop itself.
