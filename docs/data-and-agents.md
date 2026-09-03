# Data and agents — the definitive map

What every agent needs, what the submission contains, where a bank actually gets each field, and
what is wrong with the corpus today.

Reads with `coverage-model.md` (failures F1–F73 and the data contract), `kya-ruleset.md` (the 57
rules), `architecture-v3.md` (the pipeline), and `synthetic-data-spec.md` (corpus design).

**Written against the corpus as it actually is, not as intended.** Part 5 lists nine defects found by
auditing `DOSSIER-KST-2026-001` against the rulebook. All nine were unplanted.

---

# Part 1 — The two halves of the data

Everything splits on one line: **anything an operator could shade in its own favour lives
regulator-side.**

```
SUBMITTED by the institution                 HELD by the regulator
────────────────────────────────             ──────────────────────────────
dossier.json    what the runs share          institutions.json   who may submit
runs/*.json     50 complete AP2 chains       operators.json      who may operate
transactions.json  the ledger                agents.json         WHICH AGENTS EXIST ← the proposal
ground_truth.json  eval only, never shipped  merchants.json      who was really paid
                                             tools.json          which servers are authorised
                                             model_blocklist.json which models are barred
                                             issuers.json        which credentials count
```

The operator declares which model it used — `self_attested_by`, and the data contract is explicit
that this catches misconfiguration and silent upgrades, not a determined liar. Whether that model is
*blocked*, whether that prompt release was *approved*, and who *owns* the merchant are all facts the
regulator keeps. That asymmetry is the design.

## 1.1 · What the submission contains

| File | Holds | Why it is not somewhere else |
|---|---|---|
| `dossier.json` | ids · `submission_context` · `kya_credential` + `credential_history` · `agent_card` · `controls` · `change_log` · `run_index` | Everything the 50 runs share. Copying it into each run would let 50 copies drift apart |
| `runs/RUN-*.json` | one complete AP2 chain each: `intent_mandate` → `construction_context` → `consent_ceremony` → `cart` → `payment` → `controls_evaluated` | Runs are produced independently, one execution each. AP2's human-present flow makes the shopper's request the mandate, so the mandate belongs to the run |
| `transactions.json` | 102 rows — 47 in-window with `run_ref`, 55 trailing without | Drift needs 30+ for a baseline/comparison split. Fifty runs alone leave a third of the rulebook `absent`. A transaction with no `run_ref` *inside* the window is itself a finding |
| `ground_truth.json` | `planted[]` · `clean_runs[]` · `narrative` | Separate file so `load_for_pipeline()` withholds it by not opening it, rather than a `model_copy` someone forgets to call |

---

# Part 2 — The KYA ruleset: 42 rules, 8 families

`registry/rulesets/kya.json` v2026.3 — **18 active, 24 draft, 2 judged.**

A draft rule is not an unfinished one. It is a rule whose evidence the submission does not yet carry;
promoting it is a data question, not a coding one.

### A · `IDN` — identity is cryptographically sound (5)

| Rule | Asserts | Status | Needs |
|---|---|---|---|
| `IDN-01` | credential signature verifies against the issuer key | active | credential + keystore |
| `IDN-02` | signature algorithm is on the allowlist | active | credential |
| `IDN-03` | signed payload hash recomputes over canonical content | active | credential |
| `IDN-04` | the signer key backs no other agent identity | draft | **cross-case ledger** |
| `IDN-05` | the credential id is unique across the register | draft | **cross-case ledger** |

### B · `ISS` — the issuer is accredited and current (5)

| Rule | Asserts | Status | Needs |
|---|---|---|---|
| `ISS-01` | issuer is in the trust registry | active | `issuers.json` |
| `ISS-02` | issuer was not revoked at the issue date | active | `issuers.json` |
| `ISS-03` | issuer trust tier meets the minimum for this mandate | active | `issuers.json` |
| `ISS-04` | accreditation reviewed within the maximum age | active | `issuers.json` |
| `ISS-05` | issuer is accredited for **this agent classification** | draft | `issuers.authorised_classifications` — **missing** |

### C · `ACC` — authority traces to an accountable human (7)

