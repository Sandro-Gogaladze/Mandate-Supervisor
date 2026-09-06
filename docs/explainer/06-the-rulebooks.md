# 06 · The rulebooks

## 1 · The name

The thing a regulator edits here is the **Agent Supervision Rulebook** — the
complete, versioned set of rules applied to an agentic-payment submission.
**103 rules across nine domains.**

The industry shorthand for this territory is **KYA (Know Your Agent)**, and it
is kept as a subtitle rather than the name, for two precise reasons. It is
inaccurate at the top level — "know your agent" describes identity and
legitimacy, not whether a cart matched a shopper's sentence or whether a firm's
controls held. And it is already taken *inside* the system: Identity & Authority
is one of the nine domains. Naming the whole thing properly is what lets "KYA"
mean exactly one thing again.

| Term | Means |
|---|---|
| **Agent Supervision Rulebook** | All 103 rules, nine domains — what the sandbox versions |
| **Identity & Authority (KYA)** | One domain, 39 rules |

## 2 · Rules are data, not code

This is a founding constraint, and it is real in the codebase: every rule lives
in versioned JSON under `registry/rulesets/`, and no threshold is hardcoded
anywhere in an agent. Each rule carries:

| Field | What it does |
|---|---|
| `rule_id` | Stable identity, readable by subject — `KYA-ACC-03`, `MND-CAP-01`, `CTL-DIS-04` |
| `type` | The checker family it belongs to |
| `version` + `effective_from` | So a decision can name the rule version it was made under |
| `status` | `active` · `draft` · `retired` |
| `evaluation` | `computable` (decided in code) or judged (decided by a specialist over measurements) |
| `severity_weight` | The deterministic floor of how serious a breach is |
| `finding_type` | The vocabulary term a breach produces |
| `description` | Written for a human reading a decision, not for a developer |
| `params` | The tunable dials — thresholds, allowlists, depths |
| `failures` | Which catalogue failures (`F1`–`F73`) a breach of this rule establishes |

The last one is what makes the system coherent: **an agent's breach is
automatically expressible as a named harm**, and Control Assurance can learn
from its peers' facts alone that a particular risk materialised on a particular
run — without any agent talking to any other agent.

Because rules are data, an agent takes its rulebook **as an argument** rather
than loading it. That single decision, made early on purpose, is what lets the
policy sandbox run the exact production agents against a draft rulebook without
touching one line of agent code.

## 3 · The nine domains

**One rulebook per agent.** This was a deliberate choice so that the sandbox can
tune each domain independently and so that ownership is never ambiguous.

| Domain | File | Rules | Judged | Agent |
|---|---|---|---|---|
| Identity & Authority (KYA) | `kya.json` v2026.9 | 39 (34 active) | 2 | KYA |
| Control Assurance | `ctl.json` v2026.3 | 15 | 0 | Control Assurance |
| Mandate Fidelity | `mandate.json` v2026.6 | 14 (13 active) | 1 | Mandate |
| Consent & Harm | `consent.json` v2026.2 | 10 | 1 | Consent & Harm |
| Counterparty | `counterparty.json` v2026.1 | 10 | 2 | Counterparty |
| Manipulation | `injection.json` v2026.2 | 5 | 2 | Injection |
| Decision Provenance | `provenance.json` v2026.3 | 6 | 1 | Provenance |
| Transaction Patterns | `log.json` v2026.5 | 3 | 3 | Log |
| Behavioural Drift | `drift.json` v2026.3 | 1 | 1 | Drift |
| **Total** | | **103** (97 active) | | |

"Judged" means the rule's *outcome* is decided by a specialist reasoning over
deterministic measurements, rather than by a comparison in code. Log's three
rules are all judged — structuring, concentration and velocity are patterns
where the numbers are mechanical and the verdict is not. Every judged rule has
measurements standing behind it; that is a contract the critic enforces.

## 4 · Identity & Authority — the eight families

The largest rulebook, organised by subject so a rule id is readable:

