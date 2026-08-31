# Phase 11 — Risk scoring

Status: complete. `pipeline/scoring.py`, `schemas/scoring.py`, `registry/scoring.json`, `registry/loader.py::load_scoring_config()`, a `risk_score` graph node, `ScoreCard` in `ResultsPanel.tsx`. Tested (`tests/test_scoring.py`, 7 tests; graph-level assertion in `tests/test_pipeline.py`). Verified live: case-002 scored **3.60 → ESCALATE** mid-run, and the drafted report's lede stated the tier verbatim.

## 1. A pure function, and why that's the whole point

CLAUDE.md's framing verbatim: a pure function with weights from the ruleset is "the only honest version of 'explainable, factor-level scoring'". `score_findings(case_id, findings, config)` sums each finding's `severity_weight` per agent and in total; the disposition tier is the highest floor the total reaches in `registry/scoring.json`. Same findings in, same score out — when a firm challenges "why 3.60," the answer is a printable derivation: these findings × these ruleset weights × tier config version 2026.08.0. An LLM-assigned score would be an opinion wearing a number.

Design details that carry the honesty:

- **Observations can't be scored *by signature*** — the function takes `list[Finding]` only. "Unverified is never scored" is enforced by the type system, not convention.
- **`severity_weight=None` counts but prices at zero** — visible in its factor's `finding_count`, contributing 0.0, rather than silently invisible.
- **Tiers are data** (`registry/scoring.json`, versioned, `ScoringConfig`-validated) — the same rules-as-data treatment as the rulesets, which is what lets the policy sandbox (item 14) later answer "what does tightening the escalate floor do to our caseload?" by re-running with a draft config. The config's ordering isn't trusted (sorted at use), and a misconfigured tier set that leaves a score below every floor falls back to the lowest floor instead of crashing a live review.

## 2. Where it sits in the graph

A `risk_score` node between the escalation loop's settled exit and `draft_report` — recomputed on *every* pass through the tail, because a reviewer-directed re-analysis (item 13) may change the findings and the number must follow them. The node doubles as the cleanup point for a consumed reviewer directive (every path from the specialists to the drafting tail runs through it).

## 3. Feeding the report

`agents/drafting.py`'s payload gained a `risk` block (total, tier, label, guidance, factors), and the system prompt gained rule 6: state the tier and total **exactly as given** — never substitute your own severity arithmetic. Verified live: the issued report's first sentence was "Risk score 3.6, tier: Escalate…". The deterministic number leads; the prose follows it.

## 4. UI

`ScoreCard` at the top of the results panel: the total in display type, the tier badge (emerald/amber/red for clear/review/escalate — status hues, not brand), the config version in mono, and four per-agent factor bars with score · count. The `risk_score` node also appears in the React Flow pipeline (Gauge icon) via `/graph`, automatically.
