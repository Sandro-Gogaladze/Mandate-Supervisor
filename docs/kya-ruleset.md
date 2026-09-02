# The KYA ruleset — a rulebook designed from scratch

Ignores what is currently in `registry/rulesets/kya.json`. This is what the rules should be if you
were writing them as a regulator, with SAFR's recommendations folded in and every policy dial called
out so the sandbox has something to actually tune.

Companion to `docs/kya-and-the-sandbox.md` (why KYA needs rules at all) and `docs/coverage-model.md`
(the failure ids `F#` referenced throughout).

---

## Part 0 — Why not just use SAFR's four disposition names?

You asked why we'd invent `monitor` instead of taking SAFR's four labels directly. **You should take
the structure, and you can't take the labels — and the reason is worth putting in the pitch.**

SAFR's disposition engine returns one of four outcomes: **execute · reject · escalate to human ·
allow-with-monitoring.** Those are **pre-execution verbs.** SAFR sits between the agent and the
execution environment and decides whether an action *may happen*.

We sit outside the firm and review what *already happened*. Three of the four don't translate:

| SAFR outcome | Why it doesn't transfer | What it becomes here |
|---|---|---|
| **Execute** | Nothing to permit — it already settled | **Close, no action** |
| **Reject** | You cannot un-settle a payment | **Escalate** — supervisory action against the firm |
| **Escalate to human** | **This is our entire workflow, not a disposition.** Every case reaches a named human at the gate by design. SAFR can make it a disposition because most of its decisions are automated and only some escalate; for us it's the process, so it can't also be an outcome | *(dissolves into the workflow)* |
| **Allow with monitoring** | Transfers cleanly | **Monitor** |

**So the real answer is that you already have two different four-slot things and are conflating them.**

- **Risk tier** — computed deterministically from finding weights. Triage priority. Tells the officer
  what to open first. Currently `clear / review / escalate`.
- **Disposition** — the officer's recorded decision at the gate. The outcome. Currently
  `approve & issue / reject / rerun / close-no-action`.

SAFR's four belong on the **disposition** axis, not the tier axis. Adopting them there gives:

```
DISPOSITION  (the named human's decision, recorded in the ledger)
  close_no_action   — nothing warranting supervisory attention        [SAFR: execute]
  monitor           — no action now; the agent goes on a watchlist    [SAFR: allow-with-monitoring]
                      and its next submission is triaged against this one
  query             — a supervisory query issues to the firm
  escalate          — enforcement referral or restriction             [SAFR: reject]
```

`monitor` is the one genuinely missing today, and it is the one that makes the SAFR alignment claim
literally true. It is also the disposition that most needs to exist: a drift finding, a
`possible`-confidence detection and a portfolio-level concentration are all currently forced into
either "clear" (wrong — you did find something) or "review" (wrong — there's nothing to ask the firm
yet).

**What to say:** *"SAFR's disposition engine has four outcomes. Three of them are pre-execution verbs
that don't survive translation to post-hoc supervision — you can't reject a settled payment, and
'escalate to a human' is our entire workflow rather than an outcome. We take the fourth,
allow-with-monitoring, because it's the one supervisory state we were missing."* That reads as
having thought about it. Copying four labels that don't fit reads as not having.

**And a bonus once `monitor` exists:** it gives the Systemic agent (E2) its consumer. Cases in
`monitor` are exactly the population a portfolio sweep should run over.

---

## Part 1 — Design principles

Five rules about the rules, applied throughout:

1. **Every rule is checkable against data a firm can actually submit.** Nothing here depends on
   screenshots, provider-signed model attestation, or A2A transcripts (see `coverage-model.md` Part 3).
2. **Every rule states which failure it prevents** (`F#`), so the rulebook and the threat model can't
   drift apart.
3. **Deterministic by default.** A rule is only model-judged where the question is genuinely
   semantic. 55 of the 57 below are pure computation.
