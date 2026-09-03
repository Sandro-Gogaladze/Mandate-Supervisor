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

## Agents own their rules end to end

A domain is a **ruleset plus an agent**, and the agent runs the whole thing. Nothing evaluates rules
outside the agent that owns them.

```python
class Specialist:
    ruleset_id = "kya"

    async def review(self, evidence, brief) -> SpecialistReport:
        facts = self.check(evidence)            # 1 · MY rules, deterministic, no model
        return await self.reason(facts, brief)  # 2 · interpret  3 · hunt in-domain
```

**One pass, three moves** — check, interpret, notice — which is how a domain expert actually works.

Two details that matter:

- **`check()` is the node's code, not a tool the model chooses to call.** Exposing it as a tool would
  let a model skip its own rulebook, and a specialist silently not running its rules is a coverage
  hole nobody would notice. It is still the agent running its own rules; it just isn't optional.
- **Data preparation is shared; rule evaluation is not.** Intake verifies signatures, resolves
  registries and computes statistics *once* — otherwise Log and Drift each build the same dataframe
  and can end up citing different numbers for the same thing, which is a credibility problem in a
  supervisory file. Rule evaluation stays entirely inside the agents.

**Only the orchestrator runs before the specialists**, and on round 1 it has nothing to decide — it
dispatches everything. Its judgment lands from round 2, when it holds every fact and assessment
round 1 produced.

## Not every rule is code

Each rule declares its own evaluation mode in the ruleset JSON:

```jsonc
{ "rule_id": "MND-CAP-01", "evaluation": "computable" }   // arithmetic → check()
{ "rule_id": "MND-SEM-01", "evaluation": "judged"     }   // semantic   → reason()
```

Roughly **one rule in seven is judged**. Both halves run inside the owning agent, in one dispatched
pass — `check()` first, then `reason()` over the facts it produced.

### What `check()` produces for a domain whose rules are all judged

Log's rules are *all* model-judged, so a naive `check()` would emit nothing and the agent would reason
from raw rows.

**`check()` emits two kinds of fact:**

| Kind | Source | Example |
|---|---|---|
| **rule outcome** — `breach` · `satisfied` · `absent` | a computable rule | *"Cart total 1289.0 exceeds cap 350.0 by 939.0"* `MND-CAP-01` |
| **measurement** | deterministic computation behind a *judged* rule | *"Cluster: 3 payments to MER-X within 6h, ₾2,900 + ₾2,850 + ₾2,950 = ₾8,700, threshold ₾3,000"* |

So Log's `check()` computes every cluster, velocity and concentration number as a **measurement**, and
its reasoning pass turns those into a verdict on `LOG-STR-01`. The model never sees raw transaction
rows and reaches for a calculator — it sees computed evidence and judges it.

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

# Part I·5 — The rulebook in operation

Answering, precisely: what are the rules, when do they run, who runs which, what is automatic, and is
anything run that isn't a rule.

## Is KYA the whole rulebook? No — it is one of nine

`KYA-*` covers **the agent's identity and standing only**. Eight other rulesets cover everything else,
and each has exactly one owner.

| Ruleset | Owner agent | Question it answers | Rules | Judged |
|---|---|---|---|---|
| `KYA-*` | KYA | Is this agent legitimately who it claims, with authority tracing to an accountable human? | 42 | 2 |
| `MND-*` | Mandate | Was this payment within what the human signed? | 12 | 1 |
| `PRV-*` | Provenance | Was the mandate assembled from trustworthy inputs? | ~8 | 1 |
| `INJ-*` | Injection | Was the agent manipulated by content it read? | ~6 | 1 |
| `CPY-*` | Counterparty | Who received the money, and are they who they claim? | ~8 | 0 |
| `CNS-*` | Consent & Harm | Was the human there, and is the consumer worse off? | ~9 | 1 |
| `LOG-*` | Log | What does the transaction pattern reveal? | ~7 | most |
| `DRIFT-*` | Drift | What changed against this agent's own baseline? | 3 | 3 |
| `CTL-*` | Control Assurance | Did the firm's own controls work? | 15 | 0 |

