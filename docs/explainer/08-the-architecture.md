# 08 · The architecture

How a review actually runs, from a zip arriving to a decision on the record.

## 1 · Shape

One Python process — a **modular monolith**, not microservices. That is a
deliberate reversal of the concept note, and the reasoning is worth stating
because it comes up: the swap-ability the concept note wanted (a different
mandate protocol, a different rulebook, a different specialist) comes from
**typed interfaces and rules-as-data**, not from network boundaries. Splitting
the same code across HTTP would have bought deployment independence nobody
needs, at the cost of a hash-chained ledger that now needs distributed
single-writer serialisation. The interfaces are drawn exactly where the
microservice boundaries would have been, so the split remains available later.

| Layer | Technology |
|---|---|
| Core | Python 3.12, Pydantic v2 for every typed record |
| Orchestration | **LangGraph** — state graph, fan-out, conditional edges, `interrupt()` for the human gate |
| Models | Anthropic API, default `claude-sonnet-5` |
| Ledger | SQLite, SHA-256 hash chain, append-only |
| Resume plumbing | LangGraph's SQLite checkpointer, in a **separate** database |
| API | FastAPI, with a streaming endpoint per review |
| Console | React + Vite + Tailwind + shadcn/ui + React Flow + CopilotKit (AG-UI protocol) |

## 2 · The ledger is authoritative; the checkpointer is disposable

This distinction is enforced by putting them in different databases, and it is
the kind of thing that quietly ruins audit systems when it is not enforced:

- **Delete the checkpointer** → you lose in-flight resumability of a paused run.
  Nothing else.
- **Delete the ledger** → you lose the audit trail.

Only one of those is allowed to matter. The checkpointer never becomes a second
source of truth, and no projection reads it.

## 3 · The pipeline

```
INTAKE — code only, zero model calls
  verify every signature and every chain link
  verify the run index against the actual file digests
  resolve all six regulator registries
  compute the shared statistics ONCE
  record which submission blocks are present
  ──────────────────────────────────────────────►  the EVIDENCE PACK
  No rules evaluated here beyond the eight cryptographic ones.
  Rules belong to agents.
        │
        ▼
ORCHESTRATOR
  first pass : code dispatches every review skill. No model call.
  later      : judge the officer's question against every fact round 1
               produced, NARROW the context to the runs it concerns,
               dispatch only what is relevant
        │
        ├──► mandate     ├──► counterparty  ├──► log
        ├──► kya         ├──► consent       ├──► drift
        ├──► provenance  ├──► injection     └──► investigator
        │
        │   EACH AGENT, ONE PASS:  check() → facts
        │                          assess() → floor assessments
        │                          reason() → one model call → judged assessments
        ▼
CONTROL ASSURANCE   (consumes the peers' facts; cannot be dispatched directly)
        ▼
SYNTHESIS — sequential
  critic (deterministic) → synthesizer → score → authorisation recommendation
        ▼
OFFICER reads the case ──► asks a question ──► ROUND 2 ──┐
        └────────────► REPORT ⇄ GROUNDING ──► HUMAN GATE ◄┘
```

Everything each node produces — every fact, every assessment, every dispatch
context, every finding, every score — is appended to the ledger **as it is
produced**, not at the end.

## 4 · Intake, in detail

Intake is the security boundary, and it is deliberately not an agent, because
every question it answers is deterministic:

1. **Verify.** Every Ed25519 signature on every credential, delegation link,
   Intent, Cart and Payment. Every hash link between mandates in every chain.
2. **Verify the attestation.** Every run index digest against the real file; no
   run missing, none unlisted.
3. **Resolve.** All six regulator registries — institutions, operators, agents,
   merchants, tools, issuers, model blocklist, keystore.
4. **Compute once.** Counterparty profiles, concentration, baseline/comparison
   splits, decline timelines, roundness and off-hours rates.
5. **Record presence.** Which submission blocks exist at all.

Point 4 matters more than it looks. The same counterparty profile is read by
Counterparty, Log and Systemic; the same baseline split by Drift and the
investigator. Computed once, recorded once, cited everywhere **by the same
numbers** — which is also what makes it possible for the critic to check an
agent's quoted values against something.

A submission that cannot be parsed at all **raises** — garbage is a different
failure class from a submission with something wrong in it, and the second comes
back as facts rather than as an exception.

## 5 · Review scope — one call per agent, whole dossier

**Round 1 is whole-dossier per agent.** Each specialist gets one model call over
the entire dossier and produces one coherent account of that agent's behaviour
across all runs, **citing specific runs**.

Why this shape, and not per-run:

- **The model reasons over facts, not raw runs.** The deterministic floor runs
  per run first and produces a compact fact table. "The whole dossier" is 50
  runs' worth of *facts*, not 50 JSON files.
- **Cross-run failures stay possible.** Cumulative caps, concentration,
  structuring, drift, double-draw — these are properties of the *set*. Asked per
  run they produce the same answer fifty times, or fifty partial ones.
- **~11 model calls per review, not ~550.** Cost and latency are a design
  constraint, not an afterthought.
- **Every assessment must cite its runs**, enforced in the schema. Without that
  rule, a whole-dossier call produces claims nobody can check.

**Round 2 is narrowed.** When the officer wants depth on one run, the
orchestrator composes a context containing only that run and dispatches only the
relevant specialists. Findings on untouched runs are preserved; new assessments
**supersede** old ones rather than overwriting them, and both stay on the
ledger.

## 6 · Two bounded loops, and only two

Autonomy in this system is deliberately narrow. There are exactly two loops, and
both have hard caps enforced in code:

- **Escalation re-dispatch**, capped at one extra round, when a specialist's
  result is ambiguous or under-evidenced. On that round a re-dispatched
  specialist may contribute only **observations**, never assessments — its
  rule-backed verdicts were decided in the first round and cannot be quietly
  revised.
- **Grounding retry** on the drafting agent, capped at two. The grounding
  problems are fed back verbatim into the retry prompt.

Everything else that looks like iteration is the **officer asking another
question**, which is a new, recorded, bounded run.

## 7 · State, and why the reducers are not ordinary

The graph's state carries the dossier, the evidence pack, the run scope, and the
accumulating facts, assessments, findings and observations. Those four use
**dedup-aware reducers keyed on deterministic ids**, not simple list
concatenation.

That is not theoretical tidiness. LangGraph re-executes a node from scratch on a
transient error — a flaky model call inside a specialist's reasoning pass, after
its deterministic floor has already computed real facts. Simple concatenation
has no way to know a retried node's output is a repeat. Because fact and
assessment ids are deterministic (`<case>:<rule>[:<run>]`), the reducers do, by
identity. Eight specialists finishing simultaneously in a fan-out and one of
them retrying is the real concurrent case, and it must not double-count a breach
in the score.

The same discipline applies to the ledger: appends serialise through a per-path
process lock plus an immediate transaction, with the sequence re-read inside it,
so a fan-out cannot fork the hash chain.

## 8 · Runs are bounded; the case is not

Each graph starts, does one job, appends what it produced, and exits. **No graph
is held open.** The case lives in the ledger, not in a paused process — a case
can be open for a week without anything running.

The single `interrupt()` left in the system is the human gate at the end of the
*drafting* run. It guards an **artifact** (a report cannot issue without a named
decision — minutes, which is what a checkpointer is for), never the case (open
for a week — a ledger state). That distinction is what keeps process state and
regulatory state from being confused.

Run kinds on the record: `triage` for a first pass or a directed re-analysis,
`investigation` for an officer's question, and `drafting` for a report. There
is no separate portfolio kind: Systemic reviews across the portfolio inside the
first pass, and its findings are recorded on every case they span.

## 9 · What is guaranteed by code rather than by prompt

This list is the honest answer to "how do you know the model behaves?" — the
answer is that these do not depend on the model behaving:

| Guarantee | Where it lives |
|---|---|
| Tool permissioning per agent | A static map, enforced when tools are handed out **and** re-checked on every call |
| The evidence floor an agent sees | Context composition code, not a prompt instruction |
| Observations never affect the score | The scoring function's signature — it cannot receive them |
| Every report claim cites a real finding | The deterministic grounding validator |
| Quoted numbers appear in the evidence | The deterministic critic |
| Correlation ids resolve to real findings | The synthesizer's validation |
| Severity may be raised, never lowered | A schema validator on the assessment |
| The human gate cannot be skipped | Graph topology |
| Control Assurance runs after its peers | Graph topology |
| First-pass coverage | Code policy, with the complete dispatch plan recorded |

## 10 · The live view

The console does not poll a database and guess. The review endpoint streams the
graph's own events over the **AG-UI protocol** (CopilotKit), and the pipeline
graph the console draws is generated from LangGraph's own graph structure —
never hand-maintained, so a diagram cannot drift from the pipeline it depicts.

One performance decision is visible in the design: the stream carries an agent's
non-fact events, fact **counts**, and the ledger sequence range — not every fact
twice. The console reads facts from the ledger once a run finishes. That took a
Kestrel review's stream from 8.4 MB to 0.8 MB, and it is why the supervision map
stays responsive while eight specialists work at once.
