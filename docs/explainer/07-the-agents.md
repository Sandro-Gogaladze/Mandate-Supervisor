# 07 · The agents

## 1 · The rule every specialist obeys

> **A deterministic floor that needs no model at all, plus at most one contained
> language-model call.**

Determinism establishes **facts**. Agents establish **meaning**. The two are
separate outputs, of separate types, on separate lines of the audit trail, so a
supervisor can always see which half of a conclusion was mechanical and which
was judgement.

Concretely, one specialist's pass is:

```
  1. check()   evaluate every computable rule I own, over the runs in scope
               → FACTS  (breach / satisfied / measurement / absent)
  2. assess()  turn those facts into meaning, mechanically
               → floor assessments and data-gap concerns
  3. reason()  ONE model call, over my own facts — never over raw run files
               → judged assessments and observations, every claim citing runs
```

Three consequences worth stating out loud:

- **The model reasons over facts, not over 50 JSON files.** That is what makes
  one call per agent over a whole dossier viable, and it is the direct answer to
  the obvious objection about context loss.
- **A run with no key and no model still produces a complete, reproducible
  deterministic result.** The system degrades to "the rules ran and here is what
  they found," never to nothing.
- **Every judged claim must cite the runs it is about.** This is enforced in the
  schema: an assessment about run-level behaviour that names no run is rejected.

## 2 · The eleven specialists

| | Agent | The question it owns | Failures | Deterministic floor | Its one model call |
|---|---|---|---|---|---|
| **A1** | **Mandate** | Was this within what the human signed? | F39–F50 | 13 `MND-*` rules: caps, scope, chain links, currency, validity window, single-use draw | **Per-line-item intent fidelity** — does this cart answer *this shopper's sentence*? The only source of F49 |
| **A2** | **KYA** | Is authority traceable to a human? | F1–F23 | 34 `KYA-*` rules plus the credential-series pass | Near-name issuer resemblance; whether observed activity fits the declared classification |
| **B1** | **Provenance** | Were the inputs to this decision trustworthy? | F33, F36, F37 | `TEC-02/05/06` and the tool/release checks | Reconcile **four sources that should agree**: agent card · credential · regulator's register · observed tool calls — and name the odd one out |
| **B2** | **Injection** | Was it manipulated by what it read — and **through which channel**? | F32, F35 | Regex triage over four text channels plus tool-schema-hash comparison | Did the agent actually **act** on it, and through which channel — because the supervisory question is where sanitisation is leaking |
| **C1** | **Counterparty** | Who received this money? | F51–F58 | Payee against merchant registry, sub-merchant disclosure, concentration statistics, decline timelines | Is this payee what it appears to be (name/account mismatch, fronting), and do the declines cluster into probing |
| **C2** | **Consent & Harm** | Was the human actually there, and is the consumer worse off? | F24–F31, F38 | `rendered_values` against the signed cart, ceremony scope, consent supersession | **Value for money against `selection_context`** — the detectable signature of merchant-bias tuning |
| **D1** | **Log** | What does the history reveal? | F59–F64, F66 | pandas statistics: structuring, velocity, roundness, off-hours, concentration | Narrate already-computed numbers; judge whether a cluster is benign |
| **D2** | **Drift** | What changed, **and when did it start**? | F65 | Baseline/comparison split, change-point detection | Which `change_log` event sits at the onset boundary |
| **E1** | **Control Assurance** | Did the firm's own controls work? | F70–F73 | 15 `CTL-*` rules | Classify posture: **absent / failed / bypassed / ineffective / effective** |
| **E2** | **Systemic** | What is true across the whole portfolio? | F57, F67, F69 | Shared-payee, model-monoculture and shared-digest sweeps across dossiers | Is this concentration meaningful, or ordinary popularity? |

### A few of these deserve unpacking

**Mandate's model call** is the one that justifies the whole data model. It
receives, per run, the shopper's sentence and the cart's line items, and returns
a verdict per run. Code does the enforcing: a `run_id` the model invents is
dropped and logged; a run it declined to judge is recorded as `inconclusive`
rather than silently passed; consistent runs roll into one `clear` assessment
citing them all. And it is deliberately **independent** of the floor's line-item
injection heuristic — two mechanisms, so a manipulated semantic check does not
leave injection detection with a single point of failure.

**Control Assurance is the one that makes this a supervision tool.** Every other
agent asks whether the agent misbehaved. This one asks whether the firm's
declared controls did their job — which is the question a supervisor is actually
empowered to act on. Its posture classification is *computed, not judged*:

