# Architecture v3 — an orchestrator, twelve specialists, and a review that iterates

Branch `feat/supervision-architecture-v3`. Supersedes `architecture-v2.md` §14–18; v2 §5 (where
guarantees live) survives, extended.

Companions: `coverage-model.md` (73 failures) · `kya-ruleset.md` (57 rules) ·
`kya-and-the-sandbox.md` (positioning).

---

# Part I — The governing principle

> **Determinism establishes facts. Agents establish meaning.**

A deterministic check does not produce a verdict. It produces a **fact**: *"Cart total ₾1,289. Intent
cap ₾350. Excess ₾939."* True, reproducible, cheap, injection-proof — and **not supervision**. Nothing
there says whether it was deliberate, what it connects to, how serious it is for this firm, or what
else deserves a look.

**Checks belong to the agents that own their domain.** Each specialist has two phases:

```python
class Specialist:
    def check(self, evidence) -> list[Fact]:      # deterministic · no model · always runs
    async def assess(self, facts, brief) -> Report: # judged · dispatched by the orchestrator
```

This is the shape v2 already had — `run()` and `review()` — and it was right. **The mistake in the
previous draft of this document was hoisting the checks out of the agents into a separate "Tier 0"
layer.** That took ownership away from the specialists for no gain. `check()` stays inside the
specialist; it simply doesn't need a model, so it runs unconditionally and in parallel before anything
is dispatched.

**Why checks run before the orchestrator plans:** so the plan is worth making. In v2 the orchestrator
saw `{firm, purpose_category, transaction_count}` and re-derived from one integer what a deterministic
floor already knew — dispatch was theatre. With facts in hand it makes a real decision:

> *"Cap breached by ₾939 and the injection heuristic fired on line item 0 — brief Injection deep with
> the attestation attached; tell Mandate to focus on line-item provenance, the cap is already
> established. Statistics unremarkable, Log standard. Drift has 7 transactions, skip it."*

Running `check()` costs microseconds. Deciding whether to run it would cost more than running it.

## What a check actually is — and no, not every rule is code

**Every rule in the registry declares its own evaluation mode.** This is a property of the rule, stored
in the ruleset JSON, not a property of the agent:

```jsonc
{ "rule_id": "MND-CAP-01", "evaluation": "computable", ... }   // arithmetic — check() evaluates it
{ "rule_id": "MND-SEM-01", "evaluation": "judged",     ... }   // semantic — assess() evaluates it
```

`check()` runs the **computable** rules. The **judged** rules cannot run there — they need a model, so
they are evaluated in the dispatched `assess()` pass. Roughly one rule in seven is judged.

### So what does `check()` produce for an agent whose rules are all judged?

This is the hole the previous draft left. Log's three v2 rules are *all* model-judged, so a naive
`check()` would emit nothing, and the orchestrator would plan blind about transaction patterns —
straight back to v2's problem.

**`check()` emits two kinds of fact, and this is what closes it:**

| Fact kind | From | Example |
|---|---|---|
| **rule outcome** — `breach` · `satisfied` · `absent` | a computable rule | *"Cart total 1289.0 exceeds cap 350.0 by 939.0"* `MND-CAP-01` |
| **measurement** | deterministic computation feeding a *judged* rule | *"Cluster: 3 payments to MER-X within 6h, ₾2,900 + ₾2,850 + ₾2,950 = ₾8,700, threshold ₾3,000"* |

So Log's `check()` computes every cluster, velocity and concentration number as **measurements**, even
though the verdict on whether they constitute structuring is judged. The orchestrator plans on the
measurement — *"there's a cluster summing to 8,700 against a 3,000 threshold, brief Log deep"* — and
`assess()` turns the measurement into a verdict on `LOG-STR-01`.

**Every judged rule has measurements behind it.** That is the contract: a rule may be judged, but the
evidence it is judged on is always computed deterministically first. It is also what the critic checks
— an agent's assessment must cite the measurements it was given.

### Which rulebook does a check use?

**One ruleset per domain, one owner each.** `kya-ruleset.md` fully specifies two of them; the rest
exist in v2 at various maturity and expand per `coverage-model.md`.

