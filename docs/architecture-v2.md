# Architecture v2 — orchestrator-led supervision

Status: **proposed, not adopted.** Branch `feat/orchestrator-led-supervision`. Written 2026-08-31,
before build week (1–8 Sep).

`PLAN.md` and `CLAUDE.md` are untouched. This document is self-contained — Part III carries its own
task list. If adopted it replaces PLAN.md items 14–17.

---

# Part I — The idea

## 1 · What a review actually is

The current build treats a review as a **pipeline run**: press Run, four specialists fire in
parallel, a score comes out, a report is drafted, a human signs. One pass, one verdict, done.

That is not how supervision works. A case officer opens a file, reads what the automated pass found,
notices something, asks a question, gets an answer, asks a sharper question, sends one specialist
back with specific instructions, and only writes the report once she is satisfied she understands
what happened. It takes hours or days. It is a **conversation with a workforce**, not a batch job.

So the architecture changes shape:

> **A supervisor conducts a review by talking to an orchestrator. The orchestrator decides which
> specialists to bring in, briefs each one with exact evidence and a specific instruction, and
> writes down everything that was asked, answered, and decided.**

The closest human analogue is a case conference. The orchestrator is the officer's assistant: it
knows who to call in and how to brief them, but it has no opinion of its own about the firm. The
specialists are experts who speak only when asked, only about their own domain, and never to each
other. The record of the conference is the deliverable, not anyone's memory of it.

## 2 · The five roles

| Role | What it is | Speaks to |
|---|---|---|
| **Orchestrator** | Routes and briefs. Talks to the supervisor. Has no view of its own on the case. | supervisor, subagents |
| **Four specialists** — Mandate, KYA, Log, Drift | Domain experts. Each has its own system prompt and its own rules. Produce **Findings**. | orchestrator only |
| **Investigator** (new, 5th) | General-purpose lookup agent with read-only tools. Answers open questions the four can't. Produces **Observations**. | orchestrator only |
| **Critic** | Deterministic. Checks a subagent quoted numbers that actually exist in the evidence it was given. | nothing — it's a function |
| **Synthesizer** | Finds relationships *between* findings. Emits typed `Correlation` records. Never filters. | nothing — it's a function + one model call |

**Subagents never talk to each other.** Every message goes through the orchestrator, and every one
is recorded. This is a commitment in the submitted concept note and it stays.

## 3 · Two tiers of output, and why the line is absolute

Everything a subagent produces lands in one of exactly two tiers:

| | **Finding** | **Observation** |
|---|---|---|
| Backed by | a versioned rule (`rule_id`) | nothing — a model's read |
| Carries | `severity_weight` | no weight |
| Scored | yes | **never** |
| Citable in the report | yes | no — quarantined to one labelled note |
| Who may produce it | the four specialists only | any agent |

This is the load-bearing distinction of the whole system, and it is already enforced structurally:
`Observation` has no `rule_id` and no `severity_weight` field at all, and `score_findings()` excludes
observations **by function signature**, not by an `if`.

The consequence for this architecture: **the investigator can search freely, loop, and use tools —
in exchange for never minting a scored, citable verdict.** If it could emit Findings, "rules are
data, never hardcoded" would quietly become "except when an agent decides otherwise," and the risk
score would stop being a pure function of rule-backed evidence.

If the supervisor wants an investigation's insight turned into a real finding, she sends a
**specialist** back to look. The machine investigates; a rule decides; a human directs.

## 4 · What the orchestrator may and may not do

The orchestrator is the most powerful component and therefore the most constrained.

**It may:**
- Decide which subagents to run, by matching the situation against a **skill registry**
- Compose the context each subagent receives — *which* evidence blocks to include
- Write a specific instruction for each subagent, appended to that subagent's own system prompt
- Report back to the supervisor what came back
- Propose next steps

**It may not:**
- **Answer a substantive question about the case from its own reading.** It is a dispatcher that
  speaks, not a chatbot that knows. If the supervisor asks "is this structuring?", the orchestrator
  says "I'll ask Log" — it does not offer an opinion. Enforced structurally: its output schema is a
  routing decision (`{intent, targets, instruction, context_blocks, message_to_officer}`), not free
  prose about the firm.
- **Summarize or truncate evidence.** Whatever it includes, it includes verbatim. A summarized
  transaction list is a different question than the real one.
- **Go below the evidence floor.** Each subagent always receives at least its canonical computed
  view. The orchestrator adds; it never subtracts.
- **Skip a mandatory specialist.** Mandate and KYA run on the first pass regardless of what the
  orchestrator proposes or what any prompt says.
- **Rewrite a subagent's system prompt.** It appends an instruction to a prompt that lives in the
  repo. Prompts are policy; runtime-invented policy is unreviewable policy.

### Why the evidence floor exists

Verdict reproducibility is already gone — every judgment tier in this system is an LLM call with
adaptive thinking. That is accepted and it is fine. **Evidence integrity is a different thing and it
is worth keeping.**