4. **Every threshold is a named parameter, not a literal.** That is what makes the sandbox meaningful
   — §5 lists all eleven dials in one place.
5. **Severity is a policy choice, not a technical one.** Weights are proposed, not derived. They are
   the most important thing to tune and the most likely to be wrong on first pass.

**Two rulesets, not one.** KYA is about *the agent*. SAFR's controls repository, disposition engine and
audit log are about *the firm's runtime governance* — a different subject with a different owner, so
they get their own ruleset (`CTL-*`) rather than being bolted onto KYA. Both ship together.

---

## Part 2 — The KYA ruleset (`KYA-*`), 42 rules

### A · `IDN` — Identity is cryptographically sound

*Does this credential actually belong to who it claims?*

| Rule | Asserts | Prevents | Type | Weight |
|---|---|---|---|---|
| `KYA-IDN-01` | The credential's signature verifies against the issuer's public key | forged credentials | det | 1.00 |
| `KYA-IDN-02` | The signature algorithm is on the allowlist | downgrade to a weak algorithm | det | 0.80 |
| `KYA-IDN-03` | The signed payload hash recomputes over the canonical content | post-signature tampering | det | 0.80 |
| `KYA-IDN-04` | The signer key is not used by any other agent identity | F22 — one actor, two names, double limits | det | 0.70 |
| `KYA-IDN-05` | The credential id is unique across the register | F23 — attribution collision | det | 0.55 |

### B · `ISS` — The issuer is accredited and current

*Did someone with authority vouch for this agent, and were they entitled to at the time?*

| Rule | Asserts | Prevents | Type | Weight |
|---|---|---|---|---|
| `KYA-ISS-01` | The issuer is present in the trust registry | F1 — an attacker as their own passport office | det | 1.00 |
| `KYA-ISS-02` | The issuer was not revoked **as at the credential's issue date** | F2 — point-in-time, not current status | det | 1.00 |
| `KYA-ISS-03` | The issuer's trust tier meets the minimum for this agent's risk class | F3 — a low-tier issuer backing a high-value mandate | det | 0.45 |
| `KYA-ISS-04` | The issuer's accreditation has been reviewed within the maximum age | F4 — a trust list of who *used to be* trustworthy | det | 0.25 |
| `KYA-ISS-05` | The issuer is authorised to issue for this agent classification | issuers operating outside their accredited scope | det | 0.40 |

### C · `ACC` — Authority traces to an accountable human

*If this agent causes a loss, who answers for it?* **The most important family in the rulebook.**

| Rule | Asserts | Prevents | Type | Weight |
|---|---|---|---|---|
| `KYA-ACC-01` | The delegation chain terminates in a natural person or a legally liable entity | **F6 — an autonomous payer with nobody accountable** | det | 1.00 |
| `KYA-ACC-02` | The chain terminus is the same principal that signed the Intent | F7 — authority and authorisation held by different people | det | 0.70 |
| `KYA-ACC-03` | Every delegation entry's signature verifies | F8 — a forged link mid-chain | det | 0.85 |
| `KYA-ACC-04` | No holder appears twice in the chain | F9 — manufactured oversight depth | det | 0.50 |
| `KYA-ACC-05` | Chain depth is within the maximum | F10 — accountability diluted past usefulness | det | 0.30 |
| `KYA-ACC-06` | No link grants authority exceeding what the granting holder itself holds | **F11 — privilege manufactured inside the chain** | det | 0.85 |
| `KYA-ACC-07` | The terminus is on the operator firm's authorised-signatory list | someone with no mandate to bind the firm binding it | det | 0.55 |

### D · `OPF` — The operator firm is fit to run it

*Is there a supervised entity behind this, and is it in a fit state?*

