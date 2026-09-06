# 14 · Safety and guardrails

The hackathon judges this work against four mandatory guardrails:
**human-in-the-loop, auditability, safety and governance, cyber risk.** Every
build decision traces to one of them. This document collects the answers in one
place.

## 1 · Human-in-the-loop

**Two gates, both requiring a named person, both on the ledger:**

| Gate | What it guards |
|---|---|
| **Draft → sent** | No supervisory report reaches a firm without a named human approving, editing, or blocking it |
| **Draft rulebook → policy** | No rule change takes effect without a named person, a written rationale, and the sweep that justified it attached as evidence |

The first is enforced by **graph topology** — the pipeline physically cannot
reach a "sent" state without passing through the interrupt, and the decision is
validated server-side so a malformed client payload re-interrupts rather than
being accepted.

Beyond the gates, the design keeps the human in the analytical loop rather than
just at the end of it: the officer asks questions in plain language, and each one
runs a real, recorded, bounded review round with a narrowed scope. And every
disposition is a **recommendation** until a person records a decision.

There is also a manual stop on any run.

## 2 · Auditability

Covered in full in document 13. In summary: a hash-chained, append-only SQLite
ledger with no update or delete method, SQL triggers as defence in depth, a
global chain so tampering anywhere breaks verification everywhere, a mandatory
typed actor on every event, per-case JSONL export, and a verifier exposed both
as a CLI and as an API endpoint.

Three properties worth repeating because they are unusual:

- **Case status and risk score are computed from events, never stored** — a
  stored value can disagree with the record; a derived one cannot.
- **The exact context each agent received is recorded**, so a review is
  reproducible and an agent's quoted numbers are checkable against something.
- **"Clearing" a review is itself an event.** Nothing is ever deleted.

## 3 · Prompt injection — the containment story

This is the guardrail the product takes most seriously, because a supervisory
tool that can be talked into a false clean bill of health is worse than no tool.

### 3.1 · The entry point is code, not a model

Intake is deterministic. It parses, verifies signatures and hash chains, checks
the run index, and resolves registries. **No firm-authored text reaches a model
unparsed at the entry point**, because no model is present at the entry point.

### 3.2 · Free text reaches models in exactly three places, all contained

| Where | Contained how |
|---|---|
| Mandate's intent-fidelity call (line-item descriptions, the agent's attestation) | Wrapped in explicit untrusted-text delimiters; the system prompt states they are data; output is schema-constrained by a forced tool shape; every run id returned is validated against the runs shown |
| Injection's own call (the four text channels it triages) | Same delimiters, plus the channel it names must be one the deterministic floor actually observed for that run |
| Consent's value-for-money call (alternative descriptions) | Same delimiting |

The delimiter is literal and unambiguous — `<<<UNTRUSTED_TEXT>>> … <<<END_UNTRUSTED_TEXT>>>`
— and applied by code as the evidence bundle is composed, not by the model
choosing to be careful.

### 3.3 · The drafting agent never sees firm text at all

The one agent whose entire output is free prose has the **most restricted input
in the pipeline**: typed findings, observations, the dispatch plan, the score.
The firm's name and the case id are the only submission-derived strings it
receives. There is nothing for an injected instruction to ride in on.

### 3.4 · Tools cannot leak the injection surface

Every tool in the system is read-only, deterministic and non-LLM. None returns
line-item descriptions, the user prompt, or a tool-result excerpt. Where a
result unavoidably contains firm-authored strings — a counterparty name, a firm
name — they arrive delimited exactly as the specialists delimit merchant text.

### 3.5 · Detection is doubled on purpose

Mandate's semantic check and the floor's line-item injection heuristic are
**two independent mechanisms**. A manipulated semantic check does not leave
injection detection with a single point of failure.

### 3.6 · The trust boundary is about authorship

Regulator-authored text — a case officer's re-analysis instruction — *is*
allowed to reach a specialist's prompt as free text, delimited, with the output
still schema-constrained. **Firm-submitted text never is.** The boundary is
drawn around who wrote the words, not around where they end up.

## 4 · Least-privilege tool access

The concept note promised that tool access is *dispatcher-permissioned, not
prompt-instructed*. In the code that is:

- A **static agent → allowed-tools map**.
- Enforced when tool definitions are handed out — an agent is never even shown a
  tool it may not use.
- **Re-checked on every call**, so permissioning holds at both ends.
- Every tool read-only, deterministic, non-LLM. None writes to the ledger,
  mutates a rulebook, or makes a model call.

A model that decided to call something outside its map would simply be refused.
It is not asked to behave.

## 5 · Hallucination

Three independent mechanisms, none of which is a model checking a model:

| Mechanism | What it catches |
|---|---|
| **The grounding validator** (deterministic) | A report claim citing a finding that does not exist; a section with no citation; **a finding silently dropped from the report**; an observation smuggled into cited prose |
| **The critic** (deterministic) | An agent quoting a number that does not appear in the evidence it was given |
| **Schema enforcement** | An assessment about run-level behaviour naming no run; an invented run id; a severity lowered below the rulebook floor; a correlation citing a finding that does not exist |

The critic's failures are **surfaced, never suppressed** — a false negative in
the critic must not delete a real finding, so the officer sees the flag and
judges.

And observations — unverified model hunches — are excluded from the score **by
the scoring function's signature**, not by convention. It is the strongest
available way to keep "never scored" true forever.

## 6 · False positives and bias

- **Scoring is a pure function with no model in it.** Same findings, same score,
  every time; the answer to a challenge is a printable derivation.
- **Every rate is shown with its n**, and thin evidence is labelled as
  insufficient rather than given a number that invites trust.
- **`inconclusive` is a first-class verdict.** An agent that cannot decide says
  so, scores nothing, and routes to a human — instead of being forced to guess
  in one direction.
- **Confidence multiplies severity**, so an uncertain finding is priced as one.
- **A human reviews before anything reaches a firm.**

## 7 · Over-reliance

No action leaves the system without named human sign-off, and rulebook promotion
requires a separate human decision. The policy file declares itself
`prototype_uncalibrated`, and that status travels with every recommendation. The
console states numbers from the deterministic layer verbatim and never invents
severity language of its own.

## 8 · Data sensitivity and cyber risk

- **Synthetic data only; no live rail access.** By design and by declaration.
- **A dossier is verified at the door** — signatures, chain links, index digests
  — and a submission that contradicts itself is rejected with the reason.
- **The graph reads the case from the ledger by id**, never from a
  client-supplied path.
- Any `ground_truth.json` in an uploaded zip is **stripped on ingest**, so a
  submission cannot smuggle in its own answer key.
- Payment instruments appear masked; the corpus carries no real identifiers.

## 9 · The honest limits

Stated here rather than discovered later:

- Facts are mechanical results **about submitted evidence**. They are not proof
  that an operator's self-attestation is true.
- **A content index cannot establish that unfiled executions never existed.**
- **No regex hit is not proof of no injection.** Triage narrows; it does not
  clear.
- Thresholds are prototype parameters. Calibration is future work, and the
  system says so about itself.
