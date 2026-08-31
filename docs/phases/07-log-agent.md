# Phase 7 — Log Agent

Status: complete. `agents/log.py`, `agents/log_stats.py`, `agents/log_reasoning.py`, tested (`tests/test_log_agent.py`, `tests/test_log_reasoning.py`). Verified live against the real API.

**Revision note:** this phase was built twice. The first pass gave structuring a hardcoded deterministic Python rule (`agents/log_checks.py`, since deleted) alongside LLM-judged concentration/velocity. Per explicit direction — "I don't want [a] deterministic part for Log agent, it should be able to do everything on its own" — that rule was removed and structuring folded into the same LLM judgment as the other two categories. §1-2 below describe the final design; the git history/PLAN.md notes carry the first pass for reference.

## 1. What stayed deterministic, and why that's not a contradiction

`agents/log_stats.py` is unchanged: pure pandas arithmetic — sums, per-counterparty groupbys, candidate same-counterparty clusters via `diff()`/`cumsum()` boundary detection, inter-transaction gaps. This is data preparation, not a verdict: precisely summing sixteen transaction amounts or detecting minute-level time clusters across dozens of rows is exactly the kind of thing an LLM does unreliably and arithmetic does perfectly. Removing the *deterministic detection rule* doesn't mean removing all computation — it means nothing in this codebase pre-decides whether a candidate cluster, a concentration share, or a velocity burst actually *counts* as reportable. That judgment, for all three named categories, is now the model's, given the same real computed evidence every time.

Concretely: `structuring_clusters()` still finds every candidate same-counterparty cluster within a time window. What's gone is the old `agents/log_checks.py` code that then compared each cluster's sum against a threshold and decided the finding itself. Now every candidate cluster (plus the threshold, as context) is handed to the model, which decides — case-005's live run shows the model's stated reasoning went further than the old hardcoded rule ever did, explicitly comparing the cluster against the account's own mean/std (₾5,344 / ₾2,098) to conclude "not typical of this account's normal purchasing behavior," not just "cluster sum > threshold."

## 2. Three rules, one evidentiary tier — all model-judged

`LOG-STR-01` (structuring), `LOG-CON-01` (concentration), `LOG-VEL-01` (velocity) are all evaluated identically now: real, scoped, rule-cited `Finding`s when the model judges them anomalous, each requiring quoted evidence in its own `cited_evidence` field. A naive fixed-percentage concentration threshold was explicitly rejected regardless of this revision — case-003 (77.3%) and case-007 (100%) both show high concentration that's entirely correct given how few counterparties those mandates approve, so the rule is instructed to judge *relative to the mandate's own approved-counterparty count*, not an absolute cutoff. `other_observations` stays genuinely open-ended, `Observation`-style (unscored, no `rule_id`), same tier as KYA's ceiling — the system prompt gives a taxonomy (round-number clustering, escalating amounts, off-hour timing, sudden new-counterparty concentration) as *examples*, explicitly not exhaustive.

`schemas/observation.py`: `Observation` moved out of `agents/kya_reasoning.py` into a shared schema this phase, once Log needed the identical concept — generalized with an `agent` field and renamed `cited_field` → `cited_evidence` (more accurate once "the evidence" can be a transaction cluster, not just a single field path).

The full current system prompt (`agents/log_reasoning.py::SYSTEM_PROMPT`) names all three categories explicitly with the reasoning each one needs (structuring's cluster-vs-threshold logic, concentration's relative-not-absolute framing, velocity's distinction from structuring), gives the open-ended taxonomy, and states the grounding requirement (quote real numbers/transaction ids/cluster contents, never assert without evidence) before instructing high-effort thinking and a forced tool-call response.

## 3. A dispatch-floor tension found and resolved

CLAUDE.md's dispatch floor states "Log+Drift run when history ≥ 30 tx." case-005 — the corpus's own purpose-built structuring case — has only 16 transactions. Under that floor exactly as stated, the orchestrator would never dispatch Log to the one case it's specifically designed to catch. Resolution (discussed and confirmed before building): the 30-tx floor fits **Drift**, which genuinely needs volume for baseline statistics to mean anything; it doesn't fit **Log**'s structuring check, which can validly fire on a handful of tightly-clustered transactions regardless of total history size. This phase doesn't implement the dispatch floor itself (that's PLAN item 9) — noting it here so item 9 doesn't silently inherit a bundled threshold that would starve Log of its own test case.

## 4. Verified live, with two results worth keeping on record

Beyond the mocked test suite (`tests/test_log_reasoning.py` — fake client, no key needed), this phase was run live against the full corpus, both before and after the revision. Two results stood out as genuine, unprompted corroboration rather than noise:

- **case-002**: the LLM independently identified that the breach transaction went to a counterparty (`MER-DWE-011`) not even among the mandate's 2 approved ones — the same underlying defect Mandate already caught (`counterparty_not_approved`), found here through a completely different mechanism (transaction-pattern statistics vs. mandate-scope comparison), with no knowledge of Mandate's specific finding fed into the prompt.
- **case-007**: correctly declined to flag concentration or velocity (single approved counterparty, by design — exactly the case this rule's relative-not-absolute framing was built to handle correctly), but independently flagged the injected ₾1,289 transaction as a statistical outlier (4x mean, 7x median) — a third independent signal alongside Mandate's cap check, injection heuristic, and semantic subcheck.
- **case-003, case-004, case-001**: no false positives on the two naturally-high-concentration cases, and appropriately silent (zero findings, zero observations) on the two cases with genuinely nothing to note.

## 5. What this phase does *not* do

- No dispatch floor wired up anywhere — PLAN item 9. §3's resolution is a design decision recorded for that item to pick up, not implemented here.
- `run()` (agents/base.py's Protocol method, called by `pipeline/graph.py`) is now a true no-op for Log — same shape as Drift's current stub. All of this phase's real analysis is only reachable through `review()`, which the orchestrator doesn't call, same pattern as KYA's ceiling and Mandate's semantic subcheck. This means the deterministic pipeline path (`pipeline/graph.py::run_case()`) never surfaces a Log finding at all right now — only calling `LogAgent().review()` directly does.
- No cross-agent correlation (e.g. automatically linking case-002's Log-found and Mandate-found signals into one combined claim) — that's explicitly the concept note's own "cut first if short on time" item, still out of scope.
