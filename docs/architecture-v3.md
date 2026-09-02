# Architecture v3 — one orchestrator, twelve specialists, an iterative review

Branch `feat/supervision-architecture-v3`. Supersedes `architecture-v2.md` §14–18; v2 §5 (where
guarantees live) survives, extended.

Companions: `coverage-model.md` (73 failures) · `kya-ruleset.md` (57 rules) ·
`kya-and-the-sandbox.md` (positioning).

---

# Part I — The principle, and the three parts of a domain

> **Determinism establishes facts. Agents establish meaning.**

A deterministic check produces a **fact**, not a verdict: *"Cart total ₾1,289. Intent cap ₾350. Excess
₾939."* True, reproducible, cheap, injection-proof — and **not supervision**. Nothing there says
whether it was deliberate, what it connects to, how serious it is for this firm, or what else deserves
a look. That is the agents' job.

## A domain has three parts, and only one of them is an agent

This is the distinction the previous draft blurred. **No agent runs before the orchestrator.**

| Part | What it is | When it runs |
|---|---|---|
| **The ruleset** | `registry/rulesets/mandate.json` — versioned data | — |
| **The checker** | `checks/mandate.py` — plain functions, no model | **at intake**, before any agent exists |
| **The agent** | `MandateAgent` — an LLM reasoner with a prompt and tools | **only when the orchestrator dispatches it** |

The checker and the agent both belong to the Mandate domain — one is its mechanical half, the other
its judgment half. But the checker is *code the rule engine calls*, not an agent taking a turn. Saying
"nine specialists run their rules in parallel before dispatch" was wrong: what runs is the **rule
engine**, organised by domain.

## Not every rule is code

Each rule declares its own evaluation mode in the ruleset JSON:

```jsonc
{ "rule_id": "MND-CAP-01", "evaluation": "computable" }   // arithmetic → the rule engine
{ "rule_id": "MND-SEM-01", "evaluation": "judged"     }   // semantic   → the agent
```

Roughly **one rule in seven is judged**. The rule engine evaluates the computable ones at intake. The
judged ones can only be evaluated by the dispatched agent.

### What the rule engine produces for a domain whose rules are all judged

Log's rules are *all* model-judged. A naive rule engine would emit nothing for Log, and the
orchestrator would plan blind about transaction patterns — back to v2's problem.

**The rule engine emits two kinds of fact:**

| Kind | Source | Example |
|---|---|---|
| **rule outcome** — `breach` · `satisfied` · `absent` | a computable rule | *"Cart total 1289.0 exceeds cap 350.0 by 939.0"* `MND-CAP-01` |
| **measurement** | deterministic computation behind a *judged* rule | *"Cluster: 3 payments to MER-X within 6h, ₾2,900 + ₾2,850 + ₾2,950 = ₾8,700, threshold ₾3,000"* |

So Log's checker computes every cluster, velocity and concentration number as a **measurement**, even
though the verdict is judged. The orchestrator plans on the measurement; the Log agent turns it into a
verdict on `LOG-STR-01`.

**Every judged rule has deterministic measurements behind it.** That is the contract, and it is what
the critic later checks an assessment against.

## The nine rulesets

One per domain, one owner each.

| Ruleset | Domain | Rules | Judged | Status |
|---|---|---|---|---|
| `KYA-*` | KYA | 42 | 2 | **fully specified** in `kya-ruleset.md` |
| `CTL-*` | Control Assurance | 15 | 0 | **fully specified** in `kya-ruleset.md` |
| `MND-*` | Mandate | 12 | 1 | exists in v2; add `MND-SEM-03`, geographic scope |
| `LOG-*` | Log | 3 → ~7 | most | exists; add round amounts, off-hours, limit probing, alert flooding |
| `DRIFT-*` | Drift | 1 → 3 | 3 | exists; split into amount / frequency / mix |
| `PRV-*` | Provenance | — | ~1 | **to write** — F33, F34, F36, F37 |
| `INJ-*` | Injection | — | ~1 | **to write** — F32, F35, per channel |
| `CPY-*` | Counterparty | — | 0 | **to write** — F51–F58, all mechanical |
| `CNS-*` | Consent & Harm | — | ~1 | **to write** — F24–F31, F38 |