| Rule | Asserts | Prevents | Type | Weight |
|---|---|---|---|---|
| `KYA-OPF-01` | The operator firm holds a current licence or registration | F12 — an unregulated firm moving money | det | 0.90 |
| `KYA-OPF-02` | The firm's standing is not in a barring state | F13 — a firm in wind-down deploying new agents | det | 0.75 |
| `KYA-OPF-03` | No unnotified change of control since the credential was issued | F14 — a credential as a transferable asset | det | 0.60 |
| `KYA-OPF-04` | A named compliance contact is on record and current | F15 — findings with nobody to serve them on | det | 0.20 |

### E · `REG` — The agent is declared and classified

*Do we know this agent exists, and does its declared nature match what it does?*

| Rule | Asserts | Prevents | Type | Weight |
|---|---|---|---|---|
| `KYA-REG-01` | The agent was registered before its first transaction | F16 — an undeclared payer | det | 0.65 |
| `KYA-REG-02` | A risk classification is declared | F17 — no basis for proportionate rules | det | 0.25 |
| `KYA-REG-03` | Observed activity is consistent with the declared classification | **under-declaration** — registering as low-risk and transacting at treasury scale | **judged** | 0.70 |
| `KYA-REG-04` | The registration is current | stale registrations describing agents that have changed | det | 0.30 |
| `KYA-REG-05` | The registered purpose matches the mandate's `purpose_category` | an agent operating outside what it registered to do | det | 0.55 |

> `KYA-REG-03` is one of only two judged rules here, and it is the one that turns registration from
> paperwork into supervision: a firm can declare anything, and this asks whether the declaration
> survives contact with the transaction history.

### F · `TEC` — The technical substrate is declared and controlled

*What actually made the decisions, and was it the thing that was approved?* **Directly SAFR-adjacent —
SAFR's agent-identity component covers the operator binding; this covers the substrate.**

| Rule | Asserts | Prevents | Type | Weight |
|---|---|---|---|---|
| `KYA-TEC-01` | A model version is declared on the mandate | F18 — behaviour that can't be attributed | det | 0.45 |
| `KYA-TEC-02` | The observed model version matches the declared one | **F37 — model substitution** | det | 0.85 |
| `KYA-TEC-03` | The model version is not on the blocklist | F19 — a known-vulnerable model still authorising payments | det | 0.90 |
| `KYA-TEC-04` | Validation evidence is on file for this model version, where required by risk class | deploying an unvalidated model at scale | det | 0.50 |
| `KYA-TEC-05` | The prompt/policy version is bound to a released artifact | F36 — runtime-invented, unreviewable policy | det | 0.55 |
| `KYA-TEC-06` | Every tool server used is on the agent's declared tool list | F33 — a tool nobody authorised | det | 0.70 |

### G · `CAP` — Capability proportionality

*Does this agent hold the right amount of power — not too little, not too much?*

| Rule | Asserts | Prevents | Type | Weight |
|---|---|---|---|---|
| `KYA-CAP-01` | Capabilities are non-empty | a credential granting nothing, used anyway | det | 0.50 |
| `KYA-CAP-02` | All capabilities are in the allowed vocabulary | invented, unreviewable permissions | det | 0.35 |
| `KYA-CAP-03` | Capabilities are sufficient for the declared purpose | the agent is doing things it wasn't credentialed for | det | 0.55 |
| `KYA-CAP-04` | Capabilities are not materially broader than the purpose requires (**least privilege**) | over-provisioning — the blast radius of a compromise | **judged** | 0.40 |
| `KYA-CAP-05` | No capability creep across reissuance beyond tolerance | **F20 — authority that accumulated rather than was granted** | det | 0.45 |

### H · `LIF` — Credential lifecycle

*Is this credential live, singular, and time-bounded?*