| Rule | Asserts | Status | Needs |
|---|---|---|---|
| `ACC-01` | the chain terminates in a natural person | active | delegation chain |
| `ACC-02` | the terminus is the principal that signed the Intent | active | chain + intent |
| `ACC-03` | every delegation signature verifies | active | chain + keystore |
| `ACC-04` | no holder appears twice | active | chain |
| `ACC-05` | chain depth within maximum | active | chain |
| `ACC-06` | **no link grants more authority than the granting holder holds** | draft | `granted_capabilities` per level — **now present** |
| `ACC-07` | terminus is on the operator's authorised-signatory list | draft | `operators.authorised_signatories` — present |

`ACC-06` is F11, and it was undetectable until the delegation chain recorded what each level was
*granted* rather than only who each level *was*. A chain of names and signatures is not a record of
delegated authority.

### D · `OPF` — the operator firm is fit to run it (4)

| Rule | Asserts | Status | Needs |
|---|---|---|---|
| `OPF-01` | the operator holds a current licence or registration | draft | `operators.licence_status` — **missing** |
| `OPF-02` | standing is not in a barring state | draft | `operators.standing` — present |
| `OPF-03` | no unnotified change of control since issuance | draft | `operators.ownership_changes` — present |
| `OPF-04` | a named compliance contact is on record | draft | `operators.compliance_contact` — present |

### E · `REG` — the agent is declared and classified (5)

| Rule | Asserts | Status | Needs |
|---|---|---|---|
| `REG-01` | registered before its first transaction | draft | `agents.registered_at` — present |
| `REG-02` | a risk classification is declared | draft | `agents.risk_class` — present |
| `REG-03` | observed activity is consistent with the classification | draft · **judged** | **transaction summary in KYA's evidence block** |
| `REG-04` | the registration is current | draft | `agents.authorisation_expires` — **null** |
| `REG-05` | the registered purpose matches `purpose_category` | draft | `agents.registered_purpose_category` — **missing** |

`REG-03` is the only rule in the book that needs the evidence floor widened: it requires a
transaction summary (count, total, max single, distinct counterparties) that today only Log and Drift
see. That is what `compose_context()` exists for — no new field from any firm.

### F · `TEC` — the technical substrate is declared and controlled (6)

| Rule | Asserts | Status | Owner | Needs |
|---|---|---|---|---|
| `TEC-01` | a model version is declared on the mandate | active | KYA | mandate |
| `TEC-02` | observed model matches declared | draft | **Provenance** | `construction_context.model` |
| `TEC-03` | the model is not blocklisted | draft | KYA | `model_blocklist.json` |
| `TEC-04` | validation evidence is on file | draft | KYA | `agents.validation_evidence` |
| `TEC-05` | the prompt is bound to a released artifact | draft | **Provenance** | `policy_version` + `approved_prompt_releases` |
| `TEC-06` | every tool server used is declared | draft | **Provenance** | `tool_calls` + `tools.json` |

**The family splits across two agents on evidence, not on topic** — three rules are answered from the
agent registry, three from `construction_context`. Splitting on evidence also removes a duplication:
F37 was assigned to Provenance in the coverage model and would have been re-asserted by KYA here.

### G · `CAP` — capability proportionality (5)

| Rule | Asserts | Status | Needs |
|---|---|---|---|
| `CAP-01` | capabilities are non-empty | active | credential |
| `CAP-02` | all capabilities are in the allowed vocabulary | active | credential |
| `CAP-03` | capabilities are sufficient for the declared purpose | draft | `agents.declared_purpose` |
| `CAP-04` | capabilities are not materially broader than the purpose | draft · **judged** | `agents.declared_purpose` |
| `CAP-05` | no capability creep across reissuance | draft | `credential_history` — **now present** |

### H · `LIF` — credential lifecycle (5)

| Rule | Asserts | Status | Needs |
|---|---|---|---|
| `LIF-01` | not expired at time of use | active | credential |
| `LIF-02` | `issued_at` precedes `expires_at` | active | credential |
| `LIF-03` | the validity window meets the minimum | active | credential |
| `LIF-04` | no two credentials for one agent valid simultaneously | draft | `credential_history` — **now present** |
| `LIF-05` | revocation checked within the staleness limit | draft | `revocation_checked_at` — **missing** |

---

# Part 3 — The controls ruleset: 15 `CTL-*` rules