**No agent evaluates another agent's ruleset.** The mapping is one-to-one and it is how a rule finds
its runner: `Rule.ruleset` names the domain, the domain names the agent.

The **Hunter has no ruleset by design.** Its whole job is what no rule covers, which is why it can
have no rulebook — and why its output is `Observation` only, never a rule-backed assessment.

## When each rule runs

Every rule declares its own evaluation mode, in the ruleset JSON:

```jsonc
{ "rule_id": "KYA-ACC-01", "evaluation": "computable" }   // code · runs in check()
{ "rule_id": "KYA-REG-03", "evaluation": "judged"     }   // model · runs in reason()
```

Both run **inside the same agent, in the same pass**:

```
KYA agent dispatched
  ├─ 1. check()   evaluates all 40 computable KYA rules  →  facts
  ├─ 2. reason()  evaluates the 2 judged KYA rules, over those facts
  └─ 3. hunt      notices anything in the KYA domain no rule covers
```

So `KYA-ACC-01` (does the delegation chain reach a human?) is pure code and always produces a fact.
`KYA-REG-03` (does observed activity match the declared classification?) needs a model and produces an
assessment. **Both are KYA's, both run when KYA runs, neither runs anywhere else.**

## What is automatic, and what is not

| | Automatic | Decided |
|---|---|---|
| **Intake** — verify, resolve registries, compute statistics | ✅ always, on every submission, 0 model calls | — |
| **Round 1 dispatch** | — | the orchestrator decides, but its prompt says a first pass is comprehensive, so in practice: everything with data |
| **A rule inside a dispatched agent** | ✅ **always** — an agent never picks which of its rules to run | — |
| **Round 2+ dispatch** | — | the orchestrator judges the officer's question against round 1's facts |
| **Synthesis** (critic → synthesizer → control assurance → score) | ✅ always, after any round | — |
| **Report** | — | only on explicit request |
| **Portfolio sweep** | ✅ scheduled | — |
| **Red Team probe** | — | officer-initiated only |

**The line that matters: an agent never chooses which of its rules to run.** Dispatch is a decision;
rule coverage inside a dispatched agent is not. If KYA runs, all 42 KYA rules are evaluated. That is
what makes coverage claimable — *"we evaluated 42 identity rules"* is true or the agent didn't run.

## Is anything run that isn't a rule?

Yes, three things — and keeping them distinct from rules is what stops the rulebook becoming a
dumping ground.

**1 · Verification and resolution, at intake.** Ed25519 signature checks, chain-hash recomputation,
registry lookups, statistical computation. These are *inputs to* rules, not rules. `KYA-IDN-01`
("the signature verifies") is the rule; the actual elliptic-curve verification is machinery it calls.

**2 · In-domain hunting, inside every agent.** After evaluating its rules, each agent looks for what
its rules don't cover. Output is `Observation` — unscored, uncitable, surfaced to the officer, and
**the raw material for new rules**. An observation recurring across cases is a candidate rule, which
is how the rulebook grows past 110 without anyone guessing in advance.

**3 · The synthesis stage.** The critic resolves evidence references (deterministic, no rules). The
synthesizer relates assessments to each other (`Correlation`, not a rule outcome). Scoring is
arithmetic over assessments. None of these evaluates a rule; all of them operate on rule output.

## How many rules run on a case

With every agent dispatched and all evidence blocks present: **~110 rules across nine rulesets**, of
which about 15 are judged. On CASE-2026-007, where the firm submitted no `construction_context` or
`consent_ceremony`, Provenance and Consent report their rules `absent` and the case carries a data-gap
finding instead.

---

# Part II — The shape