| Ruleset | Owner | Rules | Judged | Status |
|---|---|---|---|---|
| `KYA-*` | KYA | 42 | 2 | **fully specified** in `kya-ruleset.md` |
| `CTL-*` | Control Assurance | 15 | 0 | **fully specified** in `kya-ruleset.md` |
| `MND-*` | Mandate | 12 | 1 | exists in v2; needs `MND-SEM-03`, geographic scope |
| `LOG-*` | Log | 3 → ~7 | most | exists; add round amounts, off-hours, limit probing, alert flooding |
| `DRIFT-*` | Drift | 1 → 3 | 3 | exists; split into amount / frequency / mix |
| `PRV-*` | Provenance | — | ~1 | **to write** — F33, F34, F36, F37 |
| `INJ-*` | Injection | — | ~1 | **to write** — F32, F35, per channel |
| `CPY-*` | Counterparty | — | 0 | **to write** — F51–F58, all mechanical |
| `CNS-*` | Consent & Harm | — | ~1 | **to write** — F24–F31, F38 |

The Hunter has **no ruleset by design** — its whole job is what no rule covers.

## What stays absolutely deterministic

The trust anchors: cryptographic verification · the hash-chained ledger · **computable** rule
evaluation · the score floor · grounding validation · the critic · tool permissioning · the human
gate · ingestion.

**Everything a firm could challenge in a hearing is deterministic. Everything requiring supervisory
judgment is an agent.**

---

# Part II — The twelve specialists

The eleven from `coverage-model.md`, plus the Hunter. Grouped by **when they run**, not by importance —
all twelve are first-class.

## Case-scoped peers — dispatched in parallel, every round

| # | Specialist | Skill | Owns | Judged pass |
|---|---|---|---|---|
| 1 | **Mandate** | `mandate.review` | F39–F50 · 12 `MND-*` | per-line-item intent fidelity |
| 2 | **KYA** | `kya.review` | F1–F23 · 39 `KYA-*` | declaration-vs-reality, least privilege |
| 3 | **Provenance** | `provenance.verify` | F33, F34, F36, F37 · `TEC-02/05/06` | did the tool trace show action on untrusted content |
| 4 | **Injection** | `injection.trace` | F32, F35 | which channel plausibly caused the deviation |
| 5 | **Counterparty** | `counterparty.profile` | F51–F58 | *(mechanical — narration only)* |
| 6 | **Consent & Harm** | `consent.review` | F24–F31, F38 | value-for-money against real alternatives |
| 7 | **Log** | `log.analyze` | F59–F64, F66 | pattern detections, one per instance |
| 8 | **Drift** | `drift.analyze` | F65 | per-dimension drift + onset attribution |
| 9 | **Hunter** | `hunt.open` | *(nothing — no rules by design)* | **what is happening that no rule covers** |

## Sequential — consume what precedes them

| # | Specialist | Skill | Why it can't be a peer |
|---|---|---|---|
| 10 | **Control Assurance** | `controls.assess` | `CTL-EFF-01` asks whether a control that *should* have triggered did — it needs to know what tripped |

## Off-cycle — different cadence entirely

| # | Specialist | Skill | Cadence |
|---|---|---|---|
| 11 | **Systemic** | `portfolio.sweep` | scheduled, across the whole ledger |
| 12 | **Red Team** | `probe.generate` | on-demand; LLM-generated attacks against the firm's *declared* controls |

**Support agents:** Orchestrator · Investigator · Critic *(deterministic)* · Synthesizer · Drafting ·
Grounding *(deterministic)*.

## The Hunter, specifically

The failure catalogue has 73 entries. A real attacker invents #74, and no rule will catch it, because
rules only catch what someone already wrote down. The Hunter gets the **whole** evidence set and **all**
facts with no domain boundary, and is asked one question: *what is happening here that no rule covers?*

Observations only — never scored, never citable. **And its output feeds the registry:** an observation
recurring across cases becomes a candidate rule. That is the loop from discovery to policy, and it is
what gives the policy sandbox real inputs rather than guesses.

---

# Part III — The orchestrator dispatches skills, and agents never talk to each other

## Skills, not agents

The orchestrator selects from the **skill registry** — `agents/skills.py`, already in v2. It names a
skill and composes a brief; code resolves the skill to an agent. Adding a thirteenth specialist is a
registry entry, not an edit to a routing function.