**Specified in `kya-ruleset.md`, and not implemented — there is no `registry/rulesets/ctl.json`.**
This is the largest single gap between the design and the code.

| Rule | Asserts | Prevents | Weight |
|---|---|---|---|
| `CTL-REP-01` | a declared control set exists | governance by assertion | 0.70 |
| `CTL-REP-02` | every risk the mandate creates has a declared control | **F70** | 0.75 |
| `CTL-REP-03` | controls are versioned and pinnable to what ran | untraceable controls | 0.45 |
| `CTL-REP-04` | each control declares blocking or advisory | a control everyone believed was blocking | 0.35 |
| `CTL-DIS-01` | every action was evaluated before execution | bypassing the checkpoint | 0.85 |
| `CTL-DIS-02` | a disposition is recorded for each evaluation | an engine that decides silently | 0.55 |
| `CTL-DIS-03` | *human review* dispositions carry a human decision | escalation on paper only | 0.80 |
| `CTL-DIS-04` | nothing executed after a *reject* | **the control said no and it happened** | 1.00 |
| `CTL-EFF-01` | a control that should have triggered did | **F71** | 0.80 |
| `CTL-EFF-02` | no override without recorded authority and reason | **F72** | 0.85 |
| `CTL-EFF-03` | the override rate is within maximum | normalised deviance | 0.65 |
| `CTL-EFF-04` | a triggered blocking control has no settled transaction | **F73** | 0.90 |
| `CTL-LOG-01` | an audit log covers the reporting period | gaps where the activity is | 0.60 |
| `CTL-LOG-02` | the log is tamper-evident | a log editable after the fact | 0.55 |
| `CTL-LOG-03` | log entries reconcile to settlement | **silent omission** | 0.75 |

`CTL-EFF-01` consumes the *other agents' findings*, which is why Control Assurance runs after the
peer fan-out rather than inside it.

---

# Part 4 — Which agent gets what

**The assignment principle:** a rule belongs to the agent whose evidence block already contains
everything it needs — not the agent it sounds related to. That resolves boundary cases mechanically
and keeps the floor honest: an agent is never asked a question its brief cannot answer.

| | Agent | Question | Owns | Evidence block | Fed? |
|---|---|---|---|---|---|
| A1 | **Mandate** | Within what the human signed? | F39–F50 · 13 `MND-*` | run `intent_mandate` + `cart` + `payment` + `chain_link` + `merchant.region` + `usage` | ✅ |
| A2 | **KYA** | Authority traceable to a human? | F1–F23 · 39 `KYA-*` | `kya_credential` + `credential_history` + issuers/operators/agents + **tx summary** | ⚠️ 5 registry fields short |
| B1 | **Provenance** | Inputs anyone should trust? | F33, F36, F37 · `TEC-02/05/06` | `construction_context` + `agent_card` + `tools.json` | ✅ |
| B2 | **Injection** | Manipulated by what it read — which channel? | F32, F35 | `user_prompt` · `line_items[].description` · `result_excerpt` · `tool_schema_hash` | ✅ all 4 channels |
| C1 | **Counterparty** | Who received this money? | F51–F58 | `merchants.json` + `sub_merchant` + `payment.payee` + tx history | ✅ |
| C2 | **Consent & Harm** | Was the human there; is the consumer worse off? | F24–F31, F38 | `consent_ceremony` (8 fields) + `selection_context` (5 alternatives) | ✅ |
| D1 | **Log** | What does this history reveal? | F59–F64, F66 · 3 `LOG-*` | transactions + operator timezone + **reporting threshold (a dial)** | ⚠️ dial unset |
| D2 | **Drift** | What changed, **and when did it start**? | F65 · 1 `DRIFT-*` | 55-row baseline + `change_log` | ✅ |
| E1 | **Control Assurance** | Did the firm's own controls work? | F70–F73 · 15 `CTL-*` | `controls` (both owners) + `controls_evaluated` + peer findings | ⚠️ **no ruleset exists** |
| E2 | **Systemic** | What's true across the portfolio? | F67–F69, F57 at scale | many dossiers | ❌ one dossier |
| E3 | **Red Team** | Does it hold up when pushed? | on demand | the mandate's own parameters | ✅ |

