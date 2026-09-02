# Architecture v3 — evidence-first supervision

Branch `feat/supervision-architecture-v3`. Supersedes `architecture-v2.md` §14–18 (the run model and
agent set); everything in v2 §5 (where guarantees live) survives unchanged.

Reads with three companions on this branch:
`coverage-model.md` (73 failures, F1–F73) · `kya-ruleset.md` (57 rules) ·
`kya-and-the-sandbox.md` (positioning).

---

# Part I — The five shifts

v2 asked *"which specialists should run?"* and fanned four agents out over a case. That was right for
four agents and four rules-as-data files. It does not survive contact with eleven agents, 57 rules and
a submission carrying four new evidence blocks. Five things change.

## 1 · Computation is unconditional. Only judgment is dispatched.

**55 of the 57 rules are pure computation.** An orchestrator that decides whether to run them is
deciding whether to spend microseconds — which is why v2's dispatch was theatre: it re-derived from
one integer what a deterministic floor already knew.

In v3 the entire deterministic layer runs on every case, always, before any model is called. What the
orchestrator dispatches is **judgment** — the handful of LLM passes that cost real money and latency.

The consequence is the good part: **because the mechanical results already exist when the orchestrator
decides, it decides with knowledge of what was found.** "The cap check failed and the injection
heuristic fired — run Injection deep and Mandate's semantic check; the transaction statistics are
unremarkable, run Log standard." That is a genuine cost-benefit judgment. v2's orchestrator had three
fields and no findings.

## 2 · Evidence is assembled once, centrally, and recorded.

v2 had each agent build its own `_structured_view()`. Eight agents means eight overlapping
recomputations, eight dispatch contexts to store, and no way for KYA to see the transaction summary
that `KYA-REG-03` needs.

v3 assembles one **evidence pack** per case, deterministically, at intake. Every agent's brief is a
*view* over it. One `evidence_assembled` event carries its digest.

- Determinism becomes provable: same submission → same pack → same digest.
- Cross-agent evidence sharing is free rather than an architectural exception.
- Run-vs-run comparison gets meaningful at the evidence layer, not just the verdict layer.
- "What did we know?" is one lookup, not eight.

## 3 · Every rule evaluation is recorded — not only the failures.

v2 emitted a `Finding` when a rule tripped and *nothing at all* when it passed. So a clean case is
silent, and silence is indistinguishable from not having looked.

v3 records an **`Assessment`** for every rule evaluated, with a verdict of `pass`, `fail`,
`inconclusive`, or `not_applicable`. This buys four things that are hard to get any other way:

- **A clean case is provably clean** — "39 rules evaluated, 37 passed, 2 not applicable" is a
  supervisory statement. "No findings" is not.
- **The eval harness gets true negatives**, which means a real false-positive rate is computable for
  the first time.
- **`inconclusive` becomes expressible.** A judged rule where the model genuinely cannot decide
  currently has to lie in one direction.
- **`not_applicable` for missing data becomes a finding in itself** — see shift 5.

## 4 · The pipeline is staged, not flat.

Not all eleven specialists are peers. Control Assurance consumes the other agents' findings. Systemic
runs over the portfolio, not the case. Red Team generates rather than reads. A flat fan-out models
none of that.

```
  INTAKE            deterministic · no model
     │              verify · resolve registries · compute statistics · assemble the pack
     ▼
  ASSESS-DET        deterministic · no model · all 55 computable rules, always
     │
     ▼
  DISPATCH          the orchestrator's one real decision: which judged passes, at what depth
     │
     ├──► mandate ─┐
     ├──► kya ─────┤
     ├──► provenance ─┤   eight case-scoped peers, parallel
     ├──► injection ──┤
     ├──► counterparty ┤
     ├──► consent ────┤
     ├──► log ────────┤
     └──► drift ──────┘
                    │
                    ▼
  SYNTHESIS         sequential — each consumes what precedes it
     critic ──► synthesizer ──► control-assurance ──► score
                    │
                    ▼
  DISPOSITION       draft ⇄ ground ──► human gate
```

## 5 · Missing data is a finding, not a silent skip.

The feasibility work established that *a firm which cannot produce a field has told you something.*
v3 makes that mechanical: intake records which submission blocks are absent, every rule needing an
absent block returns `not_applicable(reason: missing_block)`, and the run emits one **data-gap
finding** naming the block and the rules it disabled.

A firm submitting no `controls` block doesn't get a clean case. It gets *"15 control rules could not
be evaluated; the firm did not submit a control set,"* which is a supervisory fact about its
governance.

---

# Part II — What agents return

Not `Finding` and `Observation`. Five record types, each with exactly one job.

## `Assessment` — the evaluation of one rule

The workhorse. Emitted for **every** rule an agent evaluates.