The **Hunter has no ruleset by design** — its whole job is what no rule covers.

## What stays absolutely deterministic

Cryptographic verification · the hash-chained ledger · **computable** rule evaluation · the score
floor · grounding validation · the critic · tool permissioning · the human gate · ingestion.

**Everything a firm could challenge in a hearing is deterministic. Everything requiring supervisory
judgment is an agent.**

---

# Part II — The shape

```
   submission
       │
       ▼
┌──────────────────────────────────────────────────────────────────────┐
│  INTAKE — code only, 0 model calls                                   │
│    verify signatures and chains · resolve registries                 │
│    compute shared evidence once (statistics, profiles, baselines)    │
│    RULE ENGINE evaluates every computable rule, by domain            │
│    ────────────────────────────► FACTS + MEASUREMENTS + data gaps    │
└──────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────────┐
│  ORCHESTRATOR — 1 call · the only agent that sees everything         │
│    reads all facts · plans the review · writes a brief per skill     │
│    round 1: its prompt says a first pass is comprehensive            │
│    round 2+: targeted at the officer's question                      │
└──────────────────────────────────────────────────────────────────────┘
       │  dispatches skills with briefs — agents never talk to each other
       ├──► mandate      ├──► counterparty   ├──► log
       ├──► kya          ├──► consent        ├──► drift
       ├──► provenance   ├──► injection      └──► hunter
       │                                          (9 in parallel, 1 call each)
       ▼
┌──────────────────────────────────────────────────────────────────────┐
│  SYNTHESIS — sequential, each consumes what precedes                 │
│    critic (deterministic) → synthesizer → control assurance → score  │
└──────────────────────────────────────────────────────────────────────┘
       │
       ▼
   OFFICER reads the case room ──► asks for more ──► ROUND 2 ──┐
       │                                                        │
       └────────────────► REPORT ⇄ GROUNDING ──► HUMAN GATE ◄──┘
```

**Two tiers of agent, not three.** The orchestrator dispatches specialists. **Specialists do not spawn
subagents** — a specialist that needs more evidence uses its tools, and a question that needs a
different specialist is the officer's next round. Iteration replaces recursion, which keeps
"agents never communicate" absolutely clean with no hierarchical exception to explain.

---

# Part III — The twelve specialists

The eleven from `coverage-model.md`, plus the Hunter. Grouped by **cadence**, not importance.

## Dispatched per round — nine, in parallel

| # | Specialist | Skill | Owns | Its judged rules |
|---|---|---|---|---|
| 1 | **Mandate** | `mandate.review` | F39–F50 | per-line-item intent fidelity |
| 2 | **KYA** | `kya.review` | F1–F23 | declaration-vs-reality, least privilege |
| 3 | **Provenance** | `provenance.verify` | F33, F34, F36, F37 | did the tool trace show action on untrusted content |
| 4 | **Injection** | `injection.trace` | F32, F35 | which channel plausibly caused the deviation |
| 5 | **Counterparty** | `counterparty.profile` | F51–F58 | *(none — mechanical; narration only)* |
| 6 | **Consent & Harm** | `consent.review` | F24–F31, F38 | value-for-money against real alternatives |
| 7 | **Log** | `log.analyze` | F59–F64, F66 | all three pattern verdicts |
| 8 | **Drift** | `drift.analyze` | F65 | per-dimension drift + onset attribution |
| 9 | **Hunter** | `hunt.open` | *(no rules by design)* | **what is happening that no rule covers** |

## Sequential — consumes the others