---

# Part 5 — The audit, and what it found  *(all resolved)*

Found by auditing the corpus against the rulebook rather than assuming it was
sound. **All nine were unplanted.**

| | Defect | Rule | Fix |
|---|---|---|---|
| 1 | Delegation chain never reached a human — agent → operator → institution, all orgs | `ACC-01` | A named accountable officer now terminates the chain |
| 2 | All three credentials overlapped in time | `LIF-04` | Windows staggered; **one overlap kept deliberately and declared**, so the rule is exercised rather than merely satisfied |
| 3–7 | Five registry fields missing: `authorised_classifications`, `licence_status`, `authorisation_expires`, `registered_purpose_category`, `revocation_checked_at` | `ISS-05` `OPF-01` `REG-04` `REG-05` `LIF-05` | Added; all five rules promoted |
| 8 | `ctl.json` did not exist — 15 rules specified, 0 implemented | all `CTL-*` | Written and active with checkers |
| 9 | `round_50` share 5.9% against a 6–10% target | realism | 6.9% |

Defects 1 and 2 mattered most: both would have been reported by a correct
implementation against runs the ground truth called **clean**, scoring as false
positives against a corpus that was itself wrong.

## 5.1 · Three rule-design faults the corpus exposed

Not data problems. Rules that were wrong, and only showed it once real data met
them.

**`ACC-02` breaks on consumer mandates.** It asserts the delegation chain
terminates in the principal who signed the Intent — true of corporate
delegation, where one officer both delegates to the agent and signs. In AP2's
human-present flow they are structurally different people: the shopper signs
their own Intent while the agent's chain terminates at the *operator's* officer.
Unscoped, it would breach on **every consumer purchase ever made**. Now scoped
by `principal_type`, with the note that for a consumer the equivalent assurance
is the consent ceremony, not the chain.

**`OPF-01` could not read "must hold a licence".** Kestrel is not licensed and
should not be — it is a technology operator whose authority comes from the
institution sponsoring it. The rule now reads *licence **or** live sponsorship*;
the original would have failed every non-bank operator by construction, which is
most of the market this regime exists to cover.

**`LOG-STR-01`'s threshold was inert.** Set at $3,000 against an agent whose
largest transaction is $867, no split can "stay under" it. A dial set beyond an
agent's operating range is not a lenient rule, it is a rule **silently switched
off** — and the eval reads its zero findings as clean behaviour. Now resolved per
agent classification, with the $3,000 default preserved for the B2B case that
needs it.

**`CTL-DIS-04` and `CTL-EFF-04` describe one shape.** The specification maps F73
to EFF-04, but F73 is *"it fired, it **held**, and the breach happened anyway"* —
held means not overridden, which is DIS-04's case. They now partition on whether
an override was recorded, so they never double-report one transaction. The split
is the supervisorily meaningful one: **an ignored control is a systems failure,
an overridden one is a conduct question with a name attached.**

---

# Part 6 — Feasibility: where a bank actually gets each field

The rule the schema follows: *only ask for data that already exists in a system the firm runs, or is
a small deliberate build.* Every field below meets it.

| Field | Source | Effort |
|---|---|---|
| `transaction_history` | the institution's own ledger | none |
| `intent_mandate`, `cart`, `payment` | flow to the institution at authorisation under AP2 | none |
| `payment.payee` | **acquirer settlement data** — already held, simply not surfaced to the paying side. Also gives Confirmation-of-Payee | none |
| `consent_ceremony.{occurred,timestamp,principal_id,method}` | **PSD2 Strong Customer Authentication logs** | none |
| `merchant.region`, `sub_merchant` | acquirer data; sub-merchant reporting is **already a card-scheme requirement** | plumbing |
| `construction_context.model.observed_version` | the provider API returns the resolved model id on every call | none |
| `policy_version` | the operator's own deployment pipeline; any team versioning prompts in git can hash them | hours |
| `tool_calls` | **agent observability that already exists** — LangSmith, Langfuse, OpenTelemetry. MCP clients log sessions natively | days |
| `tool_schema_hash` | hash the tool definition at call time | hours |
| `result_excerpt` | the same trace as `tool_calls`, capped at ~2,000 chars | hours |
| `selection_context` | the product-search response, truncated to the pick plus 5 alternatives | days |
| `consent_ceremony.rendered_values` | **the consent UI itself** — serialise what was displayed. Precedent: EMV 3DS challenge records | ~20 lines at the confirm handler |
| `controls.*_declared` | rules-engine configuration | mapping |
| `controls_evaluated` | the fraud/transaction-monitoring engine's own decision log | mapping |
| `override` | four-eyes and case-management systems — overrides are already logged, that is what an override *is* | mapping |
| `agent_card` | the operator publishes it (A2A/AP2) | hours |
| `change_log` | deployment pipeline + credential issuance + control config history | days |
| `granted_capabilities` per delegation level | the issuer, at issuance — it is what the signature should already cover | hours |
| `usage` | the mandate itself; AP2 models single-use vs recurring | none |

