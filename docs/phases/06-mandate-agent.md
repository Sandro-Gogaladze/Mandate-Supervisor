# Phase 6 — Mandate Agent

Status: complete. Deterministic core (§1-4) and LLM semantic subcheck (§6-8) both built and tested. Full corpus, including case-007's all three expected findings, verified live against the real API — see §8.

## 1. What got built

9 new active rules in `registry/rulesets/mandate.json` (`MND-CAP-01/02/03`, `MND-CAP-05`, `MND-CON-01`, `MND-CUR-01/02`, `MND-VAL-01`), alongside the 2 chain-integrity rules already active since Phase 3. Unlike KYA's rules, almost none of these carry ruleset-level params — the threshold being checked (`max_transaction_amount`, `allowed_merchant_categories`, ...) is the case's own Intent, not a regulator policy constant, so there's nothing for the registry to configure beyond severity/status. The one exception is `payment_amount_matches_cart_total`'s float-rounding `tolerance` (0.01) — a genuine policy knob (how much rounding slack is acceptable), not a case-derived value.

## 2. Every design decision was checked against real corpus numbers first, not assumed

Before writing any checker, I dumped every case's `authorization_scope`, cart/payment amounts, and transaction-history sums and looked at the actual numbers rather than trusting the phase-1 field table alone:

- **case-002's exact violation shape** confirmed `MND-CAP-01`/`02`/`03` (cap/category/counterparty) exactly reproduce its three expected findings, with no guessing about which fields matter.
- **The "month" in `max_cumulative_amount`** isn't a formal schema field — the phase-1 doc's field table doesn't define a period, and neither does `authorization_scope`. But case-001's own `Intent.natural_language_intent` says *"don't let the month's total go over ₾4,000"*, and its Cart's `agent_attestation.reasoning` claims *"brings month-to-date spend to ₾1,748.10"*. Summing `transaction_history` by calendar month of `Payment.authorized_at` reproduces **exactly ₾1,748.10** — confirmed to the cent before writing `MND-CAP-05`, not assumed. `tests/test_mandate_agent.py::test_cumulative_cap_check_matches_the_cases_own_reasoning_text` locks this in.
- **`transaction_history`'s last entry is always the case's own payment** (verified across all 7 files) — so summing history directly already includes the current transaction; no separate cart-total addition needed anywhere a cumulative check reads history.
- **Geographic scope is a real schema gap, not a missing-data gap.** `Merchant` only carries `country` (always `"GE"` across every case), while `geographic_scope` is region-level (`"GE-TB"`, `"GE-KU"`). A country-only comparison would be *vacuous* — every merchant and every scope value share the same country, so the check would always pass and give false confidence that geographic scope is enforced when it isn't at the granularity the field name implies. `MND-CAP-04` stays draft, with that reasoning in its `notes`, rather than shipping a check that can't fail.

## 3. A ground-truth correction, and an incidental catch worth documenting

Running the finished floor against case-007 (`prompt_injection`) surfaced `per_transaction_cap_exceeded` — not something built for this case specifically. The injected line item ("Digital Gift Card Top-Up," ₾1,200) inflates `cart_total` from ~₾89 to ₾1,289, well over the case's ₾350 cap — so a hard dollar-cap check, built entirely independently of any injection-awareness, catches part of an injection attack as a pure numeric side effect. Worth noting as a real, if incidental, defense-in-depth data point: the semantic subcheck (part 2) isn't the *only* thing standing between a prompt-injection attack and an unflagged transaction.

That same run also caught a genuine error in the original ground truth: `data/corpus_manifest.json` expected `category_out_of_scope` on case-007, but the cart's merchant (`Kutaisi Garden Supply Co`, mcc `5261`) *is* within the Intent's allowed categories — the actual problem is that the smuggled line item is a gift-card top-up, not a garden/landscaping product, which is a **line-item-level semantic mismatch**, not a merchant-MCC mismatch. `MND-CAP-02` (merchant-category matching) correctly does *not* fire here, because nothing about the merchant's registered category is wrong. The manifest was corrected to expect `cart_reasoning_semantic_mismatch` instead — the finding_type `MND-SEM-01` (part 2) will actually produce — with a note explaining the distinction, same as case-004's correction in Phase 5.

## 4. Coverage discipline carried over from KYA

