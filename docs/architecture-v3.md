# Architecture v3 — facts and meaning

Branch `feat/supervision-architecture-v3`. Supersedes `architecture-v2.md` §14–18 (the run model and
agent set); v2 §5 (where guarantees live) survives, extended.

Companions on this branch: `coverage-model.md` (73 failures) · `kya-ruleset.md` (57 rules) ·
`kya-and-the-sandbox.md` (positioning).

---

# Part I — The governing principle

> **Determinism establishes facts. Agents establish meaning.**

That one line settles every "should this be a rule or an agent?" argument in the rest of the document,
and it is a sharper split than either extreme.

**A deterministic check does not produce a verdict. It produces a fact.**

- *"Cart total is ₾1,289. The Intent's per-transaction cap is ₾350. Excess ₾939."*
- *"The credential's signature verifies. The issuer was revoked 2026-06-01. The credential issued 2026-07-03."*
- *"Three payments to one counterparty within 6 hours: ₾2,900, ₾2,850, ₾2,950. Reporting threshold ₾3,000."*

Those are true, reproducible, cheap, and injection-proof. They are also **not supervision.** Nothing
there says whether the breach was deliberate, whether it connects to anything else, how serious it is
in this firm's context, what else deserves a look, or whether this is a pattern nobody has written a
rule for.

**That is the agents' job**, and it is the part a rules engine structurally cannot do:

| An agent can | A rule cannot |
|---|---|
| Judge whether a breach reads as error, negligence or design | only that it occurred |
| Form a hypothesis and go get evidence for it | only evaluate a fixed expression |
| Connect a credential reissue on 11 July to a counterparty appearing on 12 July | span two domains it wasn't written for |
| **Find what no rule covers** — attacker #74 against a 73-item catalogue | catch only what was written down |
| Invent an attack that would evade this firm's declared controls | generate anything |
| Explain to an officer what this is a case *of* | produce a boolean |

## What this changes from the previous draft

The previous version of this document let deterministic checks emit `pass`/`fail` verdicts for 55 of
57 rules. That is a rules engine with two LLM calls attached — defensible, and much less capable than
what the problem needs. **Rule evaluation still runs deterministically and unconditionally; its output
is now a `Fact`, not a verdict.** Agents assess facts.

## Where determinism stays absolute

These are the **trust anchors**. Nothing below moves, and none of them is where judgment belongs:

Cryptographic verification · the hash-chained ledger · rule *evaluation* (the arithmetic and the
lookups) · the score floor · grounding validation · the critic · tool permissioning · the human gate ·
ingestion.

**Everything a firm could challenge in a hearing is deterministic. Everything requiring supervisory
judgment is an agent.** That is the honest version of both claims.

---

# Part II — Four tiers

```
  TIER 0   DETERMINISTIC CORE                                        no agents, no model
           verify · resolve registries · compute statistics · evaluate 57 rules
           ──────────────────────────► FACTS  (+ evidence pack, digest, recorded)
                                        │
  TIER 1   ORCHESTRATOR                  │      plans · briefs · routes · never judges the case
           reads facts, plans the review, dispatches with real briefs
                                        │
  TIER 2   SPECIALISTS  (8 domains, parallel)     assess facts · may spawn subagents
           mandate · kya · provenance · injection · counterparty · consent · log · drift
                                        │
                              ┌─────────┴─────────┐            Send() fan-out over a
  TIER 3   SUBAGENTS  ────────┤ one question each ├──────────  dynamically generated
           spawned by a specialist, narrow brief, own tool budget, answer to the parent
                                        │
           CROSS-CUTTING     hunter · synthesizer · critic · control-assurance
                                        │
                             score ──► draft ⇄ ground ──► human gate
```

## Tier 0 · The deterministic core — machinery, not an agent

Runs on every submission, always, before any model is called. Verifies signatures and chains, resolves
every registry, computes every statistic, and evaluates all 57 rules.

Output is an **evidence pack** plus a set of `Fact`s. Recorded once with a digest, so determinism is
provable: same submission → same pack → same digest.

**It is model-free, which is the point.** Zero API cost, zero injection surface, and roughly half the
rulebook resolves here. It is also what makes the agents' job tractable — they reason over
established facts rather than raw firm data.

## Tier 1 · The orchestrator — plans and briefs, never judges

Sees the pack summary **and every fact the core produced**, then decides:

```python
class ReviewPlan(BaseModel):
    dispatches: list[Brief]        # {agent, depth, focus, facts_attached, extra_blocks}
    hypothesis: str                # what it expects this case to be — scored later by eval
    open_questions: list[str]      # things no specialist owns → the hunter
    rationale: str
    message_to_officer: str
```

**Because the facts already exist when it plans, this is a real decision.** *"Cap breached by ₾939 and
the injection heuristic fired on line item 0 — brief Injection deep with the attestation attached, and
tell Mandate to focus on line-item provenance rather than the cap, which is already established. The
transaction statistics are unremarkable; Log standard. Drift has 7 transactions, skip."*

Compare v2, which saw `{firm, purpose_category, transaction_count}` and re-derived from one integer
what a floor already knew.

**What it may not do**, all enforced in code: judge the case (its schema has no verdict field) · go
below the evidence floor (it names blocks, never authors them) · suppress a fact · skip a mandatory
specialist · rewrite a prompt.

## Tier 2 · Specialists — assess, and delegate

Eight domain assessors, running in parallel. Each receives its domain's facts plus the orchestrator's
brief, and returns:

```python
class SpecialistReport(BaseModel):
    assessments: list[Assessment]    # meaning attached to facts — see Part III
    sub_questions: list[str]         # what it wants a subagent to establish
    open_notes: list[Observation]    # noticed, no rule covers it
    confidence: Literal["certain", "probable", "possible"]
    reasoning: str
```

A specialist is **not** a rule evaluator — the core already did that. It is the domain expert reading
the results: is this deliberate, how serious here, what does it connect to, what do I still need?

## Tier 3 · Subagents — one question each

When a specialist can't settle something in one pass, it **names sub-questions** and the graph fans out
one subagent per question via LangGraph's `Send()`.

> This is where `Send()` finally earns its place. `architecture-v2.md` §9 noted honestly that v2 used
> conditional edges instead, because the branch set was a subset of four fixed nodes rather than a
> generated list. **A dynamically generated list of sub-questions is exactly the case `Send()` exists
> for.** That loop closes here.

Each subagent gets: one question, a scoped slice of the pack, its own tool budget (3), and a typed
return. **It never writes to the ledger** — it answers its parent, and the parent owns the resulting
assessment. Accountability stays with the named specialist.

Worked example — KYA sees a five-deep delegation chain:

```
kya ──Send()──► sub: "does BRIDGE-CO's own credential grant the authority it passed to the agent?"
    ──Send()──► sub: "has holder SVANETI-IMPORT appeared in any other case's chain?"
    ──Send()──► sub: "is 'Kavkasia Credential Services' the accredited issuer, or a near-name?"
```

Three narrow questions, three cheap parallel agents, three typed answers, one assessment written by
KYA. Depth capped at **one** — a subagent cannot spawn subagents.

## Cross-cutting agents

### `Hunter` — the agent that exists because rules can't cover the unknown

**The strongest argument for AI in this system.** The failure catalogue has 73 entries. A real attacker
invents #74. No rule will ever catch it, because rules only catch what someone already wrote down.

The Hunter gets the **entire** evidence pack and **all** facts — no domain boundary — and is asked one
question: *what is happening here that no rule covers?* It returns `Observation`s only: never scored,
never citable, surfaced to the officer.

**And its output feeds the registry.** An observation recurring across cases is a candidate rule. That
is a real loop from discovery to policy — the mechanism by which the rulebook grows from 57 without
anyone having to guess in advance. It is also, concretely, the thing that makes the policy sandbox
have inputs.

### `Synthesizer` — cross-domain connection

As v2, but now over **full assessments with their facts**, not summaries. That is what lets it say
*"the counterparty first appears on 12 July; the credential was reissued on 11 July"* — a connection
spanning KYA and Counterparty that neither owns.

### `Critic` — deterministic, no model

Every `evidence_ref` in every assessment must resolve against the facts the agent was actually given.
A second model judging the first would hallucinate alongside it; reference resolution is mechanical
and therefore trustworthy.

### `Control Assurance` — the firm's controls

Consumes all assessments plus the `controls` block, emits one `ControlAssessment` per finding. **A tail
node by necessity** — `CTL-EFF-01` asks whether a control that should have triggered did, which
requires knowing what tripped.

### `Red Team` — adversarial, and genuinely agentic

Given the mandate's parameters and the firm's *declared controls*, invent attacks that would evade
them. **An LLM is far better at this than templates** — the previous draft had deterministic case
generation, which only ever finds the attacks you already thought of, and therefore finds nothing new
by construction. Output is a `ControlProbeReport`: generated cases, which declared controls would have
missed them, and why. Never touches a live rail.

