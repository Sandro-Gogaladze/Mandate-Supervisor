# Phase 12 — Report drafting + grounding check

Status: complete. `schemas/report.py`, `agents/drafting.py`, `agents/grounding.py`, `pipeline/graph.py` (drafting tail), `dashboard/src/components/ReportPanel.tsx`. Tested (`tests/test_drafting.py`, `tests/test_grounding.py`, `tests/test_pipeline.py` extended — 148 total). Verified live in-browser: case-002 produced a grounded report first-try, all 5 findings cited, observations quarantined in the labeled note.

## 1. Where drafting sits — and why nothing "sends" findings to it

The user's framing was "findings go to the orchestrator again or directly to drafting?" — the architecture's answer is *neither agent hands anything to anyone*. Specialists write typed `Finding`s/`Observation`s into shared graph state (CLAUDE.md: agents never message each other directly), and the graph routes to the drafting tail once the escalation loop settles. Concretely: `escalate_check`'s settled exit and `bump_round`'s no-targets exit, which both used to return `END`, now return `"draft_report"`:

```
… → escalate_check ─┬→ bump_round → (escalation loop, unchanged)
                    └→ draft_report → grounding_check ─┬→ grounded → END
                              ↑                        └→ problems ─┬→ retry (≤2) ─┘
                              └────────────────────────────────────┘└→ cap hit → blocked → END
```

No second LLM dispatch decision — "specialists are done, now draft" is deterministic routing, not judgment.

## 2. The input-restriction property (the actual security design)

The drafting agent is the only one whose entire output is free prose — so its *input* is the most restricted in the pipeline. `agents/drafting.py::_structured_view()` builds its payload from the structured record only: findings (id/agent/type/rule_id/severity/summary/details), observations, the dispatch plan's `ran` list + reasoning, and an `escalation_round_ran` boolean. **No raw case file.** No `natural_language_intent`, no line-item descriptions, no prompt playback — no slot for firm-authored text to ride an injected instruction through. The firm's *name* and the case id are the only submission-derived strings, as identifiers. `tests/test_drafting.py::test_payload_is_structured_record_only` pins the exact payload key set so a future field addition is a conscious decision, not drift.

## 3. Grounding: a deterministic validator, not an LLM judging an LLM

`DraftReport` (schemas/report.py) forces the checkable structure: sections each carry `cited_finding_ids`, and observations get exactly one labeled slot (`open_observations_note`) so unverified hunches can't be laundered into cited prose. `agents/grounding.py::check_grounding()` is pure Python:

- every cited `finding_id` must exist (no invented citations),
- when findings exist, every section must cite ≥ 1 (no free-floating prose) and every finding must be cited somewhere (silently dropping an inconvenient finding is as ungrounded as inventing one),
- a zero-findings case must have zero sections (clean verdict lives in `overall_assessment`),
- `open_observations_note` is required when observations exist and forbidden when none do.

Problem strings are written to be *actionable by the model*, because on retry they're appended verbatim to the system prompt (`RETRY_ADDENDUM`) — the model fixes the named problems rather than re-rolling blind.

## 4. The bounded loop, and a docs discrepancy resolved

PLAN item 12's wording said "regenerate-once-then-block"; CLAUDE.md's orchestration table says "grounding-retry (capped at 2) on the drafting agent". CLAUDE.md is the authority per its own header, so: 1 initial draft + at most 2 regenerations (`_MAX_GROUNDING_RETRIES = 2` in pipeline/graph.py), then **block** — `report_blocked=True`, and the UI withholds the prose entirely (destructive alert listing the validator's complaints; the findings panel remains the authoritative record). Never ship ungrounded prose, even partially. `tests/test_pipeline.py::test_ungroundable_draft_retries_twice_then_blocks` locks the exact count (3 draft calls) and that the retry prompt carried the feedback.

State plumbing: `draft_report` / `draft_attempts` / `grounding_problems` / `report_blocked` are plain overwrites, not reducers — exactly one draft is current at a time; a retry *replaces* the failed draft.

## 5. Test seam: the fake draftsman had to be payload-aware

A static canned response can't be grounded for every case — citations must reference whatever `finding_id`s the case under test actually produced. `tests/fakes.py::FakeChatModel` therefore now accepts a **callable** response (`args(messages)`), and `tests/test_pipeline.py::_grounded_draft` parses the real payload JSON and cites every finding in it — so all pre-existing graph tests pass through the new drafting tail with zero retries and no assertion churn.

## 6. UI

The review tab gained a full-width **Supervisory report** card (and switched from the fixed-viewport juggling to a normally scrolling page — four surfaces don't fit one viewport). `ReportPanel.tsx`: the overall assessment as the lede, sections with citation chips (`CASE-…-MND-001` etc.), the observations note in a dashed box labeled "unverified — for officer judgment, not findings", a `grounded ✓ / regenerating · attempt N / blocked` status in the panel header, and the full blocked-state alert. The two new nodes appear in the React Flow pipeline automatically (from `/graph`), with `draft_report` given its own agent identity (indigo, FileText) in `node-meta.tsx`.

## 7. What this phase does not do

- No risk score or disposition tier in the report — that's item 11's pure scoring function; it will slot in as one more structured input line to this same drafting payload.
- No human gate — the report is drafted, not "sent"; item 13's `interrupt()` builds directly on this (the gate sits between grounded draft and any send).
- The blocked path preserves the failed draft in state for debuggability but never renders its prose — revisit only if item 13 wants to show a redlined diff to the reviewer.
