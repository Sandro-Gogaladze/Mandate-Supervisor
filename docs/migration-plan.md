# Migrating the system to the new data, agents and rulebooks

The corpus, the rulesets and three specialists now describe a product the
pipeline does not yet run. This is the plan to close that gap.

Reads with `data-and-agents.md` (what each agent needs), `architecture-v3.md`
(the target pipeline), `coverage-model.md` (the 73 failures) and
`kya-ruleset.md` (the 57 rules).

---

# Part 0 — Where the gap actually is

**Built and working:** 2 dossiers · 70 runs · 5 rulesets · 37/42 KYA rules
active · 15 CTL rules · Provenance and Systemic checkers · 291 tests.

**Not wired:** the pipeline still consumes `CaseBundle` and dispatches four
specialists. Everything above runs from scripts and tests, not from the graph.

| Layer | Today | Target |
|---|---|---|
| Ingestion | `CaseBundle` → `IngestedCase` | `Dossier` → **EvidencePack** |
| State | `case: IngestedCase` | `dossier: LoadedDossier` + per-run scope |
| Skills | 5 registered | **11 specialists + 4 support** |
| Specialists on the graph | mandate · kya · log · drift | **+ provenance · injection · counterparty · consent · control-assurance · hunter** |
| Findings | `Finding` only | **`Fact` → `Assessment` → `Finding`** |
| Scoring | 3 tiers, sum of weights | **4 dispositions incl. `monitor`**, per-run and per-dossier |
| Ledger | 22 event types, case-scoped | **+ run scope, + portfolio run kind** |
| Systemic | a script | **a scheduled run kind** |

**27 files** reference `CaseBundle`/`IngestedCase`. `pipeline/graph.py` is 978
lines across three graphs. The dashboard is 16 components. This is a real
migration, not a refactor.

---

# Part 1 — The two decisions that shape everything else

## 1.1 · The legacy cases are gone — which makes Phase 2 urgent, not optional

`data/cases/` is deleted. The corpus is two dossiers and nothing else.

That settled the convert-vs-adapt question by removing it, and it is the right
end state: one shape, no adapter, no ambiguity about which corpus a new rule
targets. But it also removed the fixture underneath most of the suite, and the
consequence should be stated plainly rather than discovered later.

**291 tests → 117 passing, 22 modules parked, 3 deleted.**

| | |
|---|---|
| **Deleted** — 3 modules | `test_loader` · `test_signing` · `test_schemas`. They asserted things about the case corpus itself. There is nothing left for them to test |
| **Parked** — 22 modules | Everything covering agents, dispatch, the graphs, tools, prompts and uploads. The behaviour still matters; only the fixture is gone |
| **Passing** — 117 tests | Everything built on the new shape: dossiers, rulesets, CTL, Provenance, Systemic, ledger, scoring, state, facts |

Parked in `tests/conftest.py` under `collect_ignore`, by name rather than by
glob. They fail at *import*, not assertion, so a skip mark cannot reach them.
Naming them individually is deliberate: a glob would silently swallow any future
test that happened to match, and the entire reason for parking rather than
deleting is that the missing coverage stays **visible and counted**. A silently
shrinking suite is how a migration loses coverage nobody notices.

**So Phase 2 is no longer a choice about tidiness.** Until the pipeline consumes
a `Dossier`, the orchestrator, dispatch, the three graphs, the tools and the
upload path have no test coverage at all — and no data to run on.

## 1.2 · Three decisions taken — see HANDOFF.md §9

**Review scope.** Round 1 is whole-dossier per agent: one LLM call over the
entire dossier, producing one coherent account of that agent's behaviour across
all runs, **citing specific runs**. Round 2 is narrowed by the orchestrator to
the runs the officer asked about. Viable because the deterministic floor runs
per run first, so the LLM reasons over a compact fact table rather than 50 JSON
files. ~11 calls, and cross-run failures (F55, F59–F66) stay possible.

**Scoring.** Rule-gated refusals plus weighed judgement, four dispositions:
authorise / monitor / refuse / incomplete-submission. A short explicit list of
failures refuses outright; everything else weighs severity against clean-run
count and coverage, because a sum-of-weights function cannot count what went
right.