---

# Part III — Facts, assessments, and how severity works

## `Fact` — deterministic, from Tier 0

```python
class Fact(BaseModel):
    fact_id: str
    case_id: str
    rule_id: str | None                       # the rule that produced it, when there is one
    kind: Literal["breach", "satisfied", "measurement", "absent"]
    statement: str                            # "Cart total 1289.0 exceeds cap 350.0 by 939.0"
    values: dict[str, Any]                    # {cart_total: 1289.0, cap: 350.0, excess: 939.0}
    refs: list[EvidenceRef]
```

`satisfied` facts matter: they are how a clean case becomes *provably* clean rather than merely silent,
and they give the eval harness true negatives, which is what makes a real false-positive rate
computable. `absent` is a rule that could not be evaluated — which rolls up into a data-gap finding,
because a firm that cannot produce a field has told you something.

## `Assessment` — an agent's meaning attached to facts

```python
class Assessment(BaseModel):
    assessment_id: str
    case_id: str
    scope: Literal["case", "portfolio"]
    agent: str
    fact_ids: list[str]                       # what this rests on — the critic checks these
    rule_id: str | None

    verdict: Literal["breach", "concern", "explained", "inconclusive"]
    severity_floor: float                     # from the ruleset — deterministic
    severity_assessed: float                  # the agent's view, >= floor, never below
    severity_rationale: str | None            # required whenever assessed > floor
    confidence: Literal["certain", "probable", "possible"]

    subject: str | None
    narrative: str                            # what this means, for a human
    evidence_refs: list[EvidenceRef]
```

**`explained` is worth its own verdict.** A rule tripped and the agent, given context, judges it
benign — an unapproved counterparty that is the approved one's disclosed subsidiary. The fact stands
on the record; the assessment says why it isn't a concern. **A supervisor needs to record "we looked
and it's fine" as distinct from "we didn't look."**

## Severity: floor plus agent escalation

The propose-enforce pattern, applied to severity:

- **The floor is deterministic** — the ruleset's weight for that rule. Same facts, same floor, always.
- **An agent may raise it, never lower it**, and must give a rationale that gets recorded.
- **The score is computed twice**: `score_floor` from floors alone, `score_assessed` including
  escalations. Both are shown.

This keeps the concept note's *"explainable, factor-level scoring"* literally true — the floor is a
printable derivation from rules and weights — while letting an agent say *"three separate detectors
converged on one injected line item; individually 0.85, 0.6 and 0.85, but as a coordinated
manipulation this is materially worse."* That is a supervisory judgment, it is recorded with its
reasoning, and it cannot be used to make a case look better than the rules say.

`Observation`, `ControlAssessment`, `Correlation` and `InvestigationAnswer` are unchanged from the
previous draft.

---

# Part IV — Tools

## Not MCP inside the product — and the reason is our own catalogue

**F33** is *"the agent called a tool nobody authorised"*; **F32 channel 2** is *tool-description
poisoning*. Building this on unpinned MCP servers whose descriptions reach a model would reproduce
inside our product the exact failures it exists to detect.

So: in-process typed Python tools, permissioned by the `AGENT_TOOLS` map and re-checked at execution —
which is what makes *"dispatcher-permissioned, not prompt-instructed"* literally true.

**MCP earns its place outward** — exposing the registries and the ledger's verify endpoint to other
supervisory systems. If we do that we pin the server and hash the tool schemas, exactly as
`KYA-TEC-06` requires of supervised firms. **Eating our own dog food is a demo beat.**

## The surface

| Tool | Returns | Available to |
|---|---|---|
| `get_rule(rule_id)` | what a rule checks, params, status, severity | all |
| `get_facts(filter)` | facts from this case, filtered | specialists, subagents, hunter |
| `recompute_stats(kind, params)` | statistics at different parameters | log, drift, subagents |
| `get_credential_history(agent_id)` | issuance series across the ledger | kya, subagents |
| `get_registry_record(kind, id)` | issuer / firm / agent / merchant / tool | kya, provenance, counterparty |
| `get_counterparty_profile(id)` | aggregates, this case and across the ledger | counterparty, drift, investigator |
| `get_transactions(filter)` | filtered rows | log, investigator, subagents |
| `search_prior_cases(query)` | similar cases from the ledger | hunter, investigator |
| `get_case_record(id)` · `compare_runs(a,b)` | projections | investigator |

