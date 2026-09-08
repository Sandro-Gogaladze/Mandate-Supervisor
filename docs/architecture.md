# Architecture

How a review actually runs, and why the system has this shape.
[supervision-model.md](supervision-model.md) covers what is being checked;
[guardrails.md](guardrails.md) covers what stops it going wrong.

---

## The shape

A **modular monolith** — one Python process, plus a React console and a
CopilotKit runtime for the UI. Swap-ability comes from typed interfaces and
rules-as-data, not from network boundaries. Splitting ten specialists into ten
services would have bought distributed tracing problems and no isolation the
type system does not already give.

| Layer | Choice |
|---|---|
| Language | Python 3.12+, `uv`, Pydantic v2, pytest |
| Orchestration | LangGraph — `StateGraph`, conditional edges, `interrupt()` |
| Model | Anthropic API, `claude-sonnet-5` by default |
| Ledger | SQLite + SHA-256 hash chain + append-only triggers |
| Checkpointer | LangGraph's, in a **separate** store — disposable resume plumbing |
| Signatures | Real Ed25519 via `cryptography` |
| API | FastAPI |
| Console | React + Vite + Tailwind + shadcn/ui + React Flow + CopilotKit (AG-UI) |

---

## Two bounded graphs

`pipeline/graph.py` builds two. Each starts, does one job, appends what it
produced to the ledger, and exits. **Neither is held open** — the case lives in
the ledger, not in a paused process.

### REVIEW — `build_review_graph()`

```
ingest → orchestrate → { the skills it dispatched … } → specialists_done
       → control_assurance → critic → synthesizer → record → END
```

| Node | What it does |
|---|---|
| `ingest` | Reads the submission **from the ledger by case id** — never from a client-supplied path. Rebuilds the dossier, runs `ingestion/normalize.py` |
| `orchestrate` | Reads the request and dispatches specialists with a briefing each, or replies from the record, or asks for the report |
| *specialists* | Each runs its deterministic floor over the dossier in scope, assesses it, then makes its one contained model call |
| `specialists_done` | Fan-in |
| `control_assurance` | Runs **after** the peers, by topology. Learns which risk materialised from their breach facts |
| `critic` | Deterministic check over what was produced |
| `synthesizer` | Additive — correlates findings across specialists, resolves correlation ids |
| `record` | Score, authorisation recommendation, and the run's closing events |

A first pass and a later officer question use the **same graph**. On a first
pass the dispatch is deterministic — every governed review skill runs, and the
complete plan (including `not_dispatched`) is recorded. A later question lets
the orchestrator narrow the scope. The run kind on the record is `triage` for a
first pass or directed re-analysis, `investigation` for a question.

### DRAFTING — `build_drafting_graph()`

```
load_record → draft_report ⇄ grounding_check → human_gate (interrupt) → END
```

Only reachable by explicit request. It reads the score already recorded by the
completed review; reporting never re-evaluates the case.

One loop is capped:

- **Reviewer rounds**, capped at `_MAX_REVIEWER_ROUNDS = 3`. A human can send a
  report back for re-analysis; past the cap they must approve or reject.

The drafter makes one non-thinking reporting call over the completed record.
`agents/grounding.py` checks it once afterward: citations must be real, every
confirmed failure must be cited, observations remain quarantined, and a
section's declared character must match the verdicts it cites. Routine
satisfied checks are summarized by area rather than listed individually.

The single `interrupt()` in the whole system sits at `human_gate`, and the
decision it records is **bound by hash to the exact recommendation reviewed** —
a signature on a specific set of findings, not on a case that has since moved.
It guards the **artifact** — a report cannot issue without a named decision, which is a
minutes-long pause and exactly what a checkpointer is for. It never guards the
**case**, which stays open for weeks and is therefore a ledger state.

---

## State and its reducers

`pipeline/state.py`. The state carries `dossier` (the submission as loaded),
`evidence` (what intake established — signatures, registries, shared statistics,
which blocks are present), `run_scope`, and the growing `facts`, `assessments`,
`findings`, `observations`.

Those four use **dedup-aware reducers, not `operator.add`**. This is not
defensive decoration. LangGraph's default retry policy re-executes a node from
scratch on a transient error — a flaky model call inside a specialist's
reasoning pass, *after* its deterministic floor already computed real facts.
That was confirmed live in an AG-UI trace showing one node's STARTED/FINISHED
events repeating within a single run. `operator.add` cannot tell a retried
node's output from new work; these reducers can, because fact and assessment ids
are deterministic (`<case>:<rule>[:<run>]`).

---

## The determinism discipline

The design rule is: **if code can do it, code does it.**

The model has exactly three jobs, and no others:

1. **Decide the judged rules** — 15 of the 113 rules are judged. 84 are
   computable and never reach a model; the remaining 14 use an older shape that
   carries no `evaluation` key yet.
2. **Explain over already-computed facts** — narration of numbers the
   deterministic layer produced, never of raw firm text.
3. **Flag what the rules do not cover** — and those land as **observations, not
   findings**, which by construction cannot move the score.

The model is never asked whether anything is wrong. It is asked one named
question, from one rule, and it cannot invent a new kind of finding because the
vocabulary of findings is not its to write.