| # | Specialist | Skill | Why it can't be a peer |
|---|---|---|---|
| 10 | **Control Assurance** | `controls.assess` | `CTL-EFF-01` asks whether a control that *should* have triggered did — it needs to know what tripped |

## Off-cycle

| # | Specialist | Skill | Cadence |
|---|---|---|---|
| 11 | **Systemic** | `portfolio.sweep` | scheduled, across the ledger |
| 12 | **Red Team** | `probe.generate` | on-demand; LLM-generated attacks against the firm's *declared* controls |

**Support:** Orchestrator · Investigator · Critic *(deterministic)* · Synthesizer · Drafting ·
Grounding *(deterministic)*.

## The Hunter

The failure catalogue has 73 entries. A real attacker invents #74, and no rule will catch it, because
rules only catch what someone already wrote down. The Hunter gets the **whole** evidence set and **all**
facts with no domain boundary, and is asked one question: *what is happening here that no rule covers?*

Observations only — never scored, never citable. **Its output feeds the registry:** an observation
recurring across cases becomes a candidate rule. That is the loop from discovery to policy, and it is
what gives the policy sandbox real inputs rather than guesses.

---

# Part IV — The orchestrator

## It decides, including on round 1

**Round 1 is a full review because the orchestrator decides it should be**, not because a floor
bypasses it. Its default prompt says so:

> *"A first pass on a new case is comprehensive. Dispatch every skill whose data prerequisites are met.
> Your judgment on this pass is about **depth and focus** — which skills need deep attention and what
> each should concentrate on given what the rule engine already established — not about whether to
> look. Decline a skill only when a fact shows its prerequisites are unmet, and say which fact."*

The **deterministic floor remains as a backstop**, exactly as in v2: it can turn a proposed *no* into
a *yes*, never the reverse. So a hostile prompt override saying "skip KYA" changes nothing, and the
record shows both the instruction and the override. But on a normal case the orchestrator genuinely
made the call, and its reasoning is on the ledger.

## What it produces

```python
class ReviewPlan(BaseModel):
    round: int
    dispatches: list[Brief]
    declined: list[Declination]   # {skill_id, reason, fact_id} — must cite a fact
    hypothesis: str               # what it expects this case to be — the eval harness scores it
    rationale: str
    message_to_officer: str

class Brief(BaseModel):
    skill_id: str                      # from the skill registry — code resolves it to an agent
    depth: Literal["standard", "deep"] # deep = larger tool budget
    focus: str                         # what THIS dispatch is about
    facts_attached: list[str]          # fact ids — it NAMES facts, never authors them
    extra_blocks: list[str]            # record items attached verbatim
```

**Declining requires citing a fact.** *"Drift declined — fact F-007-DRIFT-ABSENT: 7 transactions
against a 30-transaction minimum."* Not a guess.

## What it may not do — all enforced in code

Judge the case (its schema has no verdict field) · author evidence (it names blocks and facts) ·
suppress a fact · skip a mandatory skill (the floor) · rewrite a prompt (it appends an instruction to a
registry prompt).

## Agents never communicate

**No specialist may see, message, or be influenced by another specialist's reasoning.** Everything
flows through the orchestrator and the ledger.

The one thing this permits: **the orchestrator may attach one specialist's recorded assessment to
another's brief.** That is briefing from the record, in the open, and recorded as part of the dispatch
— not agents talking. There is no shared scratch state, no peer channel, and **no subagents**, so
there is no other path by which Log's reasoning could reach Drift.

---

# Part V — One case, end to end

CASE-2026-007, the prompt-injection case, with real numbers from the live run.

## 1 · Intake — **0 model calls**

- **Verify** — Ed25519 on the credential and every delegation entry; Cart→Intent and Payment→Cart
  chain hashes.
- **Resolve registries** — issuer, firm, agent, merchant, tool allowlist.
- **Compute shared evidence once** — statistics, baseline split, counterparty profile. Nine agents
  will draw on this; none recomputes it.