Budgets: specialist **3**, subagent **3**, hunter **6**, investigator **8** — enforced in the node, not
requested in the prompt. Every call recorded as a `ToolCallRecord`. **No tool returns
`line_items[].description`**; the injection surface stays closed.

---

# Part V — The runs

| Run | Trigger | Model calls | Ends with |
|---|---|---|---|
| **Intake** | submission | **0** | facts, pack, data gaps, case `received` |
| **Review** | officer or auto | ~12–20 | assessments, correlations, score, case `assessed` |
| **Investigate** | officer message | 2–10 | answer, or new assessments |
| **Report** | explicit request | 1–3 | held at the human gate |
| **Portfolio** | scheduled | 1–3 | portfolio-scope assessments |
| **Probe** | officer request | 2–5 | control-probe report |

**Review call budget, honestly:** 1 orchestrator + 8 specialists + 0–6 subagents + hunter + synthesizer
+ control-assurance ≈ **12–20 calls**. Specialists run concurrently and subagents fan out in parallel,
so wall-clock is roughly *depth* not *count* — about 4 sequential hops. v2's 3-call triage took ~60s
live; expect **90–150s**, which is fine for supervision and worth saying out loud rather than
discovering on stage.

**Intake staying model-free is what makes that affordable.** A clean case with no dispatched judgment
costs nothing and can be closed without a single API call.

---

# Part VI — What carries over

Untouched from v2: the ledger · the projection · the human gate · prompts as per-run arguments ·
rules as data · deterministic ingestion · grounding · the v2 §5 guarantees table.

**Extended:** the guarantees table gains four rows —

| Guarantee | Enforced by |
|---|---|
| An agent cannot lower a severity below the ruleset floor | `Assessment` validator: `severity_assessed >= severity_floor` |
| An agent cannot assert without a fact | the critic resolves every `fact_id` and `evidence_ref` |
| A subagent cannot write to the record | it has no ledger handle; the parent owns the assessment |
| Subagent recursion is bounded | depth 1, enforced in the node |

New ledger events: `facts_recorded` · `evidence_assembled` · `plan_recorded` · `subagent_dispatched` ·
`assessment_recorded` · `control_assessed` · `probe_completed`.

---

# Part VII — The plan

## Stage 0 · Fix-first — *0.5d*
Synthesizer list guard · correlation dedup · `run_failed` + AG-UI `RUN_ERROR` · delete dead
`data/uploads.py` · investigator missing from the UI roster · pin LangGraph.

## Stage 1 · Facts and assessments — *1.5d*
`Fact`, `Assessment` with the floor/assessed severity split, `EvidenceRef`. Tier 0 emits facts instead
of findings. Scoring computes both scores. `Finding` becomes a compatibility view so nothing breaks.
**Acceptance:** existing tests pass; an agent that lowers severity fails validation.

## Stage 2 · Evidence pack + model-free intake — *1.5d*
Deterministic assembly, digest recorded, agent briefs as views, data-gap findings.
**Acceptance:** a case intakes and gap-checks with `ANTHROPIC_API_KEY` unset.

## Stage 3 · Eval harness — *1d*
Per-agent precision/recall, **a real false-positive rate** now that satisfied facts are recorded,
calibration report, confidence calibration, and orchestrator-hypothesis scoring. Baseline committed.

## Stage 4 · The rulebook — *1.5d*
57 rules as registry JSON with checkers; the eleven dials; `firms.json`, `agents.json`,
`merchants.json`, `tools.json`.

## Stage 5 · The tiers — *2d*
Orchestrator planning over facts · specialists as assessors · **subagents via `Send()`** with depth and
budget caps · sequential synthesis stage.
**Acceptance:** a case that spawns subagents shows the full tree in the ledger and the case room.

## Stage 6 · The Hunter — *1d*
Full-pack access, observation-only output, and the discovery loop: recurring observations surface as
candidate rules in the registry UI.

## Stage 7 · New specialists — *2d*
Provenance · Injection · Counterparty · Consent.

> **Cut line.** 0–6 deliver the architecture: facts distinct from meaning, a real orchestrator, genuine
> subagent delegation, and an agent whose whole job is finding what the rules missed.

## Stage 8 · `monitor` + Systemic · agentic Red Team · supervisory query — *2.5d*

## Sequencing note

**Stages 1–3 before any new agent.** Adding specialists to an unmeasured pipeline multiplies output
without improving supervision — the mistake v2 made. But the tiers (Stage 5) come *before* the new
specialists, because the tier structure is what makes eight of them tractable.