**Rulebooks.** Nine, one per agent. `consent.json`, `injection.json`,
`counterparty.json` and `provenance.json` still to be written.

## 1.3 · Facts before agents

Every checker today returns `Finding | None`, and `None` means two different
things: *this rule was satisfied* and *this rule had no evidence*. The five
registry rules promoted in Stage 2 return `None` on legacy cases meaning
**absent**, and nothing downstream can tell.

That is already wrong. It becomes unfixable once seven more specialists are
built on the same contract, and every eval number computed in between is
measuring the wrong thing — an agent that stayed silent for lack of evidence
scores identically to one that checked and found nothing.

`schemas/fact.py` and `schemas/assessment.py` exist for this and are unused.
**Phase 1 is the Fact migration. Nothing else starts first.**

---

# Part 2 — The phases

Ordered so the suite stays green at every step, and so no phase builds on a
contract the next phase changes.

## Phase 1 — Facts and Assessments  *(the foundation)*

**Why first:** it changes the return contract of every checker. Doing it after
the new specialists means writing eleven agents twice.

1. Checkers return `list[Fact]` instead of `Finding | None`. Each fact is
   `breach` · `satisfied` · `measurement` · `absent`, and an `absent` fact
   **must** name its `AbsentReason` — `missing_block`, `insufficient_history`,
   `out_of_scope`, `rule_draft`.
2. Agents turn facts into `Assessment`s: verdict, confidence, severity.
   The floor is `severity_floor` from the ruleset; an agent may **raise** it with
   a recorded rationale and may never lower it.
3. `Finding` becomes a projection of an Assessment for the API and ledger, not a
   thing agents produce directly.
4. Migrate `kya_checks` (21 checkers), `mandate_checks` (10),
   `control_checks` (15), `provenance_checks` (3).

**Gate:** every rule that lacks evidence emits an `absent` fact naming the block,
and a data-gap finding appears on the case. The legacy seven produce `absent`
for consent/construction rules instead of silence. Suite green.

**Risk:** the largest single diff in the plan (~50 checkers). Do it rule-family
by rule-family with the suite green between each.

## Phase 2 — Ingestion and state

5. `ingestion/normalize.py` gains `normalize_dossier()`: verify every signature
   and chain, resolve all six registries, **compute shared statistics once**
   (counterparty profiles, drift baselines, timing distributions, control
   evaluation counts), and record which submission blocks are present.
   Output: an **EvidencePack**. No rules evaluated here — rules belong to agents.
6. `pipeline/state.py`: `case: IngestedCase` → `dossier: LoadedDossier`,
   `evidence: EvidencePack`, plus `run_scope: list[str]` so a round can target
   specific runs rather than the whole submission.
7. Delete the `CaseBundle` path. `data/loader.py` loads a manifest that no
   longer exists and is dead; `agents/context.py`, `agents/tools.py`,
   `agents/synthesizer.py`, `api/main.py`, `ledger/seed.py` and
   `data/uploads.py` all import from it. `schemas/case.py` goes with them.
8. **Unpark the 22 modules as their fixtures land.** Build one dossier fixture
   in `tests/conftest.py` and take names off `collect_ignore` as each module's
   subject is migrated — the list is the migration's own progress bar.

**Gate:** the triage graph runs end to end on `DOSSIER-KST-2026-001` with the
four existing specialists and produces the same findings the scripts do.

## Phase 3 — Migrate the four existing specialists

8. **Mandate** — per-run now. Scope comes from `run.intent_mandate`, not one
   standing mandate. Add `usage`/F50 and `merchant.region`/F48. Its LLM call
   becomes per-line-item intent fidelity against *the shopper's own sentence*,
   which is what makes F49 a real test rather than a formality.
9. **KYA** — 37 active rules. Wire `run_credential_series_checks` (CAP-05,
   LIF-04) as a dossier-scoped pass. Widen its evidence block with the
   transaction summary `REG-03` needs — a `compose_context()` change, no new
   firm data.
10. **Log** and **Drift** — read `transaction_history` across the whole dossier;
    Drift consumes `change_log` so its onset estimate lands on a named event
    instead of a date.

**Gate:** all 21 planted defects in the two dossiers that are *computable* are
found by agents on the graph, not by `verify_dossier.py`.