| Rule | Asserts | Prevents | Type | Weight |
|---|---|---|---|---|
| `KYA-LIF-01` | The credential was not expired at time of use | expired authority | det | 0.90 |
| `KYA-LIF-02` | `issued_at` precedes `expires_at` | F5 — impossible dates defeating expiry checks | det | 0.60 |
| `KYA-LIF-03` | The validity window does not exceed the maximum | **long windows make stale mandates technically valid** (F47) | det | 0.30 |
| `KYA-LIF-04` | No two credentials for one agent are valid simultaneously | F21 — double authority, ineffective revocation | det | 0.50 |
| `KYA-LIF-05` | Revocation status was checked against a source no older than the staleness limit | acting on a stale revocation list | det | 0.40 |

**42 rules · 40 deterministic · 2 judged.**

---

## Part 3 — The controls ruleset (`CTL-*`), 15 rules — SAFR's contribution

SAFR's other three components, turned into supervisory checks. **These are about the firm, not the
agent**, which is why they are a separate ruleset with a separate owner (the Control Assurance agent,
E1). A firm running SAFR produces all the evidence these need as a by-product.

### `REP` — Controls repository *(SAFR component 2)*

| Rule | Asserts | Prevents | Type | Weight |
|---|---|---|---|---|
| `CTL-REP-01` | A declared control set exists for this agent | governance by assertion | det | 0.70 |
| `CTL-REP-02` | **Every risk the mandate creates has at least one declared control** | **F70 — a cap authorised with nothing enforcing it** | det | 0.75 |
| `CTL-REP-03` | Controls are versioned and the version in force at transaction time is identifiable | controls that can't be pinned to what actually ran | det | 0.45 |
| `CTL-REP-04` | Each control declares its enforcement mode (blocking or advisory) | a control everyone believed was blocking | det | 0.35 |

> `CTL-REP-02` is the coverage check, and it is the most useful rule in this ruleset. It produces a
> finding **with no breach required** — the firm authorised a risk and built nothing to manage it.
> Findings that predict rather than describe are what supervisors actually want.

### `DIS` — Disposition engine *(SAFR component 3)*

| Rule | Asserts | Prevents | Type | Weight |
|---|---|---|---|---|
| `CTL-DIS-01` | Every agent action was evaluated before execution | actions bypassing the checkpoint entirely | det | 0.85 |
| `CTL-DIS-02` | A disposition is recorded for each evaluated action | an engine that runs and doesn't say what it decided | det | 0.55 |
| `CTL-DIS-03` | Actions dispositioned *human review* carry a recorded human decision | the escalation path existing on paper only | det | 0.80 |
| `CTL-DIS-04` | No action executed after a *reject* disposition | **the control decided no and the payment happened** | det | 1.00 |

### `EFF` — Control effectiveness

| Rule | Asserts | Prevents | Type | Weight |
|---|---|---|---|---|
| `CTL-EFF-01` | A declared control that should have triggered did trigger | **F71 — the control is on paper, not in the system** | det | 0.80 |
| `CTL-EFF-02` | No override without a recorded authority and reason | **F72 — silent bypass** | det | 0.85 |
| `CTL-EFF-03` | The override rate is within the permitted maximum | **normalised deviance** — override as routine | det | 0.65 |
| `CTL-EFF-04` | A triggered *blocking* control has no corresponding settled transaction | **F73 — it fired, held, and the payment went anyway** | det | 0.90 |

> `CTL-EFF-03` is the culture rule. One override is an incident; a 40% override rate is a finding
> about how the firm is run. It is also the single most interesting dial in the whole rulebook.

### `LOG` — Audit log *(SAFR component 4)*

| Rule | Asserts | Prevents | Type | Weight |
|---|---|---|---|---|
| `CTL-LOG-01` | An audit log is present and covers the reporting period | gaps exactly where the interesting activity is | det | 0.60 |
| `CTL-LOG-02` | The log is tamper-evident (hash chain or WORM attestation) | a log that can be edited after the fact | det | 0.55 |
| `CTL-LOG-03` | Log entry count reconciles to settlement records | **silent omission** — the strongest signal in this family | det | 0.75 |

**15 rules · all deterministic.**

---

## Part 3.5 — Which agent checks what