```python
class Brief(BaseModel):
    skill_id: str                      # "counterparty.profile" — must exist in the registry
    depth: Literal["standard", "deep"] # deep = larger tool budget, subagents permitted
    focus: str                         # what this dispatch is specifically about
    facts_attached: list[str]          # fact ids — the orchestrator NAMES, never authors
    extra_blocks: list[str]            # record items to attach verbatim
```

## No lateral communication — the invariant, stated precisely

**No specialist may see, message, or be influenced by another specialist's reasoning.** All
information flows through the orchestrator and the ledger. This is a commitment from the submitted
concept note and it holds.

Two things it deliberately permits, and the distinction matters:

- **The orchestrator may attach one specialist's *recorded assessment* to another's brief.** That is
  not lateral communication — it is the orchestrator briefing, from the record, in the open, and
  recorded as part of the dispatch.
- **A specialist may delegate downward to subagents it owns.** Downward only, one level, and a
  subagent answers *only its parent*. Subagents cannot see each other and cannot reach another
  specialist.

What remains forbidden: peer-to-peer messaging, shared scratch state, and any path by which Log's
reasoning reaches Drift without passing through the orchestrator or the ledger.

## Subagents — one question each

When a specialist cannot settle something in one pass, it names sub-questions and the graph fans out
via LangGraph's `Send()`.

> `architecture-v2.md` §9 noted honestly that v2 used conditional edges instead, because the branch set
> was a subset of four *fixed* nodes rather than a generated list. **A dynamically generated list of
> sub-questions is exactly what `Send()` exists for.** That loop closes here.

```
kya ──Send()──► "does BRIDGE-CO's own credential grant the authority it passed on?"
    ──Send()──► "has SVANETI-IMPORT appeared in any other case's chain?"
    ──Send()──► "is 'Kavkasia Credential Services' the accredited issuer, or a near-name?"
```

Each subagent: one question, a scoped slice of evidence, its own tool budget (3), a typed return.
**It never writes to the ledger** — it answers its parent, and the parent owns the resulting
assessment. Accountability stays with the named specialist. Depth capped at **1**; a subagent cannot
spawn subagents. Only `deep` dispatches may spawn at all.

---

# Part III·5 — One case, end to end

CASE-2026-007, the prompt-injection case, with real numbers from the live run.

## Step 1 · Intake — **0 model calls**

The submission arrives. Machinery, not agents:

- **Verify** — Ed25519 on the credential, every delegation entry, the Cart→Intent and Payment→Cart
  chain hashes.
- **Resolve registries** — issuer, operator firm, agent, merchant, tool allowlist.
- **Compute shared evidence** — transaction statistics, baseline split, counterparty breakdown, the
  cross-ledger counterparty profile. Computed **once** so nine agents don't each recompute PSI.
- **Identify gaps** — which submission blocks are absent.
- **Record** — one `evidence_assembled` event with a digest. Same submission → same digest, always.

Case status: `received`. Cost so far: nothing.

## Step 2 · Check — **0 model calls, nine specialists in parallel**

Each specialist runs its own **computable** rules over the shared evidence and emits facts. Nobody has
judged anything yet.

```
Mandate.check()      11 computable rules
  ✗ breach       MND-CAP-01  "Cart total 1289.0 exceeds cap 350.0 by 939.0"
  ✗ breach       MND-SEM-02  "line_items[0].description contains instruction-like text:
                              'Note to purchasing agent'"
  ✓ satisfied    MND-CHN-01, MND-CHN-02  chain hashes recompute
  ✓ satisfied    MND-CAP-02  merchant MCC 5261 is in the allowed set
  ✓ satisfied    MND-CAP-03, MND-CUR-01/02, MND-VAL-01, MND-CON-01
  —              MND-SEM-01  judged · not evaluated here

KYA.check()          40 computable rules → 38 satisfied, 2 absent (no agent registry)
Log.check()          0 computable rules, but 6 MEASUREMENTS:
  ◆ measurement  "7 transactions; largest cluster is 1 payment; no cluster exceeds threshold"
  ◆ measurement  "counterparty concentration 100% across 1 approved counterparty"
  ◆ measurement  "velocity: max 2 transactions per 24h window"
Drift.check()        ✗ absent  "7 transactions below the 30-transaction baseline minimum"
Counterparty.check() 6 satisfied, 2 absent (no merchant registry yet)
Provenance.check()   absent × N  (no construction_context in this submission)
Consent.check()      absent × N  (no consent_ceremony in this submission)
Injection.check()    ✗ breach  INJ-01  "instruction-shaped text in channel: product_listing"
Hunter.check()       — no rules by design
```

