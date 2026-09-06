# 02 · What the product does

## 1 · The regulatory act

**Mandate Supervisor decides whether one AI payment agent should be authorised
to operate, on the evidence of what it actually did.**

That sentence contains three deliberate choices, each of which was considered
and settled:

- **One agent.** Not one firm, not one transaction, not one month of activity.
  The unit of regulatory decision is a single agent, because that is the thing
  authority is granted to and the thing that can be withdrawn.
- **Authorisation, not monitoring.** The output is a decision with consequences
  — permission to operate — not an alert in a queue. Transaction monitoring is
  a different product with a different economics; this one produces a verdict a
  supervisor signs.
- **On evidence of what it did.** Not on the policy the firm filed, not on a
  questionnaire, not on an attestation. On the actual runs.

## 2 · The submission: a dossier

An operator that wants to run a payment agent has its sponsoring institution
submit a **dossier** — one directory, not one file, containing:

| Part | What it is |
|---|---|
| `dossier.json` | Everything the runs share: who the operator is, which agent, the agent's identity credential and its delegation chain, the agent card, the controls the firm claims to run, the change log, and an index attesting to each run file |
| `runs/RUN-*.json` | One complete AP2 chain per run — the shopper's request, the Intent Mandate, how the agent constructed the cart (including every tool call), the consent ceremony, the signed cart, the payment, and the firm's own control outcomes |
| `transactions.json` | The wider transaction ledger — deliberately broader than the submitted runs |
| `ground_truth.json` | Labels. **Evaluation only.** The pipeline never opens it |

Document 03 covers each of these in full, including the thing that makes the
whole submission trustworthy: what the operator is *not* allowed to supply.

## 3 · The review

The dossier goes through one pipeline (document 08 has the full architecture):

```
   INTAKE            code only, no model. Verifies every signature and hash
                     chain, checks the run index against the actual files,
                     resolves the regulator's own registries, and computes
                     the shared statistics once.
        │
        ▼
   ORCHESTRATOR      one model call. On a first pass it dispatches every
                     review skill; on a follow-up question it decides which
                     specialists are relevant and narrows their context.
        │
        ├─── Mandate       ├─── Counterparty    ├─── Log
        ├─── KYA           ├─── Consent & Harm  ├─── Drift
        ├─── Provenance    ├─── Injection
        │
        ▼
   CONTROL ASSURANCE  runs after the others, because its question — did a
                      control that should have fired actually fire? — needs
                      to know what went wrong first.
        │
        ▼
   SYNTHESIS          a deterministic critic checks every claim against the
                      facts, a synthesizer links related findings, and the
                      versioned policy produces a score and a disposition.
        │
        ▼
   OFFICER            reads the case, asks follow-up questions (which run the
                      pipeline again, narrowed), then requests a report.
        │
        ▼
   REPORT ⇄ GROUNDING ──▶ HUMAN GATE ──▶ sent
```

Two properties of that diagram are load-bearing:

- **Every specialist has a deterministic floor that needs no model at all.**
  Rules are evaluated in code and produce facts anyone can re-check. The model
  call is the layer of judgement *on top of* the facts, never a substitute for
  them.
- **Agents never talk to each other.** They read and write typed records to a
  shared, append-only ledger. A specialist that wants more evidence uses its
  own tools; a question that needs a different specialist becomes the officer's
  next round. Iteration replaces recursion — which is what keeps the run
  bounded, replayable, and auditable.

## 4 · The output: four dispositions

| Disposition | When |
|---|---|
| **Authorise** | No hard gate tripped, the weighed picture is clean, and the evidence covers enough of the rulebook to mean something |
| **Monitor** | Neither clean nor actionable. Closed to review but under standing watch; the next submission is auto-triaged against this one |
| **Refuse** | A hard gate tripped, or the weighed picture is beyond tolerance |
| **Incomplete submission** | A verdict on the *evidence*, not on the agent — and deliberately not confusable with a refusal |

The fourth is the one most designs are missing. Telling an operator "your
evidence does not support a decision" is a completely different regulatory act
from telling them "your agent is not fit to operate," and collapsing the two
either punishes honesty or lets bad submissions pass as clean. Document 10
explains the decision function in full, including the four **hard gates** that
refuse regardless of score, and why forty clean runs count *as evidence in
favour* rather than as absence of evidence.

## 5 · The two users

**The case officer** — payments/fintech supervision. Opens a submitted dossier,
watches eleven specialists work through it, reads facts and assessments that
cite specific runs, asks follow-up questions in plain language, and signs the
decision. They triage a prioritised, explained case rather than a raw
transaction dump.

**The policy team** — the people who own the rules. They work in the **policy
sandbox**: fork a rulebook, change a threshold, run it against every labelled
submission the regulator holds, and see precisely what changed — what it now
catches, what it now falsely flags, which rules never fire at all, and whether
each dossier still gets the right disposition. Only then, with a named person
and a rationale and the sweep attached as evidence, does the change become
policy. Document 12.

Both users appear in the same console (document 15).

## 6 · The journey, end to end

1. **The institution submits.** A zip arrives at the intake endpoint. It is
   **verified at the door**: every signature verifies, every index digest
   matches its file, no run is missing, none unlisted. A submission that
   contradicts itself is rejected with the reason — accepting one would destroy
   the point of the index being an attestation.
2. **Intake establishes the facts nobody should have to trust.** Cryptography,
   chain integrity, registry resolution, shared statistics. No rules are
   evaluated here; rules belong to agents.
3. **The review runs.** Eleven specialists, each producing facts (mechanical)
   and assessments (judged), each citing the specific runs it is talking about.
4. **Control Assurance asks the supervisory question.** Not "was this payment
   wrong" but "you declared a control that should have stopped this — did it
   fire, was it bypassed, or was it never there?" This is what makes the tool a
   supervision tool rather than a detection tool.
5. **The policy computes a recommendation.** Hard gates, weighed risk per run,
   evidence adequacy, rule coverage, clean-run count — all versioned, all
   printable, no model involved.
6. **The officer interrogates it.** Questions run the pipeline again with a
   narrowed scope; later assessments supersede earlier ones and both stay on
   the record, so the case can be seen changing its mind and why.
7. **A report is drafted, grounded, and gated.** The drafting agent sees only
   structured findings — never the firm's free text. A grounding check confirms
   every claim cites a finding that actually exists. Then a named human
   approves, edits, or blocks. **Nothing sends itself.**
8. **Everything above is on the ledger**, hash-chained and append-only, with a
   verifier that can be run at any time.

## 7 · What makes it different from the obvious alternatives

| Alternative | Why it is not this |
|---|---|
| A rules engine over transactions | Cannot see the decision process, only its output — misses the entire P2 attack surface where the real attacks live |
| An LLM reading the submission | No reproducible facts, no citable evidence, and the firm's own text becomes the injection surface |
| A compliance questionnaire | Asks the firm to describe itself; this reads what the agent did |
| A fraud model | Produces a score, not an explanation, and cannot answer "which of your controls failed" |
| Transaction monitoring | Answers "is this payment risky." The regulator's question is "should this agent be allowed to operate" — which requires counting what went *right* too |

## 8 · Scope and honesty

- **Synthetic data only. No live rail access.** By design and by declaration.
- **Policy thresholds are prototype parameters**, marked
  `prototype_uncalibrated` in the policy file itself, and never presented as
  calibrated supervisory limits.
- **The system recommends; a human decides.** The word used throughout the code
  is *recommendation*, and the disposition is not a decision until a named
  person records one.