- **Rule engine** — evaluates every computable rule across all nine rulesets.
- **Record** — one `evidence_assembled` event with a digest. Same submission → same digest, always.

```
Mandate rules (11 computable)
  ✗ breach       MND-CAP-01  "Cart total 1289.0 exceeds cap 350.0 by 939.0"
  ✗ breach       MND-SEM-02  "line_items[0].description contains instruction-like text:
                              'Note to purchasing agent'"
  ✓ satisfied    MND-CHN-01/02 · MND-CAP-02 (MCC 5261 allowed) · MND-CAP-03 · MND-CUR-01/02
                 MND-VAL-01 · MND-CON-01
  —              MND-SEM-01  judged · the agent will evaluate it

KYA rules (40 computable)      38 satisfied · 2 absent (no agent registry)
Injection rules                ✗ breach  INJ-01  "instruction-shaped text · channel: product_listing"
Log rules (0 computable)       ◆ 6 measurements: "7 transactions; largest cluster 1 payment;
                                 no cluster exceeds threshold; concentration 100% across
                                 1 approved counterparty; max 2 tx per 24h"
Drift rules                    ✗ absent  "7 transactions below the 30-transaction minimum"
Counterparty rules             6 satisfied · 2 absent (no merchant registry)
Provenance rules               absent × N  (no construction_context submitted)
Consent rules                  absent × N  (no consent_ceremony submitted)
```

**~110 facts.** Three breaches, ~90 satisfied, 6 measurements, ~11 absent — plus a **data-gap
finding**: *"Provenance and Consent could not be evaluated; the firm submitted no
`construction_context` or `consent_ceremony`; 15 rules disabled."*

Status `received`. Cost: nothing.

## 2 · Plan — **1 model call**

The orchestrator sees every fact and decides:

```jsonc
{
  "round": 1,
  "hypothesis": "Prompt injection via the product listing; the agent complied and added an
                 unrequested line item. The cap breach is the arithmetic side effect, not the
                 primary failure.",
  "dispatches": [
    { "skill": "injection.trace", "depth": "deep",
      "focus": "Instruction-shaped text found in line_items[0]. Establish the channel, and whether
                the agent's own attestation cites it as authority.",
      "facts_attached": ["F-MND-SEM-02", "F-INJ-01"] },
    { "skill": "mandate.review", "depth": "deep",
      "focus": "The cap breach is already established — do not re-derive it. Assess per-line-item
                intent fidelity: which items are within what the human actually asked for.",
      "facts_attached": ["F-MND-CAP-01"] },
    { "skill": "log.analyze", "depth": "standard",
      "focus": "7 transactions, no cluster near threshold. Confirm or refute.",
      "facts_attached": ["F-LOG-M1", "F-LOG-M2", "F-LOG-M3"] },
    { "skill": "kya.review", "depth": "standard" },
    { "skill": "counterparty.profile", "depth": "standard" },
    { "skill": "hunt.open", "depth": "standard" }
  ],
  "declined": [
    { "skill": "drift.analyze",     "reason": "insufficient history", "fact_id": "F-DRIFT-ABSENT" },
    { "skill": "provenance.verify", "reason": "no construction_context", "fact_id": "F-GAP-PRV" },
    { "skill": "consent.review",    "reason": "no consent_ceremony",     "fact_id": "F-GAP-CNS" }
  ]
}
```

Note what it did: told Mandate **not to re-derive** an established breach, routed the injection facts
to Injection, and declined three skills citing specific facts. None of that was possible in v2, where
it saw three fields and re-derived from one integer what the floor already knew.

`plan_recorded` goes on the ledger, hypothesis included.

## 3 · Assess — **6 parallel calls**