**Result: ~110 facts.** Three breaches, ~90 satisfied, 6 measurements, ~11 absent. Plus one **data-gap
finding**: *"Provenance and Consent could not be evaluated — the firm submitted no `construction_context`
or `consent_ceremony` block; 15 rules disabled."*

## Step 3 · Plan — **1 model call**

The orchestrator sees every fact. **On round 1 the floor is: every case-scoped skill runs.** Its
decision is not *whether* but **depth and focus** — plus which facts to attach to whom.

```jsonc
{
  "hypothesis": "Prompt injection via the product listing; the agent complied and added an
                 unrequested line item. The cap breach is the arithmetic side effect, not the
                 primary failure.",
  "dispatches": [
    { "skill": "injection.trace",  "depth": "deep",
      "focus": "Instruction-shaped text found in line_items[0]. Establish the channel and whether
                the agent's own attestation cites it as authority.",
      "facts_attached": ["F-007-MND-SEM-02", "F-007-INJ-01"] },
    { "skill": "mandate.review",   "depth": "deep",
      "focus": "The cap breach is already established — do not re-derive it. Assess per-line-item
                intent fidelity: which items are within what the human asked for.",
      "facts_attached": ["F-007-MND-CAP-01"] },
    { "skill": "log.analyze",      "depth": "standard",
      "focus": "7 transactions, no cluster near threshold. Confirm or refute.",
      "facts_attached": ["F-007-LOG-M1", "F-007-LOG-M2", "F-007-LOG-M3"] },
    { "skill": "kya.review",       "depth": "standard" },
    { "skill": "counterparty.profile", "depth": "standard" },
    { "skill": "hunt.open",        "depth": "standard" }
  ],
  "declined": [
    { "skill": "drift.analyze", "reason": "insufficient history — 7 transactions vs 30 minimum" },
    { "skill": "provenance.verify", "reason": "no construction_context submitted" },
    { "skill": "consent.review",    "reason": "no consent_ceremony submitted" }
  ]
}
```

Note what it did: told Mandate **not to re-derive** the cap breach, attached the injection facts to
Injection, and declined three skills for *stated, factual* reasons rather than guesses. It could not
have done any of that in v2, where it saw three fields.

`plan_recorded` goes on the ledger, hypothesis included — the eval harness scores it later.

## Step 4 · Assess — **6 parallel model calls, plus subagents**

Each dispatched specialist reasons over its facts and its brief.

```
Injection.assess()   → Assessment(breach, INJ-01)
                       channel = product_listing
                       narrative: "The agent's attestation cites the listing text as authority:
                       'described as pre-authorized by the operator'. It acted on merchant-authored
                       content as though it were an operator instruction."
                       severity_floor 0.60 → severity_assessed 0.90
                       rationale: "The attestation shows compliance, not mere presence of the text."

Mandate.assess()     → Assessment(satisfied, per line item KGS-FERT-20KG)
                     → Assessment(breach, MND-SEM-01, subject=GHG-GIFTCARD-TOPUP)
                       "A gift-card top-up is not garden or landscaping supplies, whoever sells it."

Log.assess()         → Assessment(explained, LOG-STR-01)
                       "No cluster approaches the threshold. 7 transactions is too thin for a
                       structuring judgment either way." confidence: possible

KYA.assess()         → REG-03, CAP-04 → satisfied
                       ──Send()──► subagent: "is 'Guria Home & Garden' the registered operator
                                              name, or a near-match to another firm?"
                                   → answer: exact match, no concern

Hunter.assess()      → Observation: "The gift-card SKU has no prior history with this supplier
                       across the ledger. Every other SKU from MER-KGS-001 appears at least twice."
```

## Step 5 · Synthesis — **sequential**