## Phase 4 — The seven new specialists

Each is a deterministic floor plus at most one contained LLM call, per the house
pattern. Checkers for three already exist.

| | Agent | Checkers | LLM does |
|---|---|---|---|
| B1 | **Provenance** | ✅ `provenance_checks.py` | agent-card vs credential vs registry reconciliation |
| B2 | **Injection** | new | which of the four channels, and did the agent act |
| C1 | **Counterparty** | new | is this payee what it appears to be |
| C2 | **Consent & Harm** | new | value-for-money against `selection_context` |
| E1 | **Control Assurance** | ✅ `control_checks.py` | classify posture: absent/failed/bypassed/ineffective |
| E2 | **Systemic** | ✅ `systemic.py` | concentration judgement |
| E3 | **Red Team** | new | generates cases from the mandate's own parameters |

11. `agents/injection.py`, `counterparty.py`, `consent.py` + their check modules.
12. Wrap the three existing check modules in agents.
13. **Control Assurance runs after the peer fan-out**, not inside it —
    `CTL-EFF-01` consumes the other agents' findings and cannot work without
    them. There is already a test asserting it stays silent when given none.

**Gate:** all 11 dispatchable, each returning assessments with citations.

## Phase 5 — Orchestrator and skills

14. `agents/skills.py`: 5 → 11 skills, each with its evidence-block declaration
    and its permitted tools. Tool permissioning stays enforced in code.
15. Orchestrator round 1 dispatches **every agent whose evidence block is
    present**; the deterministic floor is a backstop, not the driver. Round 2+
    judges the officer's question against every fact round 1 produced.
16. `pipeline/graph.py`: 4 specialist nodes → 10 parallel + control-assurance
    sequenced after. Regenerate the React Flow graph from
    `graph.get_graph()` — never hand-maintained.

**Gate:** a round-1 dispatch runs all 11 over the whole dossier with a recorded
`DispatchPlan`, every assessment citing its runs; a round-2 officer question
about one run re-dispatches only the relevant agents **with only that run's
context**.

**Schema enforcement:** an assessment about run-level behaviour that names no run
is rejected. Without it a whole-dossier call produces claims nobody can check.

## Phase 6 — Synthesis and scoring

17. **Critic** (deterministic) then **synthesizer**. The synthesizer *marks*
    duplicate findings `same_event`; scoring *prices* the duplication through a
    registry dedup factor. Corroborating findings compound instead.
18. **`monitor` — SAFR's fourth disposition.** Add the tier, and `case_watched`
    to the ledger. An authorisation outcome is authorise / refuse / **authorise
    with conditions**, and "with conditions" is `monitor` under another name.
    It is the right home for F55's concentration and F67's monoculture — neither
    is a refusal, and both are currently forced into `review` or `clear`.
19. Scoring becomes two-level: **per run** (did this purchase go wrong) and
    **per dossier** (should this agent be authorised). The dossier verdict is
    not the sum of run scores — forty clean runs are evidence *for*
    authorisation, and a scoring function that only adds cannot express that.

**Gate:** `DOSSIER-KST-2026-001` scores `monitor` or `refuse` with a factor
breakdown citing real assessments; `DOSSIER-HAL-2026-001` scores lower.

## Phase 7 — Ledger

20. New event types: `dossier_submitted`, `run_evaluated`, `fact_recorded`,
    `assessment_recorded`, `portfolio_sweep_started/completed`, `case_watched`.
21. Events gain an optional `run_ref` so the timeline can be filtered to one run
    out of fifty.
22. `case_submitted` carried a whole `CaseBundle` dict; a 50-run dossier must be
    recorded as **the dossier plus its run index**, with run files referenced by
    digest rather than inlined.

**Gate:** hash chain verifies across a full 50-run review; the ledger export
replays the case.

## Phase 8 — API

23. New routes: `/dossiers`, `/dossiers/{id}/runs`, `/dossiers/{id}/runs/{run_id}`,
    `/portfolio/sweep`, `/dossiers/{id}/decision`. Keep `/cases/*` as aliases
    through Phase 9, then remove.