Concretely: case-005's structuring pattern is only visible across all 16 transactions relative to the
account's own mean and spread. A subagent handed three rows can still answer, and its answer will be
worse, and nothing downstream will know why. The floor means a specialist's verdict may vary between
runs, but it is always a verdict *about the same evidence*.

That also makes the supervisor's own feature work: **running a case twice and comparing** is only
meaningful if both runs saw the same data. Otherwise you are diffing two different questions.

## 5 · Where guarantees live

The single most important property of this design: **every guarantee is enforced in code, and none
of them depend on a prompt.**

| Guarantee | Enforced by | Not by |
|---|---|---|
| Mandate + KYA always run on pass 1 | `enforce_floor()` — can only turn False→True | the orchestrator's prompt |
| Subagents see at least their canonical evidence | `compose_context()` merges over a fixed base | the orchestrator's judgment |
| Observations are never scored | `score_findings(findings: list[Finding], …)` signature | convention |
| Every report claim cites a real finding | `check_grounding()`, pure Python | a second LLM judging the first |
| A subagent quoted real numbers | the critic, pure Python | trust |
| The synthesizer can't invent findings | typed `Correlation` + id resolution check | prompt instruction |
| Nothing issues without a named human | `interrupt()` — graph topology | policy documentation |
| The record can't be edited | hash chain + append-only triggers + no update method | good behaviour |

A prompt can be wrong, edited, or manipulated. None of the above changes if it is.

## 6 · Prompts are per-run arguments, not global settings

Every agent's system prompt has a **default that lives in the repo**, versioned, changed through
normal code review. The supervisor can **see** the default and **override it for a single run**.

- Overrides are **temporary**. They apply to one run and one run only; the next run starts from the
  default again. Nothing accumulates, so nothing drifts.
- The **full effective prompt text** is recorded on the run — not a version pointer, since an
  overridden prompt has no stable artifact to point at.
- Only the middle of a prompt is editable. A fixed preamble (role, available specialists) and a fixed
  contract (the tool the model must call) bracket it, so a bad edit can't break the machinery.
- The floor still holds. Write "skip KYA" and KYA runs anyway — and the record shows both the
  instruction and the override, which is itself informative.

This is `rules are data, never hardcoded` extended from thresholds to instructions, and it slots into
a pattern the codebase already uses: `SpecialistAgent.run(case, ruleset)` takes the ruleset as an
argument precisely so it can be swapped per run. The prompt becomes the same kind of argument.

**Governance falls out for free.** The default changes through a reviewed commit — git is its audit
trail. Per-run overrides change nothing permanent — the ledger is theirs. No promotion flow, no
approval queue, no drift.

## 7 · The record

A case cannot live inside a running program. Today it does — `run_case()` compiles an in-memory
checkpointer and freezes at `interrupt()`, so closing a tab or restarting the process loses every
finding. An investigation spanning days is not expressible.

So the case lives in an **append-only, hash-chained ledger**, and runs are short: they start, do one
job, write what they found, and exit.

What makes this architecture *need* the ledger more than a pipeline would:

1. **"Show me what the orchestrator gave to which agent."** That is the central auditability question
   for orchestrator-composed context, and a `dispatch_recorded` event is the only place to answer it.
2. **Comparing two runs of the same case.** You cannot diff what you did not keep.
3. **A conversation that survives a closed tab.** A chat surface over a system that forgets is worse
   than no chat, because it implies a continuity that isn't there.

Case status is **derived** from the events, never stored — a stored status can disagree with history;
a computed one cannot. Same principle as `score_findings()`, which recomputes rather than reading a
saved number.

## 8 · One case, end to end

**CASE-2026-006** — Adjara Coastal Logistics, 49 transactions.

| | What happens | Recorded |
|---|---|---|
| **1** | Bundle arrives. Triage fires automatically — no human present. | `case_submitted`, `dispatch_recorded` ×4, findings, `score_computed` |
| **2** | All four specialists run on canonical evidence. Drift flags a behavioural shift; Log finds nothing. Score 0.60. | run 1 complete, prompt text stored |
| **3** | Case lands in the queue, scored and sorted. Ana opens it. | `case_opened` |
| **4** | Ana: *"Batumi Express Freight came from nowhere — when did it start and does it fit the mandate's category scope?"* | `question_asked` |
| **5** | Orchestrator picks the **investigator** skill, composes context (the case's counterparty breakdown + the Intent's scope), briefs it. | `dispatch_recorded` with the exact context |
| **6** | Investigator runs 4 tool lookups: 17 tx, first seen 2026-07-11, ₾5,558.40, MCC 4789 — outside the 5541 baseline pattern. Answers, plus an Observation. | `investigation_completed` |
| **7** | Ana: *"then have Mandate check category scope specifically for that vendor."* Orchestrator dispatches **Mandate** with the investigator's evidence added on top of Mandate's canonical view. | `dispatch_recorded`, then a Finding or not |
| **8** | Critic verifies Mandate quoted real values. Synthesizer notes the Drift finding and the new Mandate finding describe one event. | `correlation_recorded` |
| **9** | Ana closes her laptop. Comes back tomorrow. Everything is there. | — |
| **10** | Ana asks for the report. Draft → grounding → gate. | `report_drafted`, `grounding_checked` |
| **11** | Ana signs. | `decision_recorded` |