```python
class Assessment(BaseModel):
    assessment_id: str
    case_id: str
    scope: Literal["case", "portfolio"]      # portfolio for Systemic; ids in subject_refs
    rule_id: str                              # KYA-ACC-01 — always a registry rule
    ruleset_version: str                      # which rulebook produced this
    agent: str

    verdict: Literal["pass", "fail", "inconclusive", "not_applicable"]
    confidence: Literal["certain", "probable", "possible"]
    #   deterministic rules are ALWAYS certain — enforced in code, not convention

    subject: str | None                       # the sku / transaction / counterparty it is about
    subject_refs: list[str] = []              # case ids, for portfolio scope
    rationale: str                            # one sentence, for a human
    evidence_refs: list[EvidenceRef] = []     # structured pointers — what the critic checks
    not_applicable_reason: Literal[
        "missing_block", "out_of_scope", "insufficient_history", "rule_draft"
    ] | None = None
```

**"Finding" is the word for an Assessment whose verdict is `fail`.** It is a view, not a second type —
which is how the two stop drifting apart. Only `fail` contributes to the score, weighted by the rule's
severity and the confidence factor.

**Why `inconclusive` matters.** In v2 a judged rule had to say yes or no. A Log agent looking at a
2-transaction cluster with no threshold context had to pick. `inconclusive` says *"this rule applies,
I evaluated it, I cannot decide"* — which is honest, scores nothing, and routes to a human. It is also
the natural trigger for the escalation loop, replacing v2's "any unresolved Observation."

## `Observation` — open-ended noticing

Unchanged in spirit, narrowed in scope. **Not tied to any rule** — that is now the whole distinction.
Anything a rule covers is an Assessment; an Observation is something nobody wrote a rule for yet.
Never scored, never citable in a report, surfaced to the officer, and **the raw material for new
rules** — an observation recurring across cases is a candidate rule, which is a real feedback loop
into the registry.

## `ControlAssessment` — did the firm's own control work?

Joins to an Assessment and adds the second axis Control Assurance exists to produce.

```python
class ControlAssessment(BaseModel):
    case_id: str
    assessment_id: str                        # the finding this is about
    control_id: str | None                    # the firm's control, if one exists
    posture: Literal["absent", "failed", "bypassed", "ineffective", "effective"]
    override: OverrideRecord | None
    rationale: str
```

`posture: absent` is emitted even with no failed assessment — the coverage check (`CTL-REP-02`) is a
finding about governance, not about a payment.

## `Correlation` — relationships between assessments

As v2, with `assessment_ids` instead of `finding_ids`, and now able to relate a `pass` to a `fail`
(*"the cap control passed, which is why the semantic breach is the only route this could have taken"*).

## `InvestigationAnswer` — the response to a named human's question

As v2: answer, cited evidence, full tool-call trail. Never scored, never citable.

## What this replaces

| v2 | v3 |
|---|---|
| `Finding` | `Assessment(verdict="fail")` |
| `Observation` (rule-adjacent hunch) | `Assessment(verdict="inconclusive")` |
| `Observation` (genuinely open) | `Observation` — narrowed, and now feeds rule discovery |
| *(silence on a passing rule)* | `Assessment(verdict="pass")` |
| *(silence on missing data)* | `Assessment(verdict="not_applicable")` + a data-gap finding |

---

# Part III — The agents

Eleven specialists, five support agents. Each entry: what it is briefed with, what it may call, what
it returns.

**Every specialist has the same shape:** a deterministic pass that always runs and needs no model, and
at most one judged pass that runs only when dispatched. The deterministic pass emits Assessments for
its rules; the judged pass emits Assessments for judged rules plus Observations.

## Case-scoped peers — run in parallel in the ASSESS stage

| # | Agent | Brief *(view over the pack)* | Rules | Judged pass | Tools |
|---|---|---|---|---|---|
| 1 | **Mandate** | mandate chain · full authorization scope · merchant record · **the deterministic results already computed** | 12 `MND-*` | per-line-item intent fidelity → one Assessment per line item | `get_rule`, `get_transaction` |
| 2 | **KYA** | credential · delegation chain · issuer/firm/agent registry records · credential history · **transaction summary** *(new — `KYA-REG-03` needs it)* | 39 `KYA-*` | `REG-03` declaration-vs-reality, `CAP-04` least privilege | `get_credential_history`, `get_registry_record`, `get_rule` |
| 3 | **Provenance** | `construction_context` · tool allowlist · consent `rendered_values` vs signed Cart | 3 `KYA-TEC-*` + `PRV-*` | did the tool trace show action on untrusted content | `get_registry_record`, `get_rule` |
| 4 | **Injection** | every third-party string, per channel, delimited | `INJ-*` | which channel plausibly caused the deviation | `get_rule` |
| 5 | **Counterparty** | merchant record · sub-merchant · watchlists · cross-ledger counterparty profile | `CPY-*` | *(none — all mechanical)* | `get_counterparty_profile`, `get_registry_record` |
| 6 | **Consent** | `consent_ceremony` · Intent scope · selection context | `CNS-*` | value-for-money against the alternatives actually available | `get_rule` |
| 7 | **Log** | pre-computed cluster/velocity/concentration statistics · thresholds | `LOG-*` | pattern detections, one Assessment per instance | `recompute_stats`, `get_rule` |
| 8 | **Drift** | baseline/comparison split · PSI · z-scores · change points · event timeline | `DRIFT-*` | per-dimension drift + onset attribution | `recompute_stats`, `get_counterparty_profile` |