24. **Submission becomes multi-file.** `POST /cases/upload` takes one JSON file
    and validates a `CaseBundle`. A dossier is a directory: `dossier.json`, 20–50
    run files, `transactions.json`. Replace with:
    - `POST /dossiers` — accepts a zip, or `dossier.json` first and runs
      streamed after, returning a submission id;
    - **verification at the door**, before anything is accepted: every
      `run_index` digest matches its file, no run file is missing, none is
      present that the index does not name, every signature verifies and every
      chain link resolves. A submission that fails any of these is rejected
      with the specific reason, not stored and flagged later — the index is an
      attestation, and accepting a submission that contradicts its own
      attestation destroys the point of having one;
    - `runs_submitted` vs `runs_executed_total` recorded at intake, because S2
      is decided here and nowhere else.
25. Upload is per-institution, not per-firm: the submitter is the regulated
    entity, and the API should reject a dossier whose `institution_id` is not
    the authenticated one.

**Gate:** a 50-run dossier uploads, is verified at the door, and a tampered run
file is rejected naming the run.

## Phase 9 — The supervision console

Three separate problems. The second is the one that matters most, and it is not
a styling problem.

### 9.1 · The agent conversation is unreadable, and structurally so

`StepFeed.tsx` has a `formatArgs()` that JSON-stringifies whatever it is given
into a `<pre>`; `Conversation.tsx` does `JSON.stringify(value, null, 2)` in
three more places. There is **no renderer per event type** — raw JSON is not a
fallback that occasionally shows, it is the default path. Restyling will not fix
that; the fix is a renderer for every payload the pipeline can emit, and a
rule that an unrendered payload is a bug rather than a shrug.

**What a supervisor actually needs to follow, per agent:**

| | Rendered as |
|---|---|
| Which agent, and the one question it owns | a turn header — named, with its question in words |
| What evidence it was given | the blocks present, and **the blocks absent**, which is currently invisible and is itself a finding |
| What it is doing, live | streamed reasoning text, not a spinner |
| Which rules it ran | a count that expands into rule ids and verdicts |
| What it concluded | assessment cards: verdict, confidence, severity, and the **citation** |
| What it could not check | `absent` facts with their reason — the honest half of every review |

26. **`AgentTurn`** replaces the flat step feed. One block per agent, in
    dispatch order, collapsible, with a live status. Reads like a transcript of
    eleven specialists working, because that is what it is.
27. **A renderer per payload type** — `FactCard`, `AssessmentCard`,
    `MeasurementRow`, `AbsentNotice`, `ToolCallRow`, `ControlPostureBadge`,
    `CorrelationLink`, `PortfolioFindingCard`. A registry keyed by type with a
    loud fallback: unknown payloads render as *"no renderer for X"* with the
    type named, so the gap is visible in review rather than silently ugly.
28. **Evidence is cited, never dumped.** An assessment shows its claim and a
    reference — `RUN-2026-0811-0043 · cart_total $708.00 · KST-CTL-001` — that
    expands to the underlying fact and links to the run. No payload is ever
    printed whole.
29. **Streaming that means something.** Token streaming for agent reasoning;
    event streaming for facts as they land. An agent that has produced four
    facts and is still thinking should look like that, not like a spinner. The
    existing SSE/AG-UI plumbing carries this already — what is missing is the
    rendering, not the transport.
30. **Absent is first-class.** *"Consent & Harm ran 7 rules, 5 satisfied, 2
    absent — no `rendered_values` in this submission"* is a supervisory fact,
    and today it renders as nothing at all. Depends on Phase 1.

### 9.2 · The flowchart

31. `SupervisionMap` (341 lines) and `PipelineGraph` (229) regenerate from
    `graph.get_graph()`, so Phase 5 changes their topology automatically — but
    ten parallel peers plus a sequenced Control Assurance is a busier graph than
    four, and the current layout will not hold. Needs: peers in a row that
    survives ten, Control Assurance visibly *after* the fan-out rather than
    beside it, and the escalation loop still legible as a loop.
32. **Live state on the graph**, not just topology: idle · dispatched ·
    running · returned-clean · returned-findings. A supervisor watching a review
    should be able to see where it is without reading the feed.
33. One click from a node to that agent's turn in the conversation.

### 9.3 · Fifty runs need their own navigation