Eleven steps, every one attributable, every dispatch showing exactly what was sent to whom.

---

# Part II — The design

## 9 · Invariants

These are the things that must be true after every stage. If a change would break one, the change is
wrong.

1. **Mandate and KYA run on pass 1**, whatever the orchestrator proposes and whatever any prompt says.
2. **Every subagent receives at least its canonical `_structured_view()`.** The orchestrator adds, never subtracts.
3. **No summarization.** Any evidence the orchestrator includes is included verbatim.
4. **Every dispatch is recorded with its exact effective context and instruction.**
5. **Only the four specialists mint `Finding`s.** The investigator and the orchestrator produce `Observation`s.
6. **`score_findings()` reads the raw finding set.** No component may filter, merge, or reweight findings before scoring.
7. **The orchestrator never answers a substantive question about the case from its own reading.**
8. **Subagents never communicate with each other.**
9. **Firm-authored free text never reaches a model undelimited.** `line_items[].description` is delimited where it appears; no investigator tool returns it at all.
10. **Nothing issues without a named human decision**, enforced by graph topology.
11. **Every agent's prompt is recorded in full on the run that used it.**

## 10 · The ledger

New package `ledger/`.

```
ledger/
  __init__.py
  store.py        # LedgerStore — append, read, verify. No update. No delete.
  events.py       # LedgerEvent + the event vocabulary
  projection.py   # events -> CaseRecord
  verify.py       # CLI: python -m ledger.verify
  export.py       # JSONL
```

### 10.1 Schema

```sql
CREATE TABLE IF NOT EXISTS events (
  seq          INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id      TEXT NOT NULL,
  run_id       TEXT,                    -- NULL for case-level events (open, close)
  event_type   TEXT NOT NULL,
  payload      TEXT NOT NULL,           -- canonical JSON
  actor        TEXT NOT NULL,           -- "system:*" | "agent:*" | "human:<name>"
  recorded_at  TEXT NOT NULL,           -- ISO-8601 UTC, stamped server-side
  prev_hash    TEXT NOT NULL,
  hash         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_by_case ON events(case_id, seq);
CREATE INDEX IF NOT EXISTS events_by_run  ON events(run_id, seq);
```

`run_id` is what makes "run this case twice and compare" work. `actor` is mandatory and typed by
prefix — a finding recorded by `agent:drift` and a decision by `human:Ana Dvaladze` must be
distinguishable a year later without reading the payload.

### 10.2 Hash chain

```python
def event_hash(*, seq, case_id, run_id, event_type, payload, actor, recorded_at, prev_hash) -> str:
    return payload_hash({...all fields...}, exclude_keys=())
```

Reuses `data/canonical.py::payload_hash` — **the same canonical serialization that signs the mandate
corpus.** One definition of "the bytes of this object" across signing and chaining; no second
implementation to drift out of sync.

The chain is global across all cases, so a deleted or reordered event anywhere breaks verification
everywhere. Genesis `prev_hash` is `"sha256:" + "0"*64`.

### 10.3 Append-only

```sql
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
```

Defence in depth. The primary control is that `LedgerStore` exposes no update or delete method at
all.

### 10.4 Single-writer

`append()` takes a process-level lock and opens `BEGIN IMMEDIATE`, re-reading `MAX(seq)` inside the
transaction. Four specialist nodes finishing simultaneously in a fan-out is the real concurrent case
and must not fork the chain.

### 10.5 Event vocabulary

| Event | Payload | Actor |
|---|---|---|
| `case_submitted` | full raw `CaseBundle` | `human:<officer>` / `system:seed` |
| `case_opened` | `{}` | `human:<officer>` |
| `run_started` | `{run_id, kind: triage\|investigation\|drafting, prompt_effective, prompt_default_version, prompt_override}` | `system:<kind>` |
| **`dispatch_recorded`** | `{target, skill, instruction, context_blocks, context_digest}` | `agent:orchestrator` |
| `finding_recorded` | `Finding` (one per event) | `agent:<name>` |
| `observation_recorded` | `Observation` (one per event) | `agent:<name>` |
| `critic_checked` | `{target, passed, unquoted_values}` | `system:critic` |
| `correlation_recorded` | `Correlation` | `agent:synthesizer` |
| `escalation_round_started` | `{round, targets}` | `system:triage` |
| `score_computed` | `RiskScore` | `system:scoring` |
| `run_completed` | `{run_id, finding_count, observation_count}` | `system:<kind>` |
| `question_asked` | `{question_id, question}` | `human:<officer>` |
| `investigation_completed` | `InvestigationAnswer` | `agent:investigator` |
| `report_drafted` | `DraftReport` | `agent:drafting` |
| `grounding_checked` | `{passed, problems, attempt}` | `system:grounding` |
| `report_blocked` | `{problems}` | `system:grounding` |
| `decision_recorded` | `ReviewerDecision` | `human:<reviewer>` |
| `case_closed` | `{reason}` | `human:<officer>` |