**The assignment principle:** *a rule belongs to the agent whose canonical evidence block already
contains everything the rule needs.* Not the agent it sounds related to. That resolves every boundary
case mechanically instead of by intuition, and it keeps the evidence floor honest — an agent should
never be asked a question its brief can't answer.

| Agent | Rules | Count |
|---|---|---|
| **KYA** (A2) | `IDN` ×5 · `ISS` ×5 · `ACC` ×7 · `OPF` ×4 · `REG` ×5 · `CAP` ×5 · `LIF` ×5 · `TEC-01/03/04` | **39** |
| **Provenance** (B1) | `TEC-02` · `TEC-05` · `TEC-06` | **3** |
| **Control Assurance** (E1) | all `CTL-*` | **15** |

### Why the `TEC` family splits

It reads like one family and it is answered from two different evidence blocks:

| Rule | Needs | Owner |
|---|---|---|
| `TEC-01` is a model version declared? | agent registry | KYA |
| `TEC-03` is it blocklisted? | agent registry | KYA |
| `TEC-04` is validation evidence on file? | agent registry | KYA |
| `TEC-02` does observed match declared? | `construction_context.model` | **Provenance** |
| `TEC-05` is the prompt bound to a release? | `construction_context.policy_version` | **Provenance** |
| `TEC-06` were all tool servers declared? | `construction_context.tool_calls` + `tools.json` | **Provenance** |

Splitting on evidence rather than on topic also removes the duplication flagged in
`coverage-model.md`: F37 (model substitution) was assigned to Provenance there and would have been
re-asserted by KYA here. One rule, one owner, one finding.

### Four notes that change the wiring

**1 · `KYA-REG-03` needs evidence KYA does not currently receive.** "Observed activity consistent with
the declared classification" requires the transaction history, which today only Log and Drift see.
**Fix:** widen KYA's canonical evidence block with a transaction summary — count, total, max single
amount, distinct counterparties. That is precisely what `compose_context()` exists for; the floor is
composable. It is the only rule in the book that requires an evidence-floor change.

**2 · Four rules cannot be answered from a single submission.** `IDN-04` (signer key across
identities), `IDN-05` (credential id uniqueness), `CAP-05` (creep across reissuance) and `LIF-04`
(overlapping credentials) are all *cross-case* questions. They need `get_credential_history`, the
ledger-backed tool already in KYA's roster. Worth stating explicitly, because a reviewer will
reasonably ask how you detect creep from one case: you don't.

**3 · Control Assurance is not a peer in the fan-out.** `CTL-EFF-01` asks whether a control that
*should* have triggered did — which means it consumes the **other agents' findings**. E1 therefore sits
in the tail alongside the critic and synthesizer, not beside the specialists. Its brief is the case's
findings plus the firm's control set, and it cannot start until the specialists finish.

**4 · Two of the 57 rules are model-judged, and both are KYA's.** `REG-03` (declaration vs reality) and
`CAP-04` (least privilege). Everything else is computation. That gives KYA a second contained LLM
judgment alongside its existing open-ended ceiling — worth noting when budgeting calls per case.

### What no agent checks, by design

- **The risk tier** is `pipeline/scoring.py` — a pure function over finding weights. No agent, no
  model, no judgment.
- **The disposition** is the named human at the gate. That is the point of the gate.

---

## Part 4 — Rules deliberately *not* included

Stated so the omissions read as decisions rather than oversights.

| Not included | Why |
|---|---|
| Anything requiring a consent screenshot | No screenshots — storage, personal data, manual interpretation |
| Provider-signed model attestation | No provider offers it. `KYA-TEC-02` uses a self-declaration the firm is accountable for |
| Agent-to-agent identity rules | Reserved. Almost nobody runs A2A commerce; the rules would be untestable |
| Behavioural rules (structuring, drift, velocity) | Different question, different agent. KYA is identity and standing; those belong to Log and Drift |
| A "reputation score" for agents | Reputation is inferred, not verified. It would smuggle an unaccountable judgment into a rulebook whose value is that every rule is checkable |
| Hard caps on agent count per firm | No evidence base for any number, and trivially gamed by incorporating |