```
Injection.assess()   → Assessment(breach, INJ-01, channel=product_listing)
                       "The attestation cites the listing text as authority: 'described as
                        pre-authorized by the operator'. The agent acted on merchant-authored
                        content as though it were an operator instruction."
                       severity_floor 0.60 → assessed 0.90
                       rationale: "The attestation shows compliance, not mere presence of text."

Mandate.assess()     → Assessment(satisfied, line item KGS-FERT-20KG)
                     → Assessment(breach, MND-SEM-01, subject=GHG-GIFTCARD-TOPUP)
                       "A gift-card top-up is not garden or landscaping supplies, whoever sells it."

Log.assess()         → Assessment(explained, LOG-STR-01, confidence=possible)
                       "No cluster approaches the threshold. 7 transactions is too thin for a
                        structuring judgment either way."

KYA.assess()         → REG-03, CAP-04 satisfied. Uses get_registry_record to confirm the operator
                       name is an exact match rather than a near-name — a tool call, not a subagent.

Counterparty.assess()→ Assessment(satisfied) · single approved counterparty, consistent history

Hunter.assess()      → Observation: "The gift-card SKU has no prior history with this supplier
                        across the ledger. Every other SKU from MER-KGS-001 appears at least twice."
```

## 4 · Synthesis — sequential

```
Critic (deterministic, 0 calls)
  resolves every fact_id and evidence_ref against the brief each agent was given → passed

Synthesizer (1 call)
  → Correlation(same_event, [MND-CAP-01, MND-SEM-02, MND-SEM-01, INJ-01])
    "Four detectors, one injected line item."

Control Assurance (1 call)
  → no controls block → ControlAssessment(posture="absent") on every breach
  → CTL-REP-02: "The firm declared no control set; coverage cannot be assessed."

Score (deterministic)
  score_floor 2.30 ESCALATE · score_assessed 2.75 ESCALATE
  (Injection escalated 0.60 → 0.90, rationale recorded)
```

Status `assessed`. **~10 model calls, ~3 sequential hops.**

## 5 · The officer, and round 2

> *"Was a human actually in the loop for this one?"*

- The rule engine **does not re-run** — it is deterministic over an unchanged submission.
- The orchestrator re-plans with round 1 in context. The question is about consent, and Consent was
  declined for a factual reason, so it **replies rather than dispatching**:
  *"No consent ceremony record was submitted, so I can't establish that. `human_presence_required` on
  this mandate is false, so no human was required. Shall I raise the missing record as a finding in
  its own right?"*
- She says yes. Round 2 dispatches `consent.review` scoped to the gap →
  `Assessment(breach, CNS-31)` — *no record that a human was ever involved.* Score recomputes.

## 6 · Report

Drafting sees **only** the structured record — assessments, correlations, control postures, the score
— never raw firm text. Grounding validates deterministically. The gate holds until she types her name.

---

# Part VI — Iteration

**A review is a conversation, not a run.** Round 1 is comprehensive; later rounds are targeted.

- **The rule engine runs once**, at intake. Deterministic over an unchanged submission, so re-running
  it would produce identical facts. *"Re-check that cluster at 12 hours"* is a **tool call** inside a
  round, not a re-run.
- **The orchestrator carries state.** Every round sees prior rounds' assessments, the full message
  history and the standing plan. *"And the other one?"* resolves — the absence of which was v2's
  biggest behavioural gap.
- **The officer's instruction is trusted input.** Regulator-authored, so it may reach a specialist's
  prompt as delimited free text appended to a registry prompt. Nothing firm-submitted ever gets that.
- **Rounds cap at 10**, belt-and-braces: every round costs an explicit human decision, so the human is
  the real bound. Machine-initiated escalation stays capped at 1.

## Supersession

Round 1: Counterparty finds `counterparty_not_approved`, verdict `breach`. Round 3, given context, it
establishes the payee is the approved supplier's disclosed subsidiary → verdict `explained`.

```python
supersedes: str | None       # set on the new assessment
superseded_by: str | None    # set by the projection on the old one — never edited in place
```