**`dispatch_recorded` is the event this architecture exists to make possible.** It carries the exact
context sent to each agent — the answer to "what did the orchestrator give to whom." `context_blocks`
is the verbatim payload; `context_digest` is its SHA-256 so two runs can be compared cheaply.

**One `Finding` per event, not a batch.** "Every finding citable" needs each finding to have its own
`seq`, timestamp, and producing actor.

### 10.6 Public surface

```python
class LedgerStore:
    def append(self, *, case_id, event_type, payload, actor, run_id=None) -> LedgerEvent: ...
    def events_for(self, case_id: str) -> list[LedgerEvent]: ...
    def events_for_run(self, run_id: str) -> list[LedgerEvent]: ...
    def all_case_ids(self) -> list[str]: ...
    def verify(self) -> list[str]: ...            # [] means intact
    def export_jsonl(self, case_id=None) -> Iterator[str]: ...
```

## 11 · Projection

`ledger/projection.py`, a pure function.

```python
CaseStatus = Literal[
    "submitted", "triaged", "under_review", "investigating",
    "pending_decision", "issued", "closed_rejected", "closed_no_action",
]

class RunRecord(BaseModel):
    run_id: str
    kind: Literal["triage", "investigation", "drafting"]
    prompt_effective: str
    prompt_override: str | None
    dispatches: list[DispatchRecord]
    findings: list[Finding]
    observations: list[Observation]
    started_at: str
    completed_at: str | None

class CaseRecord(BaseModel):
    case_id: str
    status: CaseStatus
    firm: str
    runs: list[RunRecord]                  # every pass, in order — enables run-vs-run diff
    findings: list[Finding]                # union across runs, deduped
    observations: list[Observation]
    correlations: list[Correlation]
    answers: list[InvestigationAnswer]
    risk_score: RiskScore | None
    draft_report: DraftReport | None
    report_blocked: bool
    decisions: list[ReviewerDecision]
    open_questions: list[str]
    opened_by: str | None
    event_count: int

def project_case(events) -> CaseRecord: ...
def diff_runs(a: RunRecord, b: RunRecord) -> RunDiff: ...
```

Status is evaluated in order, first match wins: `case_closed` → `closed_no_action`; last decision
approve → `issued`; reject → `closed_rejected`; grounded draft with no later decision →
`pending_decision`; unanswered question → `investigating`; `case_opened` → `under_review`;
`run_completed(triage)` → `triaged`; else `submitted`.

Dedup reuses `pipeline/state.py::_add_findings` / `_add_observations` verbatim — one definition of
"the same finding" across the run reducer and the projection.

> **Hard prerequisite.** The `finding_id` collision (Stage 0) must be fixed first.
> `verify_credential_with_ruleset()` and `verify_chain_links_with_ruleset()` both mint
> `<case_id>-FND-001` from separate counters, so a case with both a bad credential *and* a broken
> chain produces two findings under one id and the dedup silently drops one — proven, not
> theoretical. Ship the ledger first and that is permanent in the audit trail.

## 12 · Prompts

```
registry/prompts/
  orchestrator-dispatch.json     # run 1
  orchestrator-session.json      # the conversational orchestrator
  specialist-mandate.json
  specialist-kya.json
  specialist-log.json
  specialist-drift.json
  investigator.json
  drafting.json
```

```json
{
  "prompt_id": "ORCH-DISPATCH",
  "version": "2026.1",
  "body": "Two of the four specialists (Mandate, KYA) are mandatory on every case…",
  "notes": "Default standing instruction for the first-pass review."
}
```

Assembly, in `agents/prompts.py`:

```python
def assemble(prompt_id: str, *, override: str | None = None) -> tuple[str, str | None, str]:
    """Returns (effective_text, override_used, default_version).

        [FIXED PREAMBLE]  role · available specialists · that a floor exists
        [BODY]            default, or the per-run override
        [FIXED CONTRACT]  "your final response MUST be a call to <tool> and nothing else"
    """
```

The preamble and contract are **not** editable — a bad edit must not be able to stop the model
calling its tool. Overrides are per-run and never persisted. The effective text is recorded on
`run_started`.

## 13 · Skills, dispatch, and context composition

### 13.1 The skill registry

```python
# agents/skills.py
class Skill(BaseModel):
    skill_id: str                     # "log.analyze"
    agent: str                        # "log"
    description: str                  # what the orchestrator matches against
    produces: Literal["finding", "observation"]
    requires: dict                    # e.g. {"min_transactions": 1}
    context_blocks: list[str]         # canonical blocks this skill always receives
```