`run_policy_checks()` raises `NotImplementedError` on an active rule with no registered checker, same as `agents/kya_checks.py` — `tests/test_mandate_agent.py::test_coverage_gap_raises_loudly_not_silently_skipped` proves it. `agents/mandate.py::MandateAgent.run()` combines the chain pass (Phase 3, reused via `ingestion/verify.py`) and the new policy pass, with visibly distinct finding-id schemes (`-FND-` vs `-MND-`) so nothing silently collides — same pattern as KYA's `-FND-`/`-POL-` split.

## 5. What part 1 does *not* do

- **`MND-CAP-04` (geographic scope)** stays draft — real schema gap, see §2.
- No LLM call anywhere in `run()` — the deterministic floor stays fully key-free, same discipline as KYA's floor.

## 6. Part 2: the LLM semantic subcheck, and two mechanisms on purpose

`agents/mandate_reasoning.py::check_cart_reasoning_matches_intent()` is CLAUDE.md's "one contained LLM call" — comparing `Cart.agent_attestation.reasoning` and the cart's actual contents against `Intent.natural_language_intent` for semantic consistency. Same high-thinking-effort, `tool_choice: auto`, injectable-`client` pattern as `agents/kya_reasoning.py` (and the shared plumbing — `ModelDidNotCallTool`, `extract_tool_input()` — was moved into `agents/llm.py` during this phase specifically so both modules could import it without one reasoning module depending on the other).

Independently, `MND-SEM-02` (`agents/mandate_checks.py::_check_line_item_injection_heuristic`) is a **pure deterministic pattern match** over every `line_items[].description`, scanning for phrasing characteristic of an embedded instruction (direct address to an agent, false pre-authorization claims, no-confirmation-needed urgency, instruction-override language). It runs in `run()` — no LLM, no key needed — and fires completely independently of whatever the semantic subcheck concludes. This is deliberate, per CLAUDE.md's injection-containment rule ("...separately heuristic-flagged"): if the semantic check were ever manipulated into concluding "consistent" despite an actual injection, the heuristic still catches the raw pattern on its own. Two independent signals, not one mechanism with a redundant restatement.

## 7. Why this LLM output is a real `Finding`, not an `Observation`

This is the one place this codebase has two visibly different answers to "should an LLM's judgment become a citable finding," and it's worth being explicit about why, not just consistent by accident:

- **KYA's ceiling** (`agents/kya_reasoning.py`) was optional, additive reasoning over an *unbounded* search space ("anything the fixed rules didn't catch") that we added beyond CLAUDE.md's original scope. Nothing about it corresponds to a specific rule; there's no severity to weight, no way to say in advance what it's even checking. `Observation` reflects that honestly.
- **Mandate's semantic subcheck** is a *required*, *scoped* comparison between exactly two named pieces of text, explicitly specified in CLAUDE.md as a first-class part of the agent's job, corresponding to a real rule (`MND-SEM-01`) with a real `rule_id` and `severity_weight` — structurally identical to every other Mandate rule except that its evaluation mechanism happens to be an LLM instead of arithmetic. A human reviewer could independently re-derive the same verdict by reading the same two texts. That's why it becomes a `Finding` and is merged into the same list `run()` produces, not held back as a second-class citizen.

`MandateAgent.review()` only calls the LLM at all if `MND-SEM-01` is `active` in the ruleset passed in — a draft version of this rule (e.g. mid-edit in policy sandbox, PLAN item 14) never fires, LLM or not, same governance discipline as every deterministic rule.

## 8. Verified live, not just against fakes

`tests/test_mandate_reasoning.py` covers prompt construction, response parsing, the delimiter markers actually appearing in the outbound payload, and the `run()`/`review()` split — all against a fake client, no key needed. Beyond that, this phase was also run live against the real API: case-007 produces all three of its expected findings exactly (`per_transaction_cap_exceeded`, `injection_heuristic_flag` on `line_items[0]`, and `cart_reasoning_semantic_mismatch` with a genuinely well-reasoned explanation quoting the real injected text and the false operator-authorization claim), and case-001 stays completely clean. Full corpus ground truth is now reproduced end-to-end for every case Mandate is responsible for.

## 9. What this phase does *not* do

- `pipeline/graph.py` untouched — the orchestrator calls `MandateAgent.run()` (deterministic only), never `review()`. Wiring the semantic subcheck into the pipeline state is an open question, same one left open for KYA's ceiling in Phase 5.
- `MND-CAP-04` (geographic scope) still draft — unrelated to part 2, see §2.