---

## Part 5 — The eleven dials

The whole point of the sandbox. Everything below is data in `registry/`, changed without touching
code, versioned, and promoted through the human gate.

| # | Dial | Default | Effect of tightening | What it trades |
|---|---|---|---|---|
| 1 | `max_delegation_depth` | 4 | More chains flagged | Legitimate group structures vs accountability dilution |
| 2 | `issuer_tier_by_risk_class` | primary ≥ high-risk | Fewer issuers usable at high value | Market access vs trust assurance |
| 3 | `max_issuer_reaccreditation_age_days` | 730 | Issuers must re-prove sooner | Supervisory cost vs staleness |
| 4 | `max_credential_validity_days` | 365 | Shorter-lived credentials | Operational churn vs stale-authority window |
| 5 | `capability_vocabulary` | *(list)* | Fewer permissible capabilities | Innovation headroom vs reviewability |
| 6 | `least_privilege_tolerance` | moderate | More over-provisioning flagged | False positives vs blast radius |
| 7 | `capability_creep_tolerance` | 1 new capability/reissue | Creep caught earlier | Renewal friction vs accumulated authority |
| 8 | `blocked_model_versions` | *(list)* | Faster removal of known-bad models | Firm disruption vs known-vulnerability exposure |
| 9 | `model_validation_required_above` | medium risk class | More agents need validation evidence | Compliance cost vs unvalidated deployment |
| 10 | **`max_override_rate`** | 5% | Override culture caught sooner | Operational flexibility vs normalised deviance |
| 11 | **Severity weights (all 57)** | *(above)* | Moves every case's tier | **The dial that actually determines outcomes** |

**Dial 11 is the one that matters and the one most likely to be wrong.** The weights above are a
first-pass policy judgment, not a derivation. Everything else changes which findings appear; the
weights change what happens as a result.

### What to run in the sandbox first

Three experiments that produce a real answer from the corpus you have:

1. **Weight sensitivity.** Sweep `KYA-ACC-01` from 0.5 to 1.0 and watch which cases cross the escalate
   boundary. Answers: *is accountability weighted like the most important rule in the book, or just
   described as one?*
2. **Override-rate calibration.** Vary dial 10 across 1% / 5% / 15% and count findings. With synthetic
   data this shows the mechanism; with real submissions it becomes genuine ATL/BTL calibration.
3. **Least-privilege strictness.** Dial 6 is the clearest false-positive/coverage trade in the book —
   the one where you can *show* a judge a curve rather than assert a position.

**State plainly what these prove.** They prove the mechanism, the governance and that rules are
genuinely data. They do not prove any threshold is correct — that needs real submissions and real base
rates. Saying so is the credibility win.

---

## Part 6 — Migration from what exists

The current `registry/rulesets/kya.json` has 33 rules, 18 active. This proposes 42 KYA + 15 CTL.

| | |
|---|---|
| **Carry over unchanged** | 16 of the 18 active rules map directly onto `IDN`, `ISS`, `ACC`, `CAP`, `LIF` |
| **Promoted from draft** | 11 unblock with `firms.json` + `agents.json` + ledger-derived credential history — that work is already scoped in `coverage-model.md` |
| **Genuinely new** | `ACC-06` (privilege escalation), `ACC-07` (signatory list), `REG-03` (declaration vs reality), `TEC-02/04/05/06`, `CAP-04` (least privilege), `LIF-03/05`, and all 15 `CTL-*` |
| **Moves out of KYA** | `consent_method_allowlist` → the Consent & Harm ruleset, where it belongs |
| **Restructured** | Rule ids gain a family segment (`KYA-ACC-01` not `KYA-DEL-01`) so a rule's subject is readable from its id |