The orchestrator sees the registry and selects skills. Adding a sixth specialist later means adding a
skill entry, not editing a routing function.

### 13.2 The floor still applies

```python
def enforce_floor(selection: list[str], case, *, pass_number: int) -> list[str]:
    """Can only ADD. On pass 1, mandate.verify and kya.verify are always present,
    whatever the orchestrator selected and whatever any prompt said."""
```

Skill selection is semantic matching by a model; the floor is a deterministic function. The first is
allowed to be creative because the second is not.

### 13.3 Context composition

```python
def compose_context(skill: Skill, case, *, extra_blocks: list[ContextBlock]) -> dict:
    """base = the skill's canonical blocks, computed deterministically
       (log_stats / drift_stats / _structured_view — unchanged code).
       Then merge extra_blocks in, verbatim.

       Invariants: base is always fully present (§9.2); extra blocks are
       inserted whole, never summarized (§9.3); the result is recorded as
       dispatch_recorded.context_blocks (§9.4)."""
```

The orchestrator names which extra blocks it wants (e.g. `"investigator_answer:Q-003"`); it does not
author their content. That is what makes "exact content, no summarization" mechanically true rather
than prompt-requested.

## 14 · The runs

Three graphs. Each starts, does one job, appends, and **exits.** None is held open.

### 14.1 Triage — `build_triage_graph()`

```
ingest → orchestrate_dispatch → {mandate, kya, log, drift} → escalate_check ⇄ bump_round
       → critic → synthesizer → risk_score → END
```

- The existing graph, minus the drafting tail, plus critic/synthesizer and ledger writes.
- `ingest` reads the bundle from `case_submitted` rather than a filesystem path.
  **This closes a real hole:** today `/cases` hands the browser absolute server paths, the browser
  puts `case_path` into agent state, and `_ingest_node` does `normalize_case(state["case_path"])` —
  an arbitrary file read driven by client-controlled state.
- Pass 1 selects all four (floor guarantees Mandate + KYA regardless).
- Ends at the score. No report.

### 14.2 Investigation — `build_investigation_graph()`

```
load_context → orchestrate → dispatch(1..n subagents in parallel) → critic → synthesizer → record → END
```

Driven by the conversational orchestrator. Targets may be any specialist (with new context) **or**
the investigator. A specialist dispatched here may produce a new `Finding`; the investigator may not.

### 14.3 Drafting — `build_drafting_graph()`

```
score → draft_report ⇄ grounding_check → human_gate (interrupt) → END
```

Unchanged behaviour: 2-retry grounding cap, `report_blocked` path, the gate's self-defending
`while True` loop, server-stamped `decided_at`.

**The gate guards the artifact, not the case.** `interrupt()` holds a run for minutes while a
decision is made — which is what a checkpointer is for. A case open for a week is a ledger state, not
a paused process.

| | Holds | Lifetime | Delete it and… |
|---|---|---|---|
| Checkpointer | one in-flight drafting run | minutes | lose one resumable draft |
| Ledger | the case | forever | lose the audit trail |

Only reachable by explicit request — a clear case with nothing on it never drafts, it gets
**Close — no action**, which is a named decision rather than a document. (The concept note already
says *"escalated or denied cases go to the Report drafting agent"*; the current build drafts
unconditionally.)

## 15 · Critic and synthesizer

### 15.1 Critic — deterministic

```python
def check_evidence_grounding(output, context_blocks) -> CriticResult:
    """Every numeric value the subagent quoted in cited_evidence must appear
    in the context it was given. Pure Python — no LLM judging an LLM."""
```

Same trick as `check_grounding()`, one step earlier in the pipeline. A specialist that invents a
number is caught mechanically. Failures are recorded (`critic_checked`) and surfaced to the officer;
they do not silently suppress the finding, because a false negative in the critic must not delete a
real finding.

### 15.2 Synthesizer — additive only

```python
class Correlation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    finding_ids: list[str] = Field(min_length=2)
    relationship: Literal["same_event", "causal", "corroborating", "contradictory"]
    explanation: str
```

Three properties make invention impossible in any way that matters:

1. **Every `finding_id` must resolve** to a finding that exists — checked in Python.
2. **It cannot modify or remove findings.** It only emits new records alongside them.
3. **Scoring never reads it.** `score_findings()` keeps its signature. If the synthesizer produces
   nonsense, the score is untouched and the blast radius is one display panel.

The value it adds is real and nothing currently does it: on case-007, `MND-CAP-01`, `MND-SEM-02` and
`MND-SEM-01` are three independent detectors seeing **one** injected line item. Today the report
presents three findings; a correlation says they are one event.

## 16 · The investigator

`agents/investigator.py` + `agents/tools.py`.