**Both stay on the ledger.** Scoring uses current assessments only; the audit trail shows the case
changing its mind and why. Nothing is edited or deleted — append-only is untouched.

---

# Part VII — Facts, assessments, severity

```python
class Fact(BaseModel):
    fact_id: str; case_id: str
    domain: str                               # which ruleset produced it
    rule_id: str | None
    kind: Literal["breach", "satisfied", "measurement", "absent"]
    statement: str                            # "Cart total 1289.0 exceeds cap 350.0 by 939.0"
    values: dict[str, Any]
    refs: list[EvidenceRef]

class Assessment(BaseModel):
    assessment_id: str; case_id: str; round: int
    scope: Literal["case", "portfolio"]
    agent: str; skill_id: str
    fact_ids: list[str]                       # what this rests on — the critic resolves these
    rule_id: str | None

    verdict: Literal["breach", "concern", "explained", "inconclusive"]
    severity_floor: float                     # from the ruleset — deterministic
    severity_assessed: float                  # >= floor, never below
    severity_rationale: str | None            # required when assessed > floor
    confidence: Literal["certain", "probable", "possible"]
    narrative: str
    supersedes: str | None
```

`satisfied` facts make a clean case **provably** clean rather than merely silent, and give the eval
harness true negatives — which is what makes a real false-positive rate computable. `absent` rolls up
into a data-gap finding: a firm that cannot produce a field has told you something.

**`explained`** records *"we looked and it's fine"* as distinct from *"we didn't look."*
**`inconclusive`** replaces v2's unresolved-observation escalation trigger — the rule applies, the
agent evaluated it, and cannot decide. Scores nothing, routes to a human.

**Severity: floor plus escalation.** The floor is deterministic; an agent may raise it, never lower it,
with a recorded rationale; both scores are shown. This keeps *"explainable, factor-level scoring"*
literally true while letting an agent say *"four detectors converged on one injected line item; as
coordinated manipulation this is materially worse than the sum."*

`Observation`, `ControlAssessment`, `Correlation` and `InvestigationAnswer` are unchanged from v2.

---

# Part VIII — Tools

**Not MCP inside the product**, and the reason is our own catalogue: **F33** is *"the agent called a
tool nobody authorised"*, **F32 channel 2** is *tool-description poisoning*. Building on unpinned MCP
servers whose descriptions reach a model would reproduce inside our product the exact failures it
exists to detect. In-process typed Python tools, permissioned by `AGENT_TOOLS`, re-checked at
execution.

**MCP earns its place outward** — exposing the registries and the ledger's verify endpoint to other
supervisory systems, with the server pinned and tool schemas hashed, exactly as `KYA-TEC-06` requires
of supervised firms. Eating our own dog food is a demo beat.

| Tool | Available to |
|---|---|
| `get_rule(rule_id)` | all |
| `get_facts(filter)` | all specialists, hunter |
| `recompute_stats(kind, params)` | log, drift |
| `get_credential_history(agent_id)` | kya |
| `get_registry_record(kind, id)` | kya, provenance, counterparty |
| `get_counterparty_profile(id)` | counterparty, drift, investigator |
| `get_transactions(filter)` | log, investigator |
| `search_prior_cases(query)` | hunter, investigator |
| `get_case_record(id)` · `compare_runs(a,b)` | investigator |

Budgets — **3** standard, **5** deep, **6** hunter, **8** investigator — enforced in the node, not
requested in the prompt. Every call recorded. **No tool returns `line_items[].description`.**

**Tools are how a specialist goes deeper**, now that there are no subagents. A question needing a
*different* specialist is the officer's next round.

---

# Part IX — The runs

