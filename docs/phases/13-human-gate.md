# Phase 13 — Human review gate (with directed re-analysis)

Status: complete. `human_gate` node in `pipeline/graph.py` (LangGraph `interrupt()`), `schemas/review_gate.py`, reviewer-directive threading through all four specialists, `ReviewGate.tsx` + decision trail in `ReportPanel.tsx`. Tested (7 gate tests in `tests/test_pipeline.py`: pause, approve, reject, directed rerun, invalid-payload re-interrupt, cap enforcement). Verified live end-to-end in-browser: run → gate held → reviewer sent it back to Log with a threshold-avoidance question → directed pass ran and the tail re-ran → gate again at round 1 → approved with comment → **issued ✓**, both decisions on the timestamped record. Zero console errors.

## 1. The gate is structural, not cosmetic

After `grounding_check` passes, the graph routes to `human_gate`, whose body calls LangGraph's `interrupt()` — the checkpointer freezes the run and execution *cannot* proceed until a resume payload arrives. This is the judged human-in-the-loop guardrail in its strongest form: not a UI button that politely asks, but a pipeline that is structurally incapable of issuing anything alone. A **blocked** report (failed grounding twice) never reaches the gate at all — there is nothing approvable to decide on.

The decision is typed and named (`ReviewerDecision`: action, reviewer, optional comment, optional directive), and `decided_at` is stamped **server-side** in the gate node — never trusted from the client. Decisions accumulate in state under an `operator.add` reducer: the full sequence of named calls made on a case is part of its record (and is exactly the artifact item 15's hash-chained ledger will anchor).

## 2. The gate defends itself

The node loops on `interrupt()`: an invalid payload (missing reviewer, malformed shape, non-dict) or a rerun request past the cap doesn't crash the run — it **re-interrupts** with an `error` field in the context, which the UI surfaces in the same gate card. The gate holds until a *valid* named decision arrives. Covered by `test_invalid_decision_reinterrupts_with_an_error_instead_of_crashing` and `test_rerun_cap_forces_a_final_decision`.

## 3. Directed re-analysis — the human steers the workforce

The third decision besides approve/reject: `rerun` with a `ReviewerDirective` (free-text instructions + explicit target agents — no regex guessing, unlike the machine escalation's note parsing). Routing fans back out to exactly the named specialists, then the whole tail re-runs: score recomputed, report redrafted, grounding re-validated, gate again.

Mechanics worth recording:

- **The directive reaches prompts via `REVIEWER_ADDENDUM`** (`agents/llm.py`), the same containment pattern as the escalation addendum — delimited, output still schema-constrained. The instruction is regulator-authored (trusted-principal input), which is why free text is acceptable here and never for firm-submitted content.
- **A directed pass may produce new findings** — deliberately, unlike the machine escalation round (observations-only). This is safe *because of* Phase 10's dedup reducer: a re-run's identical deterministic findings dedup away by `finding_id`, while a genuinely changed judgment (e.g. Log flipping structuring to anomalous) arrives under a new id and flows into score/report. The human's question can change the outcome; nothing double-counts.
- **Mandate is human-targetable** even though it's never a machine escalation target (it produces no observations) — a reviewer directive is the only way that node runs twice.
- **The directive is transient**: consumed by one specialist pass, cleared in the `risk_score` node (which every path to the tail crosses). Rounds are capped at `_MAX_REVIEWER_ROUNDS = 3` — belt-and-braces only, since each iteration costs an explicit human decision; the human *is* the loop bound.

## 4. Transport: the same AG-UI pipe as everything else

No bespoke endpoint. `api/main.py` sets `emit_interrupt_outcome=True`, so an interrupted run terminates its SSE stream with the structured AG-UI outcome; `ag_ui_langgraph/interrupts.py` maps the LangGraph interrupt (id + full context dict under `metadata.langgraph.raw`) into the AG-UI `Interrupt`. The client resumes via `agent.runAgent({resume: [{interruptId, status: 'resolved', payload}]})` — `RunAgentInput.resume[]`, verified present in both the installed Python (`ag_ui.core.RunAgentInput`) and TS (`@ag-ui/client` `ResumeEntry`) packages *before* designing around it. The UI's `onRunFinishedEvent` subscriber narrows on the `interrupt` outcome to open the gate card.

## 5. UI

`ReviewGate.tsx` — a primary-ringed card that appears when the run pauses: "the pipeline is paused — nothing issues without a named sign-off." Reviewer name (required to enable any decision), optional comment, **Approve & issue** / **Reject**, and a dashed "send it back with instructions" section: textarea + agent chips (round N of 3 shown; section replaced by a cap notice when exhausted). Server-side validation errors from re-interrupts render as a destructive alert in the same card. The Run button reads "Awaiting decision" and disables while a gate is open. `ReportPanel` gained the **decision record** (named, timestamped, directive text verbatim) and its header now tracks `issued ✓ / rejected / grounded ✓ · awaiting reviewer`.

## 6. Test seam

Gate tests drive the real interrupt machinery: a shared `build_graph(checkpointer=MemorySaver())` + `Command(resume=...)` per decision. `run_case()` itself now compiles with a per-call MemorySaver (interrupts require a checkpointer) and documents that it returns *at the gate* with `__interrupt__` in the returned state. `FakeChatModel` gained `last_messages_for(tool)` so the rerun test can assert the directive text actually reached the Log agent's prompt in a run where later tools were called after it.

## 7. Post-verification fix: the gate's false edge lighting

User-reported ("the human gate connection becomes orange sometimes"), confirmed real, two defects in the pipeline visualization:

1. **Edge liveness was source-based** (`live = source active || target active`). `human_gate` fires `STEP_STARTED` and then interrupts — no `STEP_FINISHED` ever arrives — so while it held, *all four of its return edges to the specialists* animated amber, as if a re-analysis had been ordered that nobody requested. Fixed by making edge liveness **target-based only**: an edge lights when its destination is the node currently working, which is the actual traversal signal (dispatch→specialist edges still light correctly because the specialists themselves go active).
2. **The paused gate rendered green "Complete"** — the settle pass (which converts stale `active` to `done` when the run stops, the node-retry defense from Phase 10 §8) swallowed the gate's held state. The gate now has its own visual state, `awaiting` ("Awaiting reviewer", primary blue ring + pulsing dot, blue animated inbound edge), forced by `displayNodeStatus` whenever a gate is open; it flips to green only after a decision resolves the node.

Verified live: during the pause, gate = blue "AWAITING REVIEWER", inbound edge blue-animated, return edges neutral; after approval, gate = green Complete. Zero console errors.

Two follow-ups from a second user report, both confirmed real and fixed:

3. **Target-only liveness had the mirror-image false positive.** While Mandate worked in round 0, *every* inbound edge of the active node lit — including `human_gate→mandate` and `bump_round→mandate`, return edges from nodes that had never executed. The rule is now "target active AND source actually ran (`done`/`active`)" — an edge lights only when it was plausibly just traversed. `bump_round→kya` during a genuine escalation round still lights, correctly, because bump_round really did run.
4. **Results bled across cases.** The CopilotKit registry agent is a shared singleton — one client state, one threadId — so opening case B rendered case A's findings/report, and running case B on case A's thread made LangGraph's checkpoint *merge* the runs (findings/observations/decisions are reducer channels; case A's entries would have survived into case B's record). Fixed in `CaseReview.tsx`: a hard reset per case open **and** per fresh run — `agent.threadId = crypto.randomUUID()`, `setMessages([])`, `setState(EMPTY + case_path)` — isolating both the client render and the server checkpoint. Verified live: after issuing case-001, case-002 opens fully empty (no findings, score, status, or decision record). Known cost, accepted for now: navigating away from an open gate abandons that paused thread (no ledger yet to resurface it — item 15's territory).

5. **Third face of the edge bug: false GREEN.** The "settled" emerald tint was still target-only — once a specialist finished, every inbound edge went green, including the gate's unused return paths. Rather than patch a third color rule, edge coloring now derives from one predicate: **actual traversal order**. `usePipelineFeed` records each node's last-STARTED sequence (tracked in its own map, since the feed's rows dedup repeated starts); an edge is traversed only if both ends started and the target started *after* the source. All three states (amber live / blue holding / green settled) require it. Semantics that fall out, verified live: the gate's return edge to a rerun target lights amber during the directed pass (target started after the gate — true traversal), forward edges re-light green cycle by cycle, and once the run loops back to a fresh hold the graph shows the *current* cycle only — history lives in the decision record, not the wires. Return edges never light without a real rerun, in any color.