```
Critic (deterministic, 0 calls)
  resolves every fact_id and evidence_ref against the brief each agent was given
  → all quoted values present · passed

Synthesizer (1 call)
  → Correlation(same_event, [MND-CAP-01, MND-SEM-02, MND-SEM-01, INJ-01])
    "Four detectors, one injected line item."

Control Assurance (1 call)
  → no `controls` block submitted
  → ControlAssessment(posture="absent") for every breach
  → plus CTL-REP-02: "The firm declared no control set. Coverage cannot be assessed."

Score (deterministic, 0 calls)
  score_floor    2.30   ESCALATE
  score_assessed 2.75   ESCALATE   (Injection escalated 0.60 → 0.90, recorded with rationale)
```

Case status: `assessed`. **Total: ~10 model calls, ~4 sequential hops.**

## Step 6 · The officer, and round 2

She opens the case room and reads the transcript. Then:

> *"Was a human actually in the loop for this one?"*

- `check()` **does not re-run** — it is deterministic over an unchanged submission.
- The orchestrator re-plans with round 1 in context: the question is about consent, and Consent was
  declined in round 1 for a factual reason. It replies rather than dispatching:
  *"The firm submitted no consent ceremony record, so I can't establish that. `human_presence_required`
  on this mandate is false, so no human was required. Do you want me to raise the missing record as a
  finding in its own right?"*
- She says yes. Round 2 dispatches `consent.review` scoped to the data gap, which emits
  `Assessment(breach, CNS-31)` — *no record that a human was ever involved.*
- Score recomputes. Round 3 is available if she wants it.

## Step 7 · Report

She asks for the report. Drafting sees **only** the structured record — assessments, correlations,
control postures, the score — never raw firm text. Grounding validates deterministically. The gate
holds until she types her name.

---

# Part IV — The review iterates

**A review is a conversation, not a pipeline run.** The officer reads what came back, asks for more,
and the orchestrator re-briefs. That loop is the product.

```
   submission
       │
       ▼
   ROUND 1  ─ every specialist runs check()  → facts
            ─ orchestrator plans on facts     → briefs
            ─ dispatched skills assess        → assessments (+ subagents)
            ─ critic → synthesizer → control-assurance → score
       │
       ▼
   ┌── OFFICER reads the case room ──┐
   │                                  │
   │  "go deeper on the counterparty" │
   │  "was the human actually there?" │
   │  "re-check Log at a 12h window"  │
   │                                  │
   ▼                                  │
   ROUND 2  ─ orchestrator re-plans, carrying rounds 1..n-1 and the officer's instruction
            ─ dispatches only what the question needs (often 1–2 skills, sometimes subagents)
            ─ new assessments may SUPERSEDE earlier ones
            ─ score recomputes
       │                              │
       └──────────────────────────────┘
                    │
              satisfied
                    ▼
            REPORT ⇄ GROUNDING ──► HUMAN GATE
```

## What changes between rounds

**`check()` does not re-run.** It is deterministic over an unchanged submission, so it would produce
identical facts. Round 2+ dispatches judgment only. If the officer's question needs different
parameters — *"re-check that cluster at 12 hours"* — that is a **tool call** inside the round, not a
re-run of the checks.

**The orchestrator carries state.** Every round sees prior rounds' assessments, the officer's full
message history, and the standing plan. *"And the other one?"* resolves — the absence of which was the
single biggest behavioural gap in v2.

**The officer's instruction is trusted input.** Regulator-authored, so it may reach a specialist's
prompt as free text — delimited, appended to a registry prompt, never replacing it. Nothing
firm-submitted ever gets that treatment.

## Supersession — how a later round overrules an earlier one

Round 1: Counterparty finds `counterparty_not_approved`, verdict `breach`.
Round 3: given the officer's context, it establishes the payee is the approved supplier's disclosed
subsidiary. Verdict `explained`.

```python
class Assessment(BaseModel):
    ...
    supersedes: str | None      # the assessment_id this replaces
    superseded_by: str | None   # set on the earlier record by the projection, never in place
```

**Both stay on the ledger.** The projection marks the earlier one superseded and scoring uses only
current assessments. The audit trail shows the case changing its mind and why — which is exactly what
a supervisory file should show. Nothing is ever edited or deleted; the ledger's append-only guarantee
is untouched.

## Round budget