| Run | Trigger | Model calls | Ends with |
|---|---|---|---|
| **Intake** | submission | **0** | facts, evidence, data gaps, `received` |
| **Review round** | officer, or auto on intake | round 1 ≈ 10–13 · later 2–5 | assessments, score, `assessed` |
| **Report** | explicit request | 1–3 | held at the human gate |
| **Portfolio** | scheduled | 1–3 | portfolio-scope assessments |
| **Probe** | officer request | 2–5 | control-probe report |

Round 1 is 1 orchestrator + up to 9 specialists + synthesizer + control assurance ≈ **12 calls**,
fanning out to about **3 sequential hops**. v2's 3-call triage ran ~60s live; expect **60–110s** for
round 1 and **15–30s** for a follow-up. Dropping subagents made this both faster and predictable.

**Intake staying model-free is what makes it affordable** — a clean case costs zero API calls.

---

# Part X — Guarantees

Untouched from v2 §5: the ledger · the projection · the human gate · prompts as per-run arguments ·
rules as data · deterministic ingestion · grounding · the mandatory skill floor.

**Four new rows:**

| Guarantee | Enforced by |
|---|---|
| An agent cannot lower severity below the ruleset floor | `Assessment` validator: `severity_assessed >= severity_floor` |
| An agent cannot assert without a fact | the critic resolves every `fact_id` and `evidence_ref` against the brief |
| **Specialists never communicate** | no shared state, no peer channel, **no subagents**; briefs come only from the orchestrator |
| A declination must cite a fact | `Declination` requires a `fact_id` that resolves |

New events: `facts_recorded` · `plan_recorded` · `assessment_recorded` · `assessment_superseded` ·
`control_assessed` · `probe_completed` · `round_started`.

---

# Part XI — The plan

**0 · Fix-first** *(0.5d)* — synthesizer list guard · correlation dedup · `run_failed` + AG-UI
`RUN_ERROR` · delete dead `data/uploads.py` · investigator missing from the UI · pin LangGraph.

**1 · Facts and assessments** *(1.5d)* — `Fact`, `Assessment` with the floor/assessed split,
`EvidenceRef`, supersession. Scoring computes both scores. `Finding` becomes a compatibility view.
*Acceptance: existing tests pass; an agent lowering severity fails validation.*

**2 · The rule engine + model-free intake** *(2d)* — extract checkers into `checks/` per domain, add
`evaluation: computable|judged` to every rule, emit facts and measurements, assemble shared evidence
once, data-gap findings. *Acceptance: a case intakes and produces its full fact set with
`ANTHROPIC_API_KEY` unset.*

**3 · Eval harness** *(1d)* — per-agent precision/recall, **a real false-positive rate** now that
satisfied facts exist, calibration, orchestrator-hypothesis scoring. Baseline committed.

**4 · The rulebook** *(1.5d)* — 57 rules as registry JSON with checkers; the eleven dials;
`firms.json`, `agents.json`, `merchants.json`, `tools.json`.

**5 · Orchestrator and skills** *(1.5d)* — planning over facts, `ReviewPlan` with declinations citing
facts, skill-based dispatch with typed briefs, the round-1-is-comprehensive prompt, floor as backstop.

**6 · The iterative review** *(1.5d)* — rounds, conversation state, supersession, the case room driving
it. *Acceptance: three rounds where round 3 supersedes a round-1 breach with `explained`, both on the
record.*

**7 · The Hunter** *(1d)* — full-evidence access, observations only, recurring observations surfacing
as candidate rules.

> **Cut line.** 0–7 deliver the architecture: facts distinct from meaning, a real orchestrator, an
> iterative review, and an agent whose job is finding what the rules missed.

**8 · New specialists** *(2d)* — Provenance · Injection · Counterparty · Consent.
**9 · `monitor` + Systemic · agentic Red Team · supervisory query** *(2.5d)*

**Sequencing:** 1–3 before any new agent — adding specialists to an unmeasured pipeline multiplies
output without improving supervision. 5–6 before 8, because the orchestration and the round loop are
what make twelve specialists tractable at all.