```
                      deterministic          model
ingestion             ██████████████████████████     none, ever
KYA floor             ██████████████████████████     none
mandate/consent/…     ████████████████████░░░░░░     floor + one contained call
log / drift           ████████████████░░░░░░░░░░     real statistics, judged verdict
scoring               ██████████████████████████     pure function
grounding             ██████████████████████████     pure Python validator
drafting              ░░░░░░░░░░░░░░░░░░░░░░░░░░     prose — but from findings only
```

Three consequences worth stating plainly:

**Scoring cannot be influenced by a model.** `pipeline/scoring.py` is a pure
function: same findings in, same score out. When a firm challenges the number
the answer is a printable derivation — these findings × these ruleset severity
weights, tiered by this config version. An LLM-assigned score would be an
opinion wearing a number.

**Observations can never score.** Unverified model hunches are excluded from
`score_findings()` **by its signature**, not by convention — the strongest way
to keep "never scored" true permanently.

**Statistics are computed, verdicts are judged.** `log_stats.py` and
`drift_stats.py` produce per-counterparty totals, candidate clusters, gap
distributions, PSI and z-scores. Nothing pre-decides whether a candidate cluster
is structuring. That call is the one contained judgement, and it is made over
computed numbers rather than raw firm text.

---

## The output vocabulary

Every agent returns typed records, never a print statement or a loose dict.
This is what made adding the ledger and the console additive rather than a
rewrite.

```
Fact          one rule's result on one run — re-checkable by hand
   ↓          absent facts name their reason and what is missing
Assessment    a specialist's conclusion over facts, with a confidence
   ↓          later rounds supersede earlier assessments
Finding       the projection the report and the score consume
Observation   a model hunch — quarantined, never scored, never cited as evidence
```

Confidence is priced, not decorative: `certain` 1.0, `probable` 0.7,
`possible` 0.4 (`registry/authorisation.json`).

---

## Ledger, and what it is not

`ledger/store.py` — SQLite, append-only, SHA-256 hash-chained.

- The class **exposes no update and no delete method at all.** The SQL triggers
  are defence in depth for anything reaching the database another way.
- Hashing reuses `data/canonical.py::payload_hash` — the same canonical
  serialization that signs the corpus. One definition of "the bytes of this
  object" across signing and chaining, so there is no second implementation to
  drift.
- The chain is **global across all cases** (`prev_hash` links by `seq`, not per
  case), so a deleted or reordered event anywhere breaks verification
  everywhere.
- Appends serialize: a per-path process lock plus `BEGIN IMMEDIATE` with
  `MAX(seq)` re-read inside the transaction. Specialist nodes finishing
  simultaneously in a fan-out is the real concurrent case and must not fork the
  chain.

Verify it independently:

```bash
python -m ledger.verify
```

Exit 0 and "intact" on a clean chain; exit 1 listing every broken link
otherwise. The same check is exposed at `GET /ledger/verify`.

> **The ledger is not the checkpointer.** LangGraph's checkpointer lives in a
> separate store and is disposable resume plumbing. Delete it and you lose
> in-flight resumability. Delete the ledger and you lose the audit trail. Only
> one of those is allowed to matter, and letting the checkpointer quietly become
> a second source of truth is the failure this separation exists to prevent.

Event types are a closed vocabulary validated on write (`ledger/events.py`), and
actors are typed `<kind>:<name>`. Notably `dispatch_recorded` stores the **exact
composed context** each agent received, so a finding can be traced back to the
precise input that produced it.

---

## API and console

`api/main.py` plus routers for dossiers and the sandbox. FastAPI, with the
console served by nginx on the same origin so there is no CORS surface.

```
browser :5173 ── nginx ─┬─ /            static console (React, Vite)
                        ├─ /api/        FastAPI + LangGraph + ledger  :8123
                        └─ /copilotkit  CopilotKit ⇄ AG-UI runtime    :4000
```

The pipeline graph shown in the console is generated from LangGraph's own
`graph.get_graph()` via `pipeline/map.py` and `GET /review-graph` — never
hand-maintained, so a diagram cannot drift from the code it depicts.

The console is built on CopilotKit's hooks implementing the **AG-UI protocol**
(`useCoAgent`, `useCoAgentStateRender`, `useCopilotAction`) rather than its
default chat widgets. This is a case-review product, not a chat app: the hooks
give live agent state, streamed reasoning and the human-approval widget without
imposing a chat shell.

---

## Why this shape

| Decision | Reasoning |
|---|---|
| Orchestrator-worker, no agent-to-agent messaging | Everything reads and writes typed records to a shared ledger, so any conclusion is traceable to inputs. Direct messaging makes the trail a transcript |
| Bounded graphs, not one long-running process | A case is open for weeks; a process is not. Case state belongs in the ledger, and only the minutes-long artifact gate belongs in a checkpointer |
| Reviewer loop capped in code | A human-directed re-analysis is bounded at three rounds, so it remains useful without becoming an unbounded workflow. Drafting itself is one reporting call. |
| Control Assurance runs last, by topology | It needs its peers' breach facts to know which risk materialised. Making that a graph edge rather than a prompt instruction means it cannot be skipped |
| Ledger built after the detection pipeline worked | Deliberately sequenced late. A hash chain needs single-writer serialization regardless of database, so Postgres's concurrency advantage does not apply — and building the audit trail before there was anything worth auditing would have frozen the wrong vocabulary |