```
   submission
       │
       ▼
┌──────────────────────────────────────────────────────────────────────┐
│  INTAKE — code only, 0 model calls                                   │
│    verify signatures and chains · resolve registries                 │
│    compute shared statistics once (profiles, baselines, clusters)    │
│    note which submission blocks are present                          │
│    ──────────────────────────────────────► the EVIDENCE PACK         │
│    No rules evaluated here. Rules belong to agents.                  │
└──────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────────┐
│  ORCHESTRATOR — 1 call                                               │
│    round 1: dispatch every agent whose evidence block is present     │
│             (nothing to decide — its prompt says a first pass is     │
│              comprehensive; the floor is a backstop, not the driver) │
│    round 2+: judge the officer's question against every fact and     │
│              assessment round 1 produced, dispatch what is relevant  │
└──────────────────────────────────────────────────────────────────────┘
       │  dispatches skills with briefs — agents never talk to each other
       ├──► mandate      ├──► counterparty   ├──► log
       ├──► kya          ├──► consent        ├──► drift
       ├──► provenance   ├──► injection      ├──► control assurance
       │                                     └──► hunter (cross-domain only)
       │
       │   EACH AGENT, ONE PASS:   1 · check()  its rules → facts
       │                           2 · reason   over its facts
       │                           3 · hunt     in its own domain
       │                           → assessments + observations
       ▼
┌──────────────────────────────────────────────────────────────────────┐
│  SYNTHESIS — sequential, each consumes what precedes                 │
│    critic (deterministic) → synthesizer → score                      │
│    the synthesizer joins fact → assessment → control posture         │
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

## Dispatched per round — ten, in parallel

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

| 10 | **Control Assurance** | `controls.assess` | F70–F73 · 15 `CTL-*` | *(none — mechanical)* |

### Why Control Assurance is a peer after all

An earlier draft made it sequential, reasoning that `CTL-EFF-01` ("did a control that *should* have
triggered actually trigger?") needs to know what tripped. **That generalised from one rule to the whole
agent, and it was wrong on both counts.**

**14 of the 15 `CTL-*` rules have no dependency at all.** Coverage (`CTL-REP-02`) reads the *mandate's*
risk surface — the caps and scopes the firm itself declared — not anyone's findings. Disposition rules
read the control execution log against the transaction log. Override rate, audit-log completeness,
tamper-evidence: all self-contained.

**And `CTL-EFF-01` doesn't need Mandate either.** It holds the mandate (cap ₾350) and the transaction
(₾1,289); "a cap breach occurred" is the same arithmetic, available from shared evidence. It asks a
different question from Mandate's — *did your control fire*, not *was this authorised* — and it can
answer it independently.

So Control Assurance runs in parallel with the rest, and **`ControlPosture` links to a `fact_id`
rather than an `assessment_id`.** Facts are the better anchor anyway: they are stable, whereas an
assessment can be superseded in a later round. The synthesis stage joins fact → assessment → posture
when it assembles the case.

## Off-cycle

| # | Specialist | Skill | Cadence |
|---|---|---|---|
| 11 | **Systemic** | `portfolio.sweep` | scheduled, across the ledger |
| 12 | **Red Team** | `probe.generate` | on-demand; LLM-generated attacks against the firm's *declared* controls |

**Support:** Orchestrator · Investigator · Critic *(deterministic)* · Synthesizer · Drafting ·
Grounding *(deterministic)*.

## The Hunter — and what it is told *not* to look at

The failure catalogue has 73 entries. A real attacker invents #74, and no rule will catch it, because
rules only catch what someone already wrote down. The Hunter gets the **whole** evidence set and **all**
facts with no domain boundary.

**Every other agent already hunts inside its own domain**, so a Hunter repeating that is pure waste and
noise. Its brief is therefore an *exclusion*, and its prompt carries two things no other agent gets:

1. **The domain map** — what each of the ten specialists covers, stated as territory to stay out of.
   *"Mandate has scope, caps, counterparty and currency. KYA has identity, accreditation and
   delegation. Log has structuring, velocity and concentration. Do not report in these terms."*
2. **The full rule inventory across all nine rulesets** — so it can check whether a rule already exists
   for what it noticed, and say so if it does.

What it is asked for instead:

- **Cross-domain relationships** no single specialist could see — a counterparty appearing the day
  after a credential reissue spans KYA and Counterparty, and neither owns it.
- **Patterns with no rule anywhere**, in any ruleset, in any domain.
- **Absences** — something a case of this shape should contain and doesn't.

Observations only, never scored, never citable. **Its output feeds the registry:** an observation
recurring across cases becomes a candidate rule. That is the loop from discovery to policy, and what
gives the policy sandbox real inputs rather than guesses.

---

# Part IV — The orchestrator

## It decides, including on round 1

**Round 1 is a full review because the orchestrator decides it should be**, not because a floor
bypasses it. Its default prompt says so:

> *"A first pass on a new case is comprehensive. Dispatch every skill whose data prerequisites are met.
> Your judgment on this pass is about **depth and focus** — which skills need deep attention and what
> each should concentrate on given what the last round established — not about whether to
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
                       name is an exact match rather than a near-name.

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

- `check()` **does not re-run** — it is deterministic over an unchanged submission.
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

- **Each agent's `check()` runs once**, in its round-1 dispatch. Deterministic over an unchanged submission, so re-running
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

# Part X·5 — Everything this needs before it works

The architecture is the easy half. Below is every input it depends on, where each comes from, and what
is blocked without it. Sourcing and feasibility are argued in `coverage-model.md` Part 3; this is the
checklist.

## A · Submitted by the firm — four new blocks

Six of twelve specialists cannot function on what firms send today. **All of it exists in a system a
bank already runs**; nothing here is a research problem.

| Block | Unblocks | Where the firm gets it | Effort |
|---|---|---|---|
| **`consent_ceremony`** — occurred, timestamp, principal, method, **`rendered_values`**, scope, supersedes | F24–F27, F29–F31 · the `CNS-*` ruleset · Consent agent | Most of it is **PSD2 Strong Customer Authentication logs**, which every EU-aligned bank already keeps. `rendered_values` is the consent UI serialising what it displayed. | ~20 lines at the confirm handler |
| **`construction_context`** — model declared/observed, policy hash, tool calls with `server_id` and `tool_schema_hash`, bounded `selection_context` | F32, F33, F35–F38 · `PRV-*` and `INJ-*` · Provenance + Injection | Model version is in the LLM provider's API response. Tool calls are in **agent observability that already exists** — LangSmith, Langfuse, OTel traces. | days |
| **`controls`** — declared control set + execution log with overrides | F70–F73 · the `CTL-*` ruleset · Control Assurance | The **fraud/transaction-monitoring engine's own decision log**. Overrides are already logged for audit. | mapping only |
| **merchant fields** — `region`, `sub_merchant` | F48, F52 · part of `CPY-*` | Acquirer data. **Sub-merchant disclosure is already a Visa/Mastercard PayFac requirement** — it just isn't surfaced to the paying side. | plumbing |

**Deliberately not requested:** screenshots · provider-signed model attestation · full catalog
archives · A2A transcripts. F28 and F34 are parked as a result, and the docs say so.

## B · Held by the regulator — four registries

| Registry | Unblocks | Where it comes from |
|---|---|---|
| `data/registry/firms.json` | 4 `KYA-OPF-*` + `KYA-ACC-07` | **The existing NBG licensing register.** Pure re-use — licence status, standing, ownership dates, compliance contact |
| `data/registry/agents.json` | 5 `KYA-REG-*` + `KYA-ISS-05` + 3 `KYA-TEC-*` | **Does not exist anywhere — this is the policy proposal.** An agent registration regime: declare the agent, operator, classification and pinned model before it may transact |
| `data/registry/merchants.json` | `CPY-*` · F51, F53, F54 | Company register + acquirer reporting, incl. the beneficial-ownership record the paying firm can't supply |
| `data/registry/tools.json` | `KYA-TEC-06` · F33 | Firms declare their tool/MCP stack at agent registration — one row per tool |
| *(exists)* `data/registry/issuers.json` | 5 `KYA-ISS-*` | Already built |

## C · Derived from the ledger — no new data at all

**Twelve failures need nothing from anyone.** All computable from events already stored:

- **Credential history** per `agent_id` — from prior `case_submitted` events. Unblocks `KYA-IDN-04/05`,
  `KYA-CAP-05`, `KYA-LIF-04` (creep, key reuse, id collision, rotation overlap).
- **Mandate consumption** — unblocks F50, mandate replay.
- **Cross-case counterparty profile** — unblocks F57, the same payee across unrelated firms.
- **Cross-firm model versions, timing, cart shapes** — unblocks the entire Systemic tier, F67–F69.

## D · The rulebooks — nine, four still to write

| Ruleset | State | Work |
|---|---|---|
| `KYA-*` | **42 rules shipped**, 18 active, 24 draft | promote drafts as B lands |
| `CTL-*` | specified in `kya-ruleset.md` | write JSON + 15 checkers |
| `MND-*` | 12 exist | add `MND-SEM-03`, promote geographic scope (needs `Merchant.region`) |
| `LOG-*` | 3 exist | add round amounts, off-hours, limit probing, alert flooding |
| `DRIFT-*` | 1 exists | split into amount / frequency / mix — also fixes the case-006 calibration structurally |
| `PRV-*` `INJ-*` `CPY-*` `CNS-*` | none | write from `coverage-model.md`'s failure ids |

## E · Prompts — one per agent, in `registry/prompts/`

Ten exist. **Six new:** `specialist-provenance`, `specialist-injection`, `specialist-counterparty`,
`specialist-consent`, `specialist-controls`, `hunter`. Plus a rewritten `orch-session` carrying the
round-1-is-comprehensive instruction, and a `hunter` prompt carrying the domain-exclusion map and the
full rule inventory.

## F · Scoring config — `registry/scoring.json`

- **Confidence factors** — certain / probable / possible.
- **`same_event` de-duplication factor** — how much a second detector on the *same* event adds.
- **`corroborating` compounding factor** — how much a second detector on a *different* event adds.
- **Per-rule-class floors** — a cryptographic chain break is categorically escalate.
- **The fourth disposition, `monitor`**, plus a `case_watched` ledger state. Without it, drift
  findings, `possible`-confidence assessments and portfolio concentrations are all forced into
  `clear` or `review`.

## G · Corpus — two new cases, two edits

| Case | Change | Demonstrates |
|---|---|---|
| **new case-008** | `consent_ceremony.rendered_values.amount = 50.00` against a signed Cart of ₾1,200 | **F29** — every existing check passes and one comparison exposes it. The best single demo beat available |
| **case-002** | add `controls` with the ₾500 cap declared, `outcome: triggered`, plus an `override` | **F72** — turns a cap breach into a conduct question |
| **case-007** | add `construction_context` with the poisoned listing, plus a variant carrying it in the **tool description** | **F32** with a `channel` field — one attack, two routes, one currently invisible |
| **+2 firms** | same `observed_model_version` across three firms | **F67** monoculture — needs no new fields, only more cases |

## H · The eleven dials

Named in `kya-ruleset.md` Part 5, all registry data: delegation depth · issuer-tier-by-risk-class ·
re-accreditation age · credential validity window · capability vocabulary · least-privilege tolerance ·
capability-creep tolerance · model blocklist · validation-required-above · **override rate** · and
**the severity weights**, which is the dial that actually determines outcomes and the one most likely
to be wrong on first pass.

## What is genuinely blocking

**Nothing, for stages 0–3.** Facts, assessments, agent-owned checks, shared evidence and the eval
harness all run on data that exists today. **B (registries) gates the KYA promotions; A (submission
blocks) gates the four new specialists.** Both are synthetic for the demo — hours of JSON, not weeks —
and the feasibility argument for the real version is in `coverage-model.md`.

---

# Part XI — The plan

**0 · Fix-first** *(0.5d)* — synthesizer list guard · correlation dedup · `run_failed` + AG-UI
`RUN_ERROR` · delete dead `data/uploads.py` · investigator missing from the UI · pin LangGraph.

**1 · Facts and assessments** *(1.5d)* — `Fact`, `Assessment` with the floor/assessed split,
`EvidenceRef`, supersession. Scoring computes both scores. `Finding` becomes a compatibility view.
*Acceptance: existing tests pass; an agent lowering severity fails validation.*

**2 · Agent checks emit facts + shared evidence** *(2d)* — each specialist's `check()` returns `Fact`s
instead of `Finding`s, emitting measurements for its judged rules; shared evidence assembled
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