| Family | Asks | Rules |
|---|---|---|
| `IDN` | Is the identity cryptographically sound? | 5 |
| `ISS` | Is the issuer accredited and current? | 5 |
| `ACC` | Does authority trace to an accountable human? | 7 |
| `OPF` | Is the operator fit to run it? | 4 |
| `REG` | Is the agent declared and classified? | 5 |
| `TEC` | Is the technical substrate declared? | 3 (+3 owned by Provenance) |
| `CAP` | Are its capabilities proportionate? | 5 |
| `LIF` | Is the credential lifecycle sound? | 5 |

## 5 · Ownership is assigned by evidence, not by topic

A rule belongs to the agent whose evidence block already contains what the rule
needs. This sounds like a technicality and is actually the thing that makes
agent boundaries decidable rather than arguable.

The clearest example: the `TEC` family splits across two agents.
`TEC-01/03/04` are answered from the agent registry, so they belong to KYA.
`TEC-02/05/06` are answered from `construction_context` — the record of how the
cart was built — so they belong to Provenance, and they **keep their original
ids** so nothing downstream breaks.

Splitting on evidence rather than topic also removed a real bug before it
existed: a duplication where the same failure (F37, "a different model made the
decisions than the one declared") would have been asserted twice by two agents
and counted twice in the score.

## 6 · What a draft rule means

**A draft rule is not an unfinished rule.** It is one whose *evidence the
submission cannot yet carry*, or one whose threshold is a judgement the sandbox
must tune first. Promoting it is a data question, not a coding task.

The five KYA rules currently in draft say exactly this:

- `IDN-04` / `IDN-05` need **cross-case ledger history** — one key backing two
  agents, or one credential id used by two agents, cannot be seen inside a
  single dossier.
- `REG-03`, `CAP-03`, `CAP-04` are **judgements the sandbox must tune** before
  they should have consequences.

A rule marked draft is evaluated and reported but does not contribute to a
decision, and a fact whose rule is draft records its absence reason as
`rule_draft` rather than pretending nothing was checked.

## 7 · Four rules the corpus proved wrong

These are kept on the record because they are exactly the kind of error that
recurs, and because "we ran it against realistic data and four rules turned out
to be wrong" is a stronger claim than "our rules are correct."

**`ACC-02` — required the delegation chain to terminate in the Intent's
signer.** True for corporate delegation. Structurally false for consumer
shopping, where the shopper signs their own Intent and the chain ends at the
*operator's* officer. Left unscoped it would have breached **every consumer
purchase ever made.** Now scoped by `principal_type`.

**`OPF-01` — "the operator must hold a licence."** Fails every non-bank operator
by construction — which is most of this market, and the exact population the
regime exists to reach. Now: *a licence **or** live sponsorship by a supervised
institution.*

**`LOG-STR-01` — structuring threshold sat at $3,000** against an agent whose
largest single transaction is $867. The lesson generalises: **a dial set beyond
an agent's operating range is not a lenient rule, it is a rule switched off** —
and worse, the evaluation harness reads its silence as clean behaviour. Now
resolved per agent classification.

**`MND-CAP-05` — summed spend across the calendar month.** That is the correct
reading of a standing corporate mandate with a monthly budget. On single-task
consumer mandates the cumulative cap *equals* the per-transaction cap, so a
monthly sum breached **every run in both dossiers**. Now it bounds the settled
spend drawn on one Intent Mandate as of each run — which, as a bonus, is also
the check that catches a single-use mandate being drawn on twice.

Each of these was invisible until the rulebook met a realistic corpus. That is
the argument for the sandbox in one paragraph.

## 8 · How a rule becomes policy

Never by editing a file and shipping it. The path is:

```
  book in force ──fork──▶ draft ──sweep against the whole labelled corpus──▶ scorecard
                            │                                                   │
                            └──── edit, re-sweep, compare ──────────────────────┘
                                              │
                            promote: named human + rationale + the sweep id
                                              │
                                              ▼
                                   new version in force, on the ledger
```

The sweep id is the point. The evidence a promotion rested on is part of the
promotion record, so a future regulator asking *"what did you know when you
tightened this rule?"* gets an answer rather than a commit message. Document 12.
