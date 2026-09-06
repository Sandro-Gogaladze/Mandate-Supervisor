# 09 · What the system says: facts, assessments, findings

A supervisory tool is only as good as the shape of what it outputs. This
document explains the vocabulary, because it is where an earlier version of this
design was genuinely wrong and the correction is one of the strongest parts of
the product.

## 1 · The defect this vocabulary fixes

The first design produced **one verdict per rule per case**, with evidence as
prose and no notion of confidence. A case officer cannot act on:

> `concentration: true`

They need:

> *This counterparty. These seven transactions. This share. This window.*

The detection was often right and the output shape made it unusable. So the
system now produces **instances, not verdicts**, and separates what was
mechanically established from what was judged.

## 2 · Four record types, in order of increasing interpretation

```
   FACT           mechanical. reproducible. no model. no opinion.
     │            "Cart total 708.00 exceeds the per-transaction cap 500.00 by 208.00"
     ▼
   ASSESSMENT     meaning attached to facts. may be from the floor or from a model.
     │            "breach · certain · this reads as the control being overridden, not a mis-set cap"
     ▼
   FINDING        the projection of an assessment that scoring, the ledger and
     │            the report consume. This is the citable unit.
     ▼
   FAILURE        the named catalogue harm (F1–F87) that the finding establishes,
   OCCURRENCE     joined to the rule version, the assessment, the supporting facts,
                  and every affected run.
```

Alongside them sits a fifth, deliberately weaker type:

```
   OBSERVATION    an unverified model hunch. No rule id, no severity, never
                  scored, never citable by the report. Surfaced to a human,
                  clearly labelled as unverified.
```

## 3 · Facts — four kinds, and why `satisfied` and `absent` matter

| Kind | Means |
|---|---|
| `breach` | A computable rule was evaluated and failed |
| `satisfied` | A computable rule was evaluated and passed |
| `measurement` | A deterministic computation standing behind a *judged* rule |
| `absent` | The rule could not be evaluated — **and the reason is required** |

**`satisfied` is not noise.** It is how a clean case becomes *provably* clean
rather than merely silent. It is also what gives the evaluation harness true
negatives, without which a false-positive rate cannot be computed at all.

**`absent` is first-class, and its reason is mandatory**, because the reasons
demand different responses:

| Reason | What it means | Who has to act |
|---|---|---|
| `missing_block` | The firm did not submit the evidence this rule needs | A data-gap finding against the submission |
| `out_of_scope` | The rule does not apply to this shape of mandate | Nobody. Not a signal at all |
| `no_registry_record` | The regulator's own register has no entry | A question for the regulator, not the firm |
| `rule_draft` | The rule is not yet in force | Recorded, no consequence |

Collapsing those into silence — which is what a checker returning nothing does —
makes *"we checked and it was fine"* indistinguishable from *"we could not
look."* For a supervisor those are opposite statements. So a console line like

> *"Consent ran 7 rules: 5 satisfied, 2 absent — no `rendered_values` in this
> submission"*

is a supervisory fact in its own right, and it renders as a fact rather than as
nothing.

**Every judged rule has measurements behind it.** That is a contract, and the
critic checks assessments against them — which is what stops a judged rule from
becoming a model's free-form opinion.

**Scope is on the fact.** A rule about a run (was this cart within this
shopper's cap) produces one fact per run, carrying the run reference; a rule
about the agent or the submission (does the delegation chain end in a human)
produces one fact with none. The run list in the console and per-run
precision/recall in the evaluation both read that field.

## 4 · Assessments — five verdicts, and three of them are new capabilities

| Verdict | Means | Scores? |
|---|---|---|
| `breach` | A supervisory concern | **Yes — the only verdict that scores** |
| `concern` | Worth the officer's attention, below the bar for a breach | No |
| `explained` | A rule tripped and, in context, it is fine | No |
| `clear` | A **judged** rule was evaluated and nothing is wrong | No |
| `inconclusive` | The rule applies, the agent evaluated it, and cannot decide | No |

Three of these exist to fix a specific failure of expression:

- **`explained`** — "we looked and it's fine" must be distinguishable from "we
  didn't look." In the earlier design a passing case was simply silent.
- **`clear`** — the assessment-level twin of a `satisfied` fact, for rules
  decided by a model over measurements. "We judged it and it is fine" is a
  different record from "we did not judge it."
- **`inconclusive`** — previously this had to lie in one direction or the other.
  Now it scores nothing, routes to a human, and is the honest answer when the
  answer is genuinely unavailable.

Each assessment also carries a **confidence** — `certain`, `probable`,
`possible` — which multiplies severity when the decision is computed. A model
that is unsure is allowed to say so and is priced accordingly, instead of
choosing between overclaiming and staying silent.

## 5 · Severity is propose-and-enforce

The severity **floor** comes from the rulebook and is deterministic: same facts,
same floor, always. An agent may **raise** it, never lower it, and must say why.
Both numbers are shown.

This keeps two things simultaneously true that usually trade off:

- *"Explainable, factor-level scoring"* stays literally true — the floor is a
  printable derivation from rules and weights.
- An agent can still say something a rulebook cannot: *"four independent
  detectors converged on one injected line item; as coordinated manipulation
  this is materially worse than the sum of its parts."*

The "never lower" half is a schema validator, so it is a guarantee rather than
an instruction in a prompt.

## 6 · Superseding — how a review changes its mind

Round 1 finds an unapproved counterparty. Round 3, given more context,
establishes that it is the approved supplier's disclosed subsidiary.

**Both stay on the ledger.** The projection marks the earlier assessment
superseded, scoring reads only current assessments, and the audit trail shows
the case changing its mind and why. Nothing is ever edited in place; the ledger
stays append-only. This is the only version of "we revised our view" that a
tamper-evident record can honestly offer.

## 7 · Observations — the pressure valve

Observations exist so that the strict types above do not force every model
insight into either a scored verdict or the bin.

An observation has **no rule id** (nothing here traces to a reproducible check),
**no severity** (there is nothing to weight a hunch by), and it is excluded from
scoring **by the scoring function's signature** rather than by convention — the
strongest available way to keep "never scored" true forever. It is also not
citable by the drafting agent.

If an officer wants an observation turned into something with consequences, a
specialist is dispatched and a rule decides. That is the whole escalation path,
and it is deliberately manual.

## 8 · Findings and failure occurrences

A **finding** is the projection of an assessment — the view that scoring, the
ledger event and the report consume. Its id *is* the assessment id, so a
re-derived assessment is the same finding to both the state reducer and the
ledger; a retried node cannot inflate a count.

A **failure occurrence** is the auditable join between a rule and a harm: it
names the catalogue failure (F1–F87), the rule and the rulebook version, the
assessment, every supporting fact, and every affected run. That is what makes it
possible to say, in a report, *"F32 — the agent acted on instructions hidden in
content it read — established on runs 0025 and 0040 under `injection.json`
v2026.2, rule `INJ-ACT-01`,"* and to have every part of that sentence be
checkable.

## 9 · Evidence is cited, never dumped

In the console, evidence appears as a citation:

> `RUN-2026-0811-0043 · cart_total $708.00 · KST-CTL-001`

which expands to the underlying fact and links to the run. There is a renderer
per payload type — fact cards, assessment cards, absent notices, tool-call rows,
control-posture badges, correlation links — and a deliberately **loud** fallback
that names any unrendered type, so a gap shows up in review rather than
silently. Raw JSON is not a fallback; it is a bug.
