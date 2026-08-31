# Phase 8 — Drift Agent

Status: complete. `agents/drift.py`, `agents/drift_stats.py`, `agents/drift_reasoning.py`, tested (`tests/test_drift_agent.py`, `tests/test_drift_reasoning.py`). Verified live against the real API.

Built directly on the pattern established (and revised) in Phase 7: no hardcoded Python verdict decides drift, same as Log's structuring/concentration/velocity — real statistics computed deterministically, judgment left to the model.

## 1. What's deterministic, and what isn't

`agents/drift_stats.py` computes PSI (population stability index, for counterparty and MCC mix shift), a z-score (average transaction size shift), and per-week frequency, splitting the visible history into a baseline window (first `baseline_window_days`, default 30) and everything after. All pure pandas/numpy — verified against case-006's exact numbers before being trusted: baseline mean ₾187.95 (14 tx) vs. comparison mean ₾316.51 (35 tx), z-score 7.15, counterparty-mix PSI 5.86, MCC-mix PSI 2.02 (both roughly 20x past the conventional "major shift" PSI threshold of 0.25).

What's not deterministic: whether that shift *means* anything. `agents/drift_reasoning.py`'s system prompt explains PSI/z-score conventionally so the model can weigh them, then explicitly warns against flagging or dismissing "based on the statistics' size alone without reasoning about what they actually represent" — modest, gradual, explicable growth isn't drift; a brand-new counterparty and category dominating the mix alongside a >7-sigma amount jump is. Live confirmation on case-006: the model's own explanation reasons about all four signals together ("individually a frequency uptick or moderate size growth might be explainable... but the combination... together represent a pattern... not something that plausibly falls within normal seasonal or organic-growth variation") — genuine synthesis, not a threshold trip.

## 2. The one prerequisite check kept outside the model: `insufficient_baseline`

PLAN item 8 names this explicitly ("`insufficient_baseline` under 30 tx"). Whether there's *enough history to attempt a comparison at all* is a row count, not a judgment about behavior — `DriftAgent.review()` checks `len(transaction_history) < min_total_transactions` (ruleset param, default 30) and short-circuits to `DriftReview(insufficient_baseline=True)` without calling the model, same reasoning as Log's empty-history short-circuit (`agents/log_reasoning.py`). Verified live: case-001 (24 tx) and case-007 (7 tx) both correctly report `insufficient_baseline=True`; case-006 (49 tx) runs the full analysis.

This ties to the same dispatch-floor question Log's phase raised: CLAUDE.md's "Log+Drift run when history ≥ 30 tx" fits Drift precisely (this is exactly where that number comes from — a baseline split needs real volume on both sides to mean anything), unlike Log's structuring check, which can validly fire on a handful of transactions. Drift is the domain that floor was actually calibrated for.

## 3. `run()`/`review()` split, same as Log

`run()` is a true no-op (always `[]`) — no deterministic detection exists at all to put there. `review()` is where everything happens: the `insufficient_baseline` gate, the PSI/z-score computation, the model call, merging the one named `Finding`-producing rule (`DRIFT-BHV-01`) with open `Observation`s for anything else worth noting. `pipeline/graph.py`'s `drift` node still calls `run()`, so — same as Log — Drift currently contributes nothing through the standard orchestrator path; only `DriftAgent().review()` called directly surfaces anything.

## 4. Verified live, with a genuinely useful cross-cutting catch

Beyond the mocked test suite, this phase was run live. case-006 didn't just produce the expected drift finding — its two open observations both pointed at real, actionable follow-ups outside Drift's own remit: flagging the new dominant counterparty (`MER-BEF-005`, 48.6% of comparison-window transactions, zero baseline presence) for KYA-style verification, and flagging that the new MCC (7538, vehicle maintenance/auto repair) falls outside the mandate's declared `fleet_fuel_logistics` purpose category — a potential Mandate-scope concern the model surfaced entirely on its own, with no Mandate-specific context fed into the prompt.

## 5. What this phase does *not* do

- No dispatch floor wired up anywhere (PLAN item 9) — `insufficient_baseline` is Drift's own internal gate, not the orchestrator's dispatch decision; those are related but distinct (the dispatch floor decides whether Drift is even invoked at all, `insufficient_baseline` is what Drift itself reports when it *is* invoked without enough data).
- `pipeline/graph.py` unchanged in behavior — `drift` node calls `run()`, contributes nothing by default, same as Log.
- No cross-agent wiring — the model's own observations pointing at KYA/Mandate concerns aren't automatically routed anywhere; a human reading them would have to act on that pointer manually. Automating that is out of scope (concept note's "cut first" cross-agent correlation item).