```python
AGENT_TOOLS: dict[str, frozenset[str]] = {
    "investigator": frozenset({
        "get_transactions", "get_counterparty_profile", "get_issuer_record",
        "get_rule", "recompute_stats", "get_case_findings",
    }),
    # Schema-constrained output only — no callable capabilities, by design.
    "mandate": frozenset(), "kya": frozenset(),
    "log": frozenset(), "drift": frozenset(), "drafting": frozenset(),
}

def tools_for(agent_name: str) -> list[dict]:
    """The only way any agent obtains a tool definition. Raises on an
    unregistered agent rather than defaulting to empty (or full)."""
```

This is what finally makes the concept note's *"tool access is dispatcher-permissioned, not
prompt-instructed"* true about the code. Today there is no map because there are no tools — every
`_*_TOOL` in `agents/` is an output-schema constraint, not a capability.

| Tool | Returns |
|---|---|
| `get_transactions(filters)` | rows from this case's history — counterparty / date / amount filters |
| `get_counterparty_profile(id)` | count, total, share, first-seen; this case then across the ledger |
| `get_issuer_record(id)` | from `data/issuers.py` |
| `get_rule(rule_id)` | what a rule checks, its params, its status |
| `recompute_stats(kind, params)` | re-run `log_stats` / `drift_stats` with a different window |
| `get_case_findings()` | what is already on the record |