34. **Run list** inside the dossier — sortable by verdict, filterable to the
    ones carrying findings, with the clean majority visibly the majority. Forty
    clean runs are the substance of an authorisation, and a UI that only shows
    exceptions tells the opposite story.
35. **Run detail** — one AP2 chain end to end: the shopper's request, the
    tool calls, what they were shown at consent, what was signed, what settled,
    which controls fired. This is the view that makes the product legible.
36. **Portfolio view** — `PortfolioFinding` spans dossiers and has nowhere to
    render today.
37. **The dossier decision** — authorise / refuse / monitor, with the factor
    breakdown behind it, at the human gate.

**Gate:** an officer opens a dossier, sees 50 runs with the clean ones obvious,
drills into the one that breached, reads eleven agent turns with no raw JSON
anywhere, asks a question, watches round 2 stream, and signs a disposition.

## Phase 10 — Eval

26. `eval/` does not exist. Build the harness over `ground_truth.json`:
    per-rule and per-run precision/recall, false-positive rate over the 54 clean
    runs, and the **judged** failures reported separately — F49 and F38 are not
    machine-checkable, and folding them into one number hides that.
27. Wire `awaiting_specialist` so a planted failure with no implemented agent
    fails the eval until someone moves it. The coverage gap stays executable.

**Gate:** one command produces per-agent precision/recall and a false-positive
rate against both dossiers.

## Phase 11 — Portfolio as a run kind

28. Systemic becomes a scheduled sweep, not a script: its own run kind, its own
    ledger events, `PortfolioFinding` persisted and rendered.

**Gate:** a sweep runs from the API and its findings appear in the ledger.

---

# Part 3 — What this costs, and what could go wrong

| Phase | Size | Risk |
|---|---|---|
| 1 Facts | **largest** — ~50 checkers | Touches everything. Mitigate by family, suite green between each |
| 2 Ingestion/state | large | **22 test modules are dark until this lands.** The orchestrator, all three graphs, dispatch, tools and uploads currently have zero coverage |
| 3 Migrate 4 | medium | Their LLM prompts assume one mandate per case |
| 4 Seven agents | **largest by volume** | 11 LLM calls per review — cost and latency both real. Measure before assuming Sonnet everywhere |
| 5 Orchestrator | medium | Fan-out of 10 changes the failure modes; one slow agent stalls a round |
| 6 Scoring | small, high value | The two-level verdict is a genuine design question, not a refactor |
| 7 Ledger | medium | Event-shape changes are not retro-compatible with existing chains — plan a reseed |
| 8 API | medium | Multi-file intake is new; verification-at-the-door is the part not to skip |
| 9 Console | **large** | Most visible, least tested, and 22 parked test modules do not cover any of it. The conversation renderer is a rewrite of the largest component in the app (`Conversation.tsx`, 687 lines) |
| 10 Eval | medium | Should have existed before any of this |
| 11 Portfolio | small | Mostly plumbing |

**Three things I would not do:**

- **Do not run all 11 specialists on every round.** Round 1 comprehensive is the
  design; rounds 2+ dispatching everything again is waste dressed as rigour.
- **Do not let the adapter live.** §1.1's middle option is the one that quietly
  costs the most.
- **Do not build the console before the eval.** Without precision/recall there
  is no way to tell a working pipeline from a plausible-looking one, and a good
  console makes plausible-looking extremely convincing. Build the eval first so
  the console is displaying something known to be true.
- **Do not restyle the conversation.** The JSON is not a styling failure, it is
  the absence of a renderer layer. Prettier `<pre>` blocks are still `<pre>`
  blocks.

# Part 4 — The shortest path to a working demo

If time is short, this order gets an end-to-end demo soonest while keeping every
gate honest:

**Phase 1 → 2 → 3 → 5 (partial: dispatch the 4 migrated agents over the new
state) → 6 (`monitor`) → 8 (multi-file intake) → 9.1 and 9.3 (the conversation
renderer, the run list, the run detail).**

That demonstrates the real story — an authorisation dossier of 50 runs, reviewed
per run, with a disposition — on four specialists rather than eleven. Phase 4's
seven agents then land one at a time behind an eval that can prove each one
earns its place.