Machine-initiated escalation is capped at **1** extra round, as in v2 — an agent cannot spin.
**Officer-initiated rounds are capped at 10**, and that cap is belt-and-braces: every round costs an
explicit human decision, so the human is the real bound.

---

# Part V — Facts, assessments, severity

## `Fact` — from a specialist's `check()`

```python
class Fact(BaseModel):
    fact_id: str; case_id: str
    agent: str                                # the specialist that established it
    rule_id: str | None
    kind: Literal["breach", "satisfied", "measurement", "absent"]
    statement: str                            # "Cart total 1289.0 exceeds cap 350.0 by 939.0"
    values: dict[str, Any]
    refs: list[EvidenceRef]
```

`satisfied` facts are how a clean case becomes *provably* clean rather than merely silent, and they
give the eval harness true negatives — which is what makes a real false-positive rate computable.
`absent` means a rule could not be evaluated, which rolls up into a **data-gap finding**: a firm that
cannot produce a field has told you something.

## `Assessment` — an agent's meaning attached to facts

```python
class Assessment(BaseModel):
    assessment_id: str; case_id: str; round: int
    scope: Literal["case", "portfolio"]
    agent: str; skill_id: str
    fact_ids: list[str]                       # what this rests on — the critic resolves these
    rule_id: str | None

    verdict: Literal["breach", "concern", "explained", "inconclusive"]
    severity_floor: float                     # from the ruleset — deterministic
    severity_assessed: float                  # agent's view — >= floor, never below
    severity_rationale: str | None            # required whenever assessed > floor
    confidence: Literal["certain", "probable", "possible"]
    narrative: str
    supersedes: str | None
```

**`explained` earns its own verdict.** A rule tripped and the agent, in context, judges it benign. The
fact stands on the record; the assessment says why it isn't a concern. **"We looked and it's fine"
must be distinguishable from "we didn't look."**

**`inconclusive`** is what replaces v2's "unresolved observation" as the escalation trigger — a rule
applies, the agent evaluated it, and cannot decide. Scores nothing, routes to a human.

## Severity: floor plus escalation

Propose-enforce, applied to severity. **The floor is deterministic**; **an agent may raise it, never
lower it**, with a recorded rationale; **both scores are shown** (`score_floor`, `score_assessed`).

This keeps *"explainable, factor-level scoring"* literally true — the floor is a printable derivation
from rules and weights — while letting an agent say *"three detectors converged on one injected line
item; as coordinated manipulation this is materially worse than the sum."* Recorded with its reasoning,
and structurally unable to make a case look better than the rules say.

---

# Part VI — Tools

**Not MCP inside the product**, and the reason is our own catalogue: **F33** is *"the agent called a
tool nobody authorised"* and **F32 channel 2** is *tool-description poisoning*. Building on unpinned
MCP servers whose descriptions reach a model would reproduce inside our product the exact failures it
exists to detect. In-process typed Python tools, permissioned by `AGENT_TOOLS`, re-checked at
execution.

**MCP earns its place outward** — exposing the registries and the ledger's verify endpoint to other
supervisory systems, with the server pinned and tool schemas hashed, exactly as `KYA-TEC-06` requires
of supervised firms. Eating our own dog food is a demo beat.

| Tool | Available to |
|---|---|
| `get_rule(rule_id)` | all |
| `get_facts(filter)` | specialists, subagents, hunter |
| `recompute_stats(kind, params)` | log, drift, subagents |
| `get_credential_history(agent_id)` | kya, subagents |
| `get_registry_record(kind, id)` | kya, provenance, counterparty |
| `get_counterparty_profile(id)` | counterparty, drift, investigator |
| `get_transactions(filter)` | log, investigator, subagents |
| `search_prior_cases(query)` | hunter, investigator |
| `get_case_record(id)` · `compare_runs(a,b)` | investigator |

Budgets — specialist **3**, subagent **3**, hunter **6**, investigator **8** — enforced in the node,
not requested in the prompt. Every call recorded. **No tool returns `line_items[].description`.**

---

# Part VII — The runs