All **read-only, deterministic, non-LLM.** None writes to the ledger, mutates a ruleset, or makes a
model call. **None returns `line_items[].description`** — the one adversarial field in the schema
(case-007's injection lives there). Where a result contains firm-authored strings
(`counterparty_name`), they are delimited exactly as `mandate_reasoning.py` already delimits merchant
text.

The loop is capped at **8 tool calls, enforced in the node, not requested in the prompt.** Every call
is recorded as a `ToolCallRecord` on the answer.

```python
class ToolCallRecord(BaseModel):
    tool: str
    arguments: dict[str, Any]
    result_digest: str

class InvestigationAnswer(BaseModel):
    case_id: str
    question_id: str
    question: str
    answer: str
    cited_evidence: list[str]
    tool_calls: list[ToolCallRecord]
```

`InvestigationAnswer` is **not** an input to the drafting agent —
`test_payload_is_structured_record_only` stays green.

## 17 · Unchanged

`schemas/` (three types added), `agents/` specialists, `ingestion/`, `registry/rulesets/`,
`pipeline/scoring.py`, `agents/grounding.py`, `pipeline/state.py`. The detection layer does not move.
That was the bet PLAN item 15 was sequenced on — *additive, not a rewrite* — and it holds.

## 18 · API and UI

```
GET    /cases                      from the ledger, sorted by score desc, with status
GET    /cases/{id}                 projected CaseRecord + raw bundle
GET    /cases/{id}/runs            run list, for comparison
GET    /cases/{id}/runs/{a}/diff/{b}   run-vs-run diff
POST   /cases/upload               validate → case_submitted → fire triage
POST   /cases/{id}/triage          re-run (optional prompt_override)
POST   /cases/{id}/open            case_opened
POST   /cases/{id}/session         start/continue the orchestrator conversation   (AG-UI stream)
POST   /cases/{id}/report          drafting run → interrupt                       (AG-UI stream)
POST   /cases/{id}/decision        resume the drafting run
POST   /cases/{id}/close           case_closed
GET    /prompts                    defaults, for display and override editing
GET    /ledger/verify              hash-chain verification
GET    /ledger/{id}/export         JSONL
GET    /graph/{run_kind}           React Flow structure per run kind
```

| Component | Change |
|---|---|
| `CaseQueue` | sort by score desc; tier badge + status |
| `CaseReview` | hydrates from `CaseRecord`; `case_path` gone |
| *new* `OrchestratorPanel` | the conversation. The officer's primary surface. |
| *new* `PromptPanel` | shows the active default; per-run override editor; diff vs. default |
| *new* `CaseTimeline` | the ledger rendered — who did what, when, **and what was sent to whom** |
| *new* `RunCompare` | two runs side by side: prompts, dispatches, findings, where they diverged |
| `ResultsPanel` | add correlations and investigation answers, visually distinct from findings |
| `ReportPanel` | stops auto-filling; **Draft report** button; **Close — no action** |
| `PipelineGraph` | triage graph unchanged (the showpiece); small linear variants for the other runs |

`CaseTimeline` and `RunCompare` are the highest-value new surfaces for the pitch: they make
auditability and honest LLM-variance *visible* rather than claimed.

---

# Part III — The plan

Dependencies are strict top to bottom. Each stage lands green (all 161 existing tests passing, minus
the ones that legitimately move) before the next.

## Stage 0 — Fix-first *(~1h, blocks everything)*

- [ ] **`finding_id` collision.** Give `ingestion/verify.py::_FindingIdCounter` a `prefix` argument —
      `KYC` for credential checks, `CHN` for chain checks. Test that a case with both defects yields
      two distinct ids that survive `_add_findings`.
- [ ] **Stale ground truth** in `data/corpus_manifest.json`: case-005 expects `structuring_pattern`
      (the rule emits `transaction_structuring_detected`); case-006 expects three drift types (the
      ruleset has one, `behavioral_drift_detected`).
- [ ] **`/graph` dangling edges** — `api/main.py`'s filter is `edge.target not in ()`, a no-op
      leftover; two edges to `__end__` ship pointing at a node that isn't emitted.

## Stage 1 — Ledger core *(~0.5d, standalone)*

- [ ] `ledger/store.py` — append/read/verify/export, **no update or delete method**
- [ ] Global hash chain reusing `data/canonical.py::payload_hash`
- [ ] Append-only triggers; single-writer lock + `BEGIN IMMEDIATE`
- [ ] `ledger/events.py` — the §10.5 vocabulary; `run_id` and prefix-typed `actor` throughout
- [ ] `python -m ledger.verify` CLI + JSONL export
- [ ] Tests — round-trip; chain verifies; tampered payload fails; UPDATE/DELETE raise; threaded
      appends don't fork; export round-trips

## Stage 2 — Projection *(~0.5d)*

- [ ] `project_case(events) -> CaseRecord` with `RunRecord`s (§11)
- [ ] Status **derived, never stored**
- [ ] `diff_runs(a, b)` — the basis of run comparison
- [ ] Dedup via `pipeline/state.py`'s existing reducers
- [ ] Tests — every status transition; re-derived-finding dedup; `rerun` returns to `under_review`;
      empty event list raises rather than returning a phantom case

## Stage 3 — Prompts as per-run arguments *(~0.5d)*

- [ ] `registry/prompts/*.json` — defaults for all seven prompts, moved out of Python
- [ ] `agents/prompts.py::assemble()` — fixed preamble + body + fixed contract (§12)
- [ ] `prompt_override` threaded through every run entry point; never persisted
- [ ] Effective text recorded on `run_started`
- [ ] Tests — an override reaches the model; the contract survives a hostile override; a run's
      recorded prompt matches what was sent

## Stage 4 — Skills, floor, context composition *(~1d)*

- [ ] `agents/skills.py` — the registry (§13.1)
- [ ] Orchestrator selects skills; `enforce_floor()` rewritten over skill ids, still add-only
- [ ] `compose_context()` — canonical base + verbatim extra blocks, never summarized
- [ ] `dispatch_recorded` written for every dispatch, with `context_blocks` + `context_digest`
- [ ] Tests — a hostile prompt saying "skip KYA" still runs KYA; composed context always contains the
      full base; the recorded context byte-matches what the agent received

## Stage 5 — Triage run wired to the ledger *(~1d)*

- [ ] `build_triage_graph()` ending at `risk_score`; nodes append as they produce
- [ ] `ingest` reads the bundle from `case_submitted`; `case_path` deleted from state (§14.1)
- [ ] `run_case()` → `run_triage(case_id, *, prompt_override=None)`
- [ ] Tests — a triage run appends exactly the expected event sequence per corpus case

## Stage 6 — Critic + synthesizer *(~0.5d)*

- [ ] `agents/critic.py` — deterministic evidence-quoting check (§15.1)
- [ ] `agents/synthesizer.py` + `schemas/correlation.py`; id-resolution validator
- [ ] Wired as two nodes after the specialists, before `risk_score`
- [ ] Tests — an invented number is caught; a correlation citing a non-existent finding is rejected;
      scoring is byte-identical with and without the synthesizer

## Stage 7 — Drafting run + gate *(~0.5d)*

- [ ] `build_drafting_graph()`; `interrupt()` and the retry cap move verbatim
- [ ] `POST /report` runs to the interrupt; `POST /decision` resumes
- [ ] Drafting reads findings from the ledger, not a live triage state
- [ ] The seven gate tests move to `tests/test_drafting_run.py`, unchanged in substance

## Stage 8 — The conversational orchestrator *(~1.5d)*

- [ ] `agents/orchestrator.py` — session-scoped, output schema is a routing decision
      (`{intent, targets, instruction, context_blocks, message_to_officer}`), **never prose about the
      case** (§9.7)
- [ ] `build_investigation_graph()` (§14.2)
- [ ] Session concept: a session spans many dispatches; its prompt is fixed at session start and
      recorded; a mid-session prompt change starts a new session
- [ ] `OrchestratorPanel` — the officer's primary surface
- [ ] Tests — the orchestrator cannot emit a finding; asked a substantive question it routes rather
      than answers; a dispatch it proposes is recorded before the subagent runs

> **Cut line.** Stages 0–8 deliver the architecture: persistent auditable cases, orchestrator-composed
> dispatch with recorded context, per-run prompts, critic + synthesizer, and a supervisor who
> conducts a review by conversation. Everything below is upgrade.

## Stage 9 — The investigator *(~1d)*

- [ ] `agents/tools.py` — `AGENT_TOOLS` map + `tools_for()` raising on an unregistered agent
- [ ] Six read-only, deterministic, non-LLM tools (§16); none returns `line_items[].description`
- [ ] `agents/investigator.py`; loop capped at 8 calls **in the node**; `ToolCallRecord` trail
- [ ] Output tier `Observation` / `InvestigationAnswer` only — never a `Finding`
- [ ] Tests — `tools_for()` never returns a tool outside the map; the loop stops at 8; an
      investigation never produces a `Finding` (assert on the type)

## Stage 10 — UI completion *(~1.5d)*

- [ ] `PromptPanel`, `CaseTimeline`, `RunCompare` (§18)
- [ ] Queue sorted with status; report on demand; close-no-action
- [ ] Triage fires on submission; corpus seeded into the ledger on boot
- [ ] `GET /ledger/verify` surfaced in the UI — "prove the record wasn't tampered with" is a demo beat

## Stage 11 — Sandbox, eval, deploy *(~2d)*

- [ ] Registry promotion + policy sandbox *(PLAN item 14)*; promotion re-triages affected open cases
- [ ] Eval harness *(item 16)* — now a ledger query. Depends on Stage 0's ground-truth fix.
- [ ] docker-compose + `make demo`; Fly.io mirror; five-beat demo rehearsed cold *(item 17)*

## 19 · Effort and parallelism

Stages 0–8 ≈ **6.5 days** serial; 0–10 ≈ **9 days**. Build week is 8 days with two builders, so the
realistic split is backend (0–9) and frontend (8's panel, 10) in parallel from Stage 5 onward.
Stage 11 is at genuine risk — treat the sandbox as the first thing to cut, per the concept note's own
*"cut first if short on time."*

## 20 · Test plan

- All 161 existing tests keep passing except the ~8 in `tests/test_pipeline.py` asserting the old
  single-run shape. Those move or change meaning; none are deleted silently.
- New suites: `test_ledger.py`, `test_projection.py`, `test_prompts.py`, `test_skills.py`,
  `test_context_composition.py`, `test_critic.py`, `test_synthesizer.py`, `test_orchestrator.py`,
  `test_investigator.py`, `test_tools.py`, `test_drafting_run.py`.
- Every invariant in §9 gets at least one test that fails if it is broken. The hostile-prompt tests
  matter most: a prompt saying "skip KYA," "summarize the transactions," or "you may declare a rule
  violated" must each be defeated by code.
- One end-to-end test that *is* the demo: submit → triage → open → question → dispatch → draft →
  sign, then assert `verify()` is clean and the projected status is `issued`.

## 21 · Risks

| Risk | Mitigation |
|---|---|
| Build week is 8 days and Stage 11 was already outstanding | Hard cut line after Stage 8; 9–11 explicitly optional |
| The conversational orchestrator is the biggest new surface and the least specified | Stage 8 depends on 4 and 5 being solid; if it slips, Stages 0–7 still ship a working improvement |
| Orchestrator-composed context weakens evidence quality | §9.2 evidence floor, tested; §9.3 no summarization; every dispatch recorded |
| More agents multiply the SSE surface that already dropped on heavy runs | Investigation and drafting runs are short; the long run (triage) is unchanged in length; the `unhandledRejection` guard stays |
| Scope creep into a rewrite | §17 is the contract: the detection layer does not move |

## 22 · Considered and rejected

Recorded so a later session doesn't rediscover them as ideas.

- **Orchestrator summarizing evidence.** Would let it starve a detector (case-005's cluster is only
  visible across all 16 transactions) and make run-vs-run comparison meaningless.
- **Skills replacing the mandatory floor.** Skill selection is semantic matching; the floor is a
  deterministic function that can only add. Losing it means an orchestrator could decide a case is
  "obviously just a scope breach" and never check the credential.
- **An LLM synthesizer between findings and scoring.** If it can merge, drop, or reweight, the score
  stops being a pure function of rule-backed evidence and "explainable, factor-level scoring" is gone.
- **Letting the investigator mint `Finding`s.** Would make "rules are data, never hardcoded" false.
- **Accumulating prompt edits / a promotion flow for prompts.** Overrides are per-run and temporary;
  the default changes through a reviewed commit. No drift, no governance burden.
- **Dynamically generated specialists.** Incompatible with rules-as-data and with a mandatory floor.
- **Cross-case / portfolio orchestrator-workers.** The one place dynamic subagents genuinely fit —
  context multiplication over an unbounded corpus. Post-hackathon.

## 23 · Two calibration issues, deliberately out of scope

Surfaced during analysis; not caused by this architecture but visible in any demo.

- **case-006 (drift) scores 0.60 → tier `clear`** — "No scored findings of consequence" on the case
  built to prove drift detection. `DRIFT-BHV-01` is 0.6 against a 0.75 review floor.
- **case-003 (broken cryptographic chain) scores 1.80 → `review`, not `escalate`.**

Both are one-line edits to `registry/`. Left out because they are *policy calibration*, and
rules-as-data means they belong in Stage 11's promotion flow, not in a refactor.
