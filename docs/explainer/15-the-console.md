# 15 · The console

The console is where a case officer does the work. It is not a chat window and
not a developer tool — it is an **operate-mode product**, where scanability,
consistency and earned familiarity outrank expression.

## 1 · What it has to do

Three jobs, and the design follows from them: let an officer **see a submission
in full** without reading JSON, let them **watch and interrogate a review** as it
happens, and let them **sign a decision** with the whole derivation in front of
them. A fourth surface, the policy sandbox, serves the other user entirely.

## 2 · The sections

| Section | What it is for |
|---|---|
| **Overview** | The state of supervision at a glance: submissions, where each sits, what needs attention |
| **Case queue** | The submitted dossiers, prioritised, each with its disposition and headline signals |
| **Case review** | The main workspace — one dossier, end to end |
| **Portfolio** | What is true across dossiers: shared counterparties, model monoculture, shared injection payloads |
| **Policy sandbox** | The rulebook workbench (document 12) |

## 3 · The case review workspace

### The specialist turns

The review reads as **a transcript of eleven specialists working**. One
collapsible block per agent, in dispatch order, with live status. An agent's step
reads *"Thinking…"* while its call is open and *"Thought for 12s"* with the full
working once it has ended; facts and verdicts appear as their events land on the
record.

There is deliberately **no token streaming**. Watching a model type is not
supervisory information, and it makes the interface feel like a chat product
rather than a case system.

### A renderer per payload type

Fact cards, assessment cards, absent notices, tool-call rows, control-posture
badges, correlation links, portfolio findings — each has its own renderer,
selected from a registry keyed by type, with a deliberately **loud fallback**
that names any unrendered type. Gaps show up in review rather than silently.

**Raw JSON is not a fallback; it is a bug.** An earlier version of the console
stringified whatever it received into a `<pre>` block, and no amount of
restyling would have fixed that, because the problem was the absence of
renderers rather than their appearance.

### Evidence cited, never dumped

Evidence appears as a citation —

> `RUN-2026-0811-0043 · cart_total $708.00 · KST-CTL-001`

— which expands to the underlying fact and links straight to the run.

### `absent` is visible

*"Consent ran 7 rules: 5 satisfied, 2 absent — no `rendered_values` in this
submission"* renders as a supervisory fact, because it is one. Silence is what an
earlier design produced there, and silence is indistinguishable from "everything
was fine."

### The failure list

A specialist's headline output is *which catalogue failure, and where* —
`F42 on RUN-…-0043`. The full chain (narrative, verdict, cited facts, rule and
rulebook version) stays one disclosure away in the turn that owns it. A reviewer
scanning a case wants the headline; the provenance is what they open when a row
earns their attention.

### The run list and run detail

Runs are sortable by verdict, and **the clean ones are visibly the majority**,
because they are the substance of an authorisation rather than background noise.
Run detail shows one AP2 chain end to end: the shopper's sentence, the Intent
Mandate, how the cart was constructed, the consent ceremony, the signed cart, the
payment, and the firm's control outcomes.

### The question box

The officer asks in plain language. The question is recorded, the orchestrator
narrows the scope to the runs it concerns, the relevant specialists re-run, and
the answer arrives with the same citation discipline as everything else. New
assessments supersede old ones and both stay on the record.

### The disposition

The authorisation panel shows the disposition **with its full factor
breakdown** — every hard gate, every adequacy gap, every weighed factor with its
severity floor, assessed severity, confidence and de-duplication, the per-run
results, and the coverage counts. Signing it requires a name.

## 4 · The supervision map

A live pipeline graph, generated from the orchestration graph's own structure —
**never hand-maintained**, so the picture cannot drift from the pipeline it
depicts.

Nodes carry live state: idle · dispatched · running · returned. The settled
states are deliberately three rather than two:

| State | Means |
|---|---|
| **returned · clean** (green) | Nothing found |
| **returned · findings** (amber) | A breach or a concern |
| **returned · unresolved** (dashed) | The only open items are unjudged rules — a facts-only pass, or a model call that timed out |

That third state exists because "we did not judge it" must never render as
"clean." One click from a node jumps to that agent's turn.

## 5 · Design language

The visual world derives from the logo: institutional navy, the blue a payment
card lifts to, and the teal of a verification check, on cool near-white paper,
with a fine blueprint-grid motif standing for the drafting table a regulator
works at. The mark itself is a payment card with an agent's face on it — the
thing being supervised.

A few rules that keep it feeling like an instrument rather than a dashboard
template:

- **Every grey leans navy.** Nothing warm anywhere; shadows are tinted from the
  navy ink rather than gray-black.
- **The one expressive element is the dark sidebar rail.** Everything to its
  right stays calm.
- **Status colours are signal, never decoration**: amber = machine working,
  green = complete or clean, red = flagged. "Clean" is the logo's own check
  teal, enforced centrally so the success hue cannot drift.
- **Each specialist owns one identity hue**, used consistently everywhere that
  agent is named.
- **Mono type is strictly for data** — case ids, rule ids, amounts, timestamps,
  versions — never as a technical costume on prose. All numerals are tabular.
- **Motion conveys state only.** 150–250ms, no bounce, no page-load
  choreography.
- **Empty states name the action that fills them.**
- **The UI states numbers from the deterministic layer verbatim** and never
  invents severity language of its own.

## 6 · Submission intake

A dossier is a directory, not a file. It is uploaded as a zip, and **verified at
the door**: every index digest matches its file, no run missing, none unlisted,
every signature verifies. A submission failing any of those is rejected with the
reason shown, because accepting an attestation that contradicts itself would
destroy the point of having one.

## 7 · Why not a chat widget

The console is built on CopilotKit's hooks implementing the AG-UI protocol — the
live agent state, the step feed, the human-approval widget — but deliberately
**not on its default chat components.** This is a case-review product, not a chat
app. The officer's questions are one affordance inside a case file, not the
primary interface.

Likewise, LangGraph Studio is used during development to debug the loops, and
**never demoed**: it is a generic developer console, and the product is a
supervisory instrument.