| Run | Trigger | Model calls | Ends with |
|---|---|---|---|
| **Intake** | submission | **0** | facts, evidence, data gaps, case `received` |
| **Review round** | officer, or auto on intake | round 1 ≈ 12–20 · later rounds 2–6 | assessments, score, case `assessed` |
| **Report** | explicit request | 1–3 | held at the human gate |
| **Portfolio** | scheduled | 1–3 | portfolio-scope assessments |
| **Probe** | officer request | 2–5 | control-probe report |

**Honest timing.** Round 1 is ~12–20 calls: orchestrator + 9 peers + 0–6 subagents + synthesizer +
control-assurance. They fan out, so wall-clock is *depth* not *count* — about four sequential hops.
v2's 3-call triage ran ~60s live; expect **90–150s** for round 1 and **20–40s** for a follow-up round.
Worth knowing now rather than discovering on stage.

**Intake staying model-free is what makes it affordable** — a clean case costs zero API calls and can
be closed without one.

---

# Part VIII — Guarantees

Untouched from v2 §5: the ledger · the projection · the human gate · prompts as per-run arguments ·
rules as data · deterministic ingestion · grounding · the mandatory skill floor.

**Five new rows** covering the agent surface:

| Guarantee | Enforced by |
|---|---|
| An agent cannot lower severity below the ruleset floor | `Assessment` validator: `severity_assessed >= severity_floor` |
| An agent cannot assert without a fact | the critic resolves every `fact_id` and `evidence_ref` against the brief |
| **Specialists never communicate laterally** | no shared state; briefs come only from the orchestrator; subagent returns go only to the parent |
| A subagent cannot write to the record | it holds no ledger handle; the parent owns the assessment |
| Subagent recursion is bounded | depth 1, `deep` dispatches only, enforced in the node |

New events: `facts_recorded` · `plan_recorded` · `subagent_dispatched` · `assessment_recorded` ·
`assessment_superseded` · `control_assessed` · `probe_completed` · `round_started`.

---

# Part IX — The plan

**0 · Fix-first** *(0.5d)* — synthesizer list guard · correlation dedup · `run_failed` + AG-UI
`RUN_ERROR` · delete dead `data/uploads.py` · investigator missing from the UI · pin LangGraph.

**1 · Facts and assessments** *(1.5d)* — `Fact`, `Assessment` with the floor/assessed split,
`EvidenceRef`, supersession. Specialists' `run()` renamed `check()` and emitting facts. Scoring
computes both scores. *Acceptance: existing tests pass; an agent lowering severity fails validation.*

**2 · Shared evidence + model-free intake** *(1.5d)* — statistics and registry resolution assembled
once and shared; specialists draw from it rather than recomputing; data-gap findings. *Acceptance: a
case intakes, checks and gap-checks with `ANTHROPIC_API_KEY` unset.*

**3 · Eval harness** *(1d)* — per-agent precision/recall, **a real false-positive rate** now that
satisfied facts exist, calibration, and orchestrator-hypothesis scoring. Baseline committed.

**4 · The rulebook** *(1.5d)* — 57 rules as registry JSON with checkers; the eleven dials;
`firms.json`, `agents.json`, `merchants.json`, `tools.json`.

**5 · Orchestrator, skills, subagents** *(2d)* — planning over facts · skill-based dispatch with
briefs · **`Send()` subagent fan-out** with depth and budget caps · sequential synthesis stage.
*Acceptance: a case that spawns subagents shows the whole tree in the ledger and the case room.*

**6 · The iterative review** *(1.5d)* — rounds, conversation state across rounds, supersession, the
case room driving it. *Acceptance: three rounds where round 3 supersedes a round-1 breach with
`explained`, and both are on the record.*

**7 · The Hunter** *(1d)* — full-evidence access, observations only, recurring observations surfacing
as candidate rules in the registry UI.

> **Cut line.** 0–7 deliver the architecture: facts distinct from meaning, a real orchestrator, genuine
> delegation, an iterative review, and an agent whose job is finding what the rules missed.

**8 · New specialists** *(2d)* — Provenance · Injection · Counterparty · Consent.
**9 · `monitor` + Systemic · agentic Red Team · supervisory query** *(2.5d)*

**Sequencing:** stages 1–3 before any new agent — adding specialists to an unmeasured pipeline
multiplies output without improving supervision. But 5–6 come before 8, because the orchestration and
the round loop are what make twelve specialists tractable at all.