**Deliberately not required**, because the industry has not built them: provider-signed model
attestation, screenshots, full catalog archives, agent-to-agent transcripts. F28 and F34 are parked
as a result, and the agent-to-agent injection channel with them.

---

# Part 7 — The plan  *(complete)*

| Stage | Gate | Result |
|---|---|---|
| 1 · Fix the wrong corpus | verifier PASS | ✅ human terminus, staggered credentials, realism bands |
| 2 · Five registry fields | KYA 18 → 23, suite green | ✅ **23**, and the five returned *absent* on legacy cases rather than firing |
| 3 · Write `ctl.json` | planted F71/F72/F73 caught by rules | ✅ 15 rules active; `CTL-EFF-01` caught **all three** planted F71s |
| 4 · Promote evidence-ready rules | KYA 23 → 31 | ✅ **37** — six more were evidence-ready than the plan assumed |
| 5 · Second dossier | a `PortfolioFinding` spanning both | ✅ **F57, F67 and F69 all fire** |
| 6 · Reporting-threshold dial | a tunable dial in the ruleset | ✅ scoped per agent classification |

## 7.1 · Where it landed

| | Before | After |
|---|---|---|
| KYA rules active | 18 / 42 | **37 / 42** |
| Rulesets implemented | 4 | **5** |
| Agents fully fed | 8 of 11 | **11 of 11** |
| Dossiers | 1 | 2 (70 runs, 154 transactions) |
| Tests | 262 | **291** |

The five rules still draft are the genuinely blocked ones: `IDN-04`/`IDN-05`
need cross-case ledger history, and `REG-03`/`CAP-03`/`CAP-04` are judgements the
sandbox has to tune rather than computations anyone can write.

## 7.2 · What the portfolio sweep found

Three things, none of which any single submission can see:

- **F57** — Quickvale Direct holds 49% of one operator's spend and 22% of the
  other's, having first appeared 16 days before the window closed. The rule
  demands presence at multiple operators **and** a large share at each **and**
  recency, because presence alone describes every popular retailer. Northsole,
  Voltic, Pagegrove and Lumen are shared too, and are correctly silent.
- **F67** — 2 of 2 agents run the same model. No operator did anything wrong;
  the exposure is emergent, and the finding says so, because a finding that
  implies fault would be acted on against the wrong party.
- **F69** — the same injected payload at both operators. This is what
  `result_digest` is actually for: it cannot reveal that content carries an
  injection, but once one firm's excerpt has been read, the same digest
  elsewhere identifies the same payload without reading it twice. **Correlation,
  not detection** — and it only worked after fixing a builder bug that derived
  the digest from the run id, giving identical content different hashes and
  silently destroying the field's only purpose.

## 7.3 · Next

- **Wire the Dossier into the LangGraph pipeline.** The rulebooks run against it;
  the orchestrator still consumes `CaseBundle`.
- **The Fact migration.** Checkers return `None` where they mean *absent*, which
  is indistinguishable from *satisfied*. `schemas/fact.py` exists for this and
  is the reason the five registry rules stay quiet on legacy cases instead of
  saying "this agent is not registered" — which is itself a finding.
- **SAFR's fourth disposition.** `monitor`, plus a `case_watched` ledger state.
  An authorisation outcome is authorise / refuse / *authorise with conditions*,
  and "with conditions" is `monitor` under another name — the honest disposition
  for F55's concentration and F67's monoculture, neither of which is a refusal.