## Synthesis stage — sequential, each consumes what precedes

| # | Agent | Consumes | Returns |
|---|---|---|---|
| 9 | **Critic** *(deterministic)* | all Assessments + the briefs they were given | resolves every `evidence_ref` against the brief; flags unquoted values. **No model.** |
| 10 | **Synthesizer** | all Assessments | `Correlation` records; every id must resolve |
| 11 | **Control Assurance** | **all Assessments** + the firm's `controls` block | one `ControlAssessment` per finding, plus coverage findings |

> Control Assurance **cannot** be a peer in the fan-out: `CTL-EFF-01` asks whether a control that
> should have triggered did, which requires knowing what tripped. It is a tail node by necessity.

## Off-cycle

| Agent | Cadence | Returns |
|---|---|---|
| **Systemic** | scheduled portfolio sweep | `Assessment(scope="portfolio")` over `subject_refs` — many cases at once |
| **Red Team** | on-demand, officer-initiated | `ControlProbeReport` — generated adversarial cases run against the firm's *declared controls*, not our detectors |
| **Investigator** | on-demand, inside a conversation | `InvestigationAnswer` + `Observation`s. **Never an Assessment** — it has no rules, so it cannot mint a rule-backed verdict |

## Support

**Orchestrator** (dispatch + conversation) · **Drafting** (report and supervisory query) ·
**Grounding** (deterministic validator).

---

# Part IV — Orchestration and the runs

## What the orchestrator decides

It sees the pack summary **and the completed deterministic results**, and returns:

```python
class DispatchPlan(BaseModel):
    judged_passes: list[JudgedPass]   # {agent, depth: "standard"|"deep", instruction, extra_blocks}
    expected_concerns: list[str]      # a recorded hypothesis — the eval harness scores it later
    rationale: str
```

**What it may not do**, all enforced in code and carried over from v2 §5: skip a deterministic rule
(they already ran); go below the evidence floor (it names supplementary blocks, never authors them);
answer a substantive question from its own reading (its schema has no field for a verdict); rewrite a
prompt (it appends an instruction to a registry prompt).

**The floor becomes a floor on judgment**, not on execution: Mandate's semantic check and KYA's two
judged rules always run regardless of what the orchestrator proposes. Log and Drift's judged passes
run when their data minimums are met. Everything else is genuinely the orchestrator's call.

## Six runs

| Run | Trigger | Model calls | Ends with |
|---|---|---|---|
| **Intake** | submission arrives | **none** | pack assembled, data-gap findings, case `received` |
| **Assess** | officer, or automatically on intake | dispatch + judged passes | score computed, case `assessed` |
| **Investigate** | an officer message | orchestrator + 1–n agents | answer or new assessments |
| **Report** | explicit request | drafting + grounding | held at the human gate |
| **Portfolio** | scheduled | 1 | portfolio-scope assessments across many cases |
| **Probe** | officer request | 0 — generation is deterministic | control-probe report |

**Intake being model-free is the point.** A submission is verified, registries resolved, statistics
computed, gaps identified and the case is queued — with zero API cost and zero prompt-injection
surface. Roughly half the 57 rules resolve here. A clean case can be closed without ever calling a
model.

---

# Part V — Tools, and the MCP question

## Should the tools be MCP servers?

**No, inside the product. Possibly yes at the boundary.** The reasoning is our own failure catalogue.

**F33** is *"the agent called a tool nobody authorised"* and **F32 channel 2** is *tool-description
poisoning*. Building a supervision tool on unpinned MCP servers, whose tool descriptions reach a model,
would reproduce inside our product the exact failures we exist to detect. Every tool here is a
read-only function over local data; an MCP hop adds a network boundary, a trust surface and latency
for no capability gain.

**So:** in-process typed Python tools, permissioned by the existing `AGENT_TOOLS` map, re-checked at
execution. That map is what makes *"dispatcher-permissioned, not prompt-instructed"* literally true.

**Where MCP does earn its place** is the outward direction — exposing the registries and the ledger's
verify endpoint to *other* supervisory systems. If we do that, we pin the server, hash the tool
schemas and record both, exactly as `KYA-TEC-06` requires of supervised firms. **Eating our own dog
food is a demo beat**, and it is the honest way to use the protocol.

