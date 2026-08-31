# Mandate Supervisor — Project Context

Regulator-side supervision tool for agentic payments, built for NBG's submission to the C:\>DIR Global "Agentic Regulator" Hackathon (build week 1–8 Sep 2026). Continuously checks what an AI payment agent actually did against what it was authorised to do, using its real AP2 mandate chain and transaction history, instead of a policy review filed once a year.

Full problem framing and the submitted concept note live in `docs/concept-note.md` (imported from the original submission — read it if you need the "why," not just the "what"). This file is the "what to build and how," kept current as decisions are made. See `PLAN.md` for the task-by-task build order and current status.

## Fixed — do not redesign without a good reason (already submitted, judges have seen it)

- Workflow: firm's AP2 mandate chain (Intent, Cart, Payment) + transaction logs arrive as a routine submission → deterministic ingestion (not an agent) → Orchestrator dispatches specialists → Risk scoring → Report drafting (human-gated) → sent.
- Four specialists: **Mandate** (Cart within Intent scope, Payment hash matches), **KYA** (credential signature/issuer, delegation chain to a human), **Log** (structuring, counterparty clusters), **Drift** (behaviour vs. own baseline).
- Orchestrator-worker pattern; agents never message each other directly; everything reads/writes typed records to a shared append-only case ledger.
- Rules are data: versioned KYA/mandate registry (active/draft/retired), never hardcoded.
- Policy sandbox: same pipeline, pointed at an editable draft copy of the registry.
- Guardrails promised: human sign-off before anything sends; hash-chained append-only audit ledger; dispatcher-permissioned least-privilege tool access per agent (not prompt-instructed); deterministic ingestion closes off prompt injection at the entry point; drafting agent is grounded (only structured findings, never raw firm text; every claim must cite a real finding).
- Judged against four mandatory guardrails: **human-in-the-loop, auditability, safety/governance, cyber risk.** Every build decision should trace to one of these.

## Architecture decisions (ours, not the judges' — can be revisited with reasoning)

| Area | Decision | Why |
|---|---|---|
| Process shape | Modular monolith, one Python process | Swap-ability comes from typed interfaces + rules-as-data, not network boundaries |
| Language | Python 3.12, `uv`, Pydantic v2, pytest | — |
| Orchestration | **LangGraph** — `StateGraph`, `Send()` fan-out, conditional-edge loops, `interrupt()` human gates | Two real bounded loops: escalation re-dispatch (capped at 1 extra round) when a specialist is ambiguous/under-evidenced; grounding-retry (capped at 2) on the drafting agent |
| LLM | Anthropic API, default `claude-sonnet-5`; escalate specific nodes to `claude-opus-5` only if eval shows it's needed | Don't over-provision model tier up front |
| Checkpointer | LangGraph's SQLite checkpointer, separate table from the ledger — **disposable resume plumbing only** | Never treat it as the audit trail. Delete it → lose only in-flight resumability. Delete the ledger → lose the audit trail. Only one of those is allowed to matter. |
| Ledger | SQLite + SHA-256 hash chain + append-only triggers. **Built after the detection pipeline already works** (deliberately sequenced late — see PLAN.md), not before | A hash chain needs single-writer serialization no matter what DB you pick, so Postgres's concurrency edge doesn't apply here |
| Signatures | Real Ed25519 (`cryptography` lib) on every synthetic mandate | KYA is real crypto, not string comparison |
| Registry | Versioned JSON, typed rule vocabulary, human-gated promotion | — |
| Dispatch | Propose–enforce: LLM proposes a `DispatchPlan`, a deterministic validator enforces a mandatory floor (Mandate+KYA always run; Log+Drift run when history ≥ 30 tx) | Orchestrator genuinely decides; policy guarantees coverage |
| Scoring | Pure function, weights from ruleset, no LLM | Only honest version of "explainable, factor-level scoring" |
| Dashboard | FastAPI + React/Vite/Tailwind/shadcn-ui | One owned, restyleable design system |
| Live agent visualization | **React Flow** for the pipeline graph, generated from LangGraph's own `graph.get_graph()` (never hand-maintained) + **CopilotKit implementing the AG-UI protocol** for the step feed / streamed reasoning / human-approval widget, built on their hooks (`useCoAgent`, `useCoAgentStateRender`, `useCopilotAction`) — **not** their default chat widgets, since this is a case-review product, not a chat app | Open source, MIT-cored, LangGraph-native; stays on-brand instead of sending judges to a separate dev tool |
| Dev-only tooling | LangGraph Studio (`langgraph dev`) for debugging the loops during build. Never demo from it. | Generic dev console, not branded |
| Optional depth layer | Langfuse, self-hosted — first thing cut if short on time | — |
| Deploy | Local docker-compose + `make demo` (reseeded) for the live pitch; Fly.io mirror, reseeded on boot, for a shareable link | No wifi risk in the room; matches "no live rail access" posture already in the concept note |

## Cross-cutting design rules

1. **Deterministic core, LLM only where judgment is genuinely needed.** KYA is 100% deterministic. Mandate is deterministic checks + one contained LLM call (prompt_playback vs. Cart semantic match). Log/Drift are pandas statistics with optional LLM narration of already-computed numbers. Scoring is a pure function. The only agent whose entire output is free text is drafting, and its input is structured findings only — never raw firm text.
2. **Every agent returns a typed `Finding`**, never a print statement or loose dict — this is what makes adding the ledger later (and the UI) additive instead of a rewrite.
3. **Tool permissioning is enforced in code** (a static agent→allowed-tools map + dispatcher), never prompt-instructed.
4. **Injection containment:** deterministic ingestion never lets raw firm text reach an LLM unparsed; the one place firm-authored free text (`prompt_playback`) does reach a model, it's delimited, schema-constrained on output, and separately heuristic-flagged.
5. **Ledger vs. checkpointer:** ledger is authoritative and hash-chained; checkpointer is disposable. Never let the second one accidentally become a second source of truth.

## Repo layout

```
mandate-supervisor/
  schemas/      # Pydantic models: mandates, findings, ledger events, rulesets, graph state
  data/          # synthetic corpus + loader/validator against schema
  ingestion/     # deterministic verify + normalise — no LLM, ever
  registry/      # ruleset JSON, loader, diff, promotion
  ledger/        # append-only store, hash chain, verify CLI, JSONL export
  agents/        # orchestrator, mandate, kya, log, drift, scoring, drafting, grounding
  pipeline/      # LangGraph StateGraph: dispatch, escalation loop, grounding-retry loop, interrupt gates
  api/           # FastAPI: queue, case detail, review actions, SSE/AG-UI stream, registry, sandbox, ledger
  dashboard/     # React + Vite + Tailwind + shadcn/ui + React Flow + CopilotKit
  eval/          # labelled-corpus runner, per-agent P/R, adversarial + injection tests
  docs/
    concept-note.md      # the original submitted concept note, for reference
    phases/               # one focused spec per build phase, written just-in-time as each phase starts
```

## Working across chats

`PLAN.md` is the durable, cross-session task list — check it (and update it) at the start and end of every session, since a session's own internal task tracking does not carry over to a new chat. When starting a new chat for a specific phase, point it at the relevant `docs/phases/NN-*.md` if one exists yet; if not, writing that doc is the first thing to do in that phase's chat, using this file's decisions as the foundation.