| Posture | Means |
|---|---|
| **absent** | The mandate creates a risk and no declared control addresses it |
| **failed** | A control rejected the action and the payment settled anyway |
| **bypassed** | A control fired and a **named person** overrode it into settlement |
| **ineffective** | A control recorded `passed` on a run where its own risk breached |
| **effective** | A control fired and held |

**Systemic is the only specialist whose question cannot be asked of one
submission.** Its hard part is not finding shared counterparties — most are
shared, because popular retailers are popular. It is separating genuinely
suspicious overlap from ordinary commerce, which is exactly why the corpus was
built with a deliberately ordinary overlap between its two dossiers.

## 3 · Two ordering constraints that are not negotiable

**1 · Control Assurance runs after the peer fan-out, never inside it.** Its rule
`CTL-EFF-01` asks whether a control that *should* have triggered did — which
means knowing that the risk materialised, which is somebody else's finding.
Given no peer findings it must stay silent, and there is a test asserting
exactly that. It learns which risk materialised purely from the peers' breach
facts, through each rule's own `failures` declaration — no agent-to-agent
message required.

**2 · Agents never talk to each other.** A specialist that needs more evidence
uses its own permitted tools. A question that needs a *different* specialist
becomes the officer's next round. **Iteration replaces recursion.** This is what
keeps a review bounded, replayable, priced, and auditable — and it is why the
system cannot fall into the agent-loop failure mode where nobody can say
afterwards why anything happened.

## 4 · The six support agents

| Agent | Role | Model? |
|---|---|---|
| **Orchestrator** | A dispatcher that speaks, never an analyst. Decides which skills to run, briefs each, and reports what came back | 1 call per round (none on a first pass) |
| **Investigator** | A tool-using loop answering one named officer's question | Yes, bounded |
| **Critic** | Checks that quoted numbers actually appear in the evidence the agent was given | **No — deterministic** |
| **Synthesizer** | Links findings that are one event seen by several detectors | Yes |
| **Drafting** | Writes the supervisory report | Yes |
| **Grounding** | Verifies every claim in the report cites a real finding | **No — deterministic** |

### The orchestrator has no opinion

It is structurally incapable of stating a verdict about the firm: its output is
a forced-shape routing tool call with no field in which a judgement could be
expressed. On a **first pass it makes no routing call at all** — code dispatches
every review skill, because a first pass is comprehensive by policy and routing
is not a question worth a model call. On later rounds it judges the officer's
question against every fact round 1 produced, **narrows the context** to the
runs the question concerns, and dispatches only what is relevant. It names
skills and record items by id; code resolves both, and unknown ids are dropped
and logged.

### The investigator's bargain

It is the one agent with **callable tools** — read-only lookups it can iterate
over freely. The trade that makes that safe: **it may never mint a finding.**
Its output is an answer plus observations, which are unscored, uncitable by the
drafting agent, and surfaced to the human who asked. If the officer wants one of
its insights turned into a scored verdict, a specialist is dispatched and a rule
decides. Its loop is bounded in the node's code, not in the prompt — a runaway
model hits the budget wall, is told to answer with what it has, and the full
trail of every call it made rides along with the answer.

### Two deterministic checkers, on purpose

The **critic** and the **grounding check** are both pure code. Neither is a
second model judging the first, which would only hallucinate alongside it. The
critic asks: *did this agent quote numbers that actually appear in the evidence
it was given?* — answerable by value matching against the recorded dispatch
context. It is deliberately conservative about which numbers count (decimals of
any size, integers ≥ 100) so that "three payments" is not flagged as an
unsourced figure. And its failures are **recorded and surfaced, never
suppressed**: a false negative in the critic must not delete a real finding, so
the officer sees the flag and judges.

## 5 · Skills, not a routing function

Each specialist exposes one or more **skills** in a registry: a skill id, the
agent that serves it, a description written for a model reader (what it answers,
not how it works), what it produces, and which context blocks it needs.

Adding a twelfth specialist therefore means adding a registry entry, not editing
a routing function. And because a first pass selects every review skill by code
policy, the coverage of a first pass is a property of the system rather than of
a prompt.

## 6 · What each agent is allowed to touch

Tool access is a **static agent → allowed-tools map enforced in code**, checked
when a tool definition is handed out *and* re-checked on every call. It is not
described to the model in a prompt; a model that decided to call something else
would simply be refused.

Every tool in the system is **read-only, deterministic and non-LLM**. None
writes to the ledger, mutates a rulebook, or makes a model call. And none
returns line-item descriptions, the user prompt, or a tool-result excerpt —
the firm-authored free text where an injection would live. Where a result does
contain firm-authored strings (a counterparty name, a firm name), they are
delimited exactly as the specialists delimit merchant text. The injection
surface stays closed by construction rather than by instruction (document 14).