## The tool surface

Follow-up only. The pack is the brief; tools answer a *second* question.

| Tool | Returns | Available to |
|---|---|---|
| `get_rule(rule_id)` | what a rule checks, its params, status, severity | all |
| `recompute_stats(kind, params)` | log/drift statistics at different parameters | Log, Drift |
| `get_credential_history(agent_id)` | issuance series across the ledger | KYA |
| `get_registry_record(kind, id)` | issuer / firm / agent / merchant / tool record | KYA, Provenance, Counterparty |
| `get_counterparty_profile(id)` | per-counterparty aggregates, this case and across the ledger | Counterparty, Drift, Investigator |
| `get_transactions(filter)` | filtered rows from this case | Log, Investigator |
| `get_case_record(case_id)` | the projected record | Investigator |
| `compare_runs(a, b)` | run diff | Investigator |

Budget **3** per specialist, **8** for the investigator, enforced in the node. Every call recorded as a
`ToolCallRecord` on the dispatch. **No tool returns `line_items[].description`** — the injection
surface stays closed.

---

# Part VI — What carries over

Unchanged from v2, and this document does not touch any of it:

- The **ledger** — append-only, hash-chained, single-writer, no update or delete method.
- The **projection** — status derived from events, never stored.
- The **human gate** — `interrupt()`, server-stamped decisions, graph topology as the guarantee.
- The **guarantees table** (v2 §5) — every one still enforced in code, none in a prompt.
- **Prompts as per-run arguments** — fixed preamble and contract bracketing an editable body.
- **Rules as data** — versioned registry, draft/active/retired, human-gated promotion.
- **Deterministic ingestion** — now larger, but the same principle: no raw firm text reaches a model
  unparsed.
- **Grounding** — deterministic validation of the report, retry-then-block.

New event types the ledger needs: `evidence_assembled`, `assessment_recorded`,
`control_assessed`, `data_gap_recorded`, `probe_completed`. Existing types keep their shape.

---

# Part VII — The plan

Strict dependency order. Each stage lands with tests green before the next.

## Stage 0 · Fix-first — *0.5d*
Carried from `agent-design-v3.md`: synthesizer list guard · correlation dedup · `run_failed` event and
AG-UI `RUN_ERROR` · delete dead `data/uploads.py` · investigator missing from the UI roster · pin
LangGraph or register the msgpack types.

## Stage 1 · The output model — *1d*
`Assessment` with verdict/confidence/subject/`evidence_refs`; `ControlAssessment`; `scope`;
real id counters. Migrate `Finding` → `Assessment(verdict="fail")` behind a compatibility view so the
existing pipeline keeps running. Scoring reads `fail` only, weighted by confidence.
**Acceptance:** every existing test passes with findings expressed as assessments.

## Stage 2 · The evidence pack + model-free intake — *1.5d*
`EvidencePack` assembled deterministically at intake; `evidence_assembled` recorded with a digest;
agent briefs become views over it; data-gap detection and findings.
**Acceptance:** a case can be intaken, verified and gap-checked with `ANTHROPIC_API_KEY` unset.

## Stage 3 · Eval harness — *1d*
Per-agent precision/recall, **a real false-positive rate now that passes are recorded**, calibration
report, confidence calibration. `make eval` produces the baseline every later stage is measured
against.

## Stage 4 · The rulebook — *1.5d*
`KYA-*` (42) and `CTL-*` (15) as registry JSON; checkers for each; the eleven dials as named params;
`firms.json`, `agents.json`, `merchants.json`, `tools.json`.
**Acceptance:** every active rule has a checker, and the coverage-gap test still fails loudly on a
rule without one.

## Stage 5 · Staged pipeline + orchestrator — *1.5d*
Split ASSESS-DET from the judged passes; sequential synthesis stage; Control Assurance as a tail node;
orchestrator dispatching judgment with the deterministic results in view, recording a hypothesis.

## Stage 6 · The new specialists — *2d*
Provenance · Injection · Counterparty · Consent. Each is a deterministic floor plus at most one judged
pass, on the pack.

## Stage 7 · `monitor` disposition + Systemic — *1.5d*
The fourth disposition and `case_watched`; the portfolio run consuming watched cases;
`Assessment(scope="portfolio")`.

> **Cut line.** Stages 0–5 deliver the architecture: recorded evidence, complete assessments,
> measurable agents, a real rulebook, and an orchestrator that decides something. 6–7 are coverage.

## Stage 8 · Red Team · supervisory query · run-compare UI — *2d*
Everything that is upgrade rather than foundation.

## Sequencing note

**Stages 1–3 before any new agent.** Adding specialists to an unmeasured pipeline multiplies output
without improving supervision — which is the mistake v2 made and this document exists to correct.
