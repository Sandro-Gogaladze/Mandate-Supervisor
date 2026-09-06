# 17 · Pitch notes

Everything else in this directory explains the system. This one is about
telling it.

## 1 · The spine of the argument

Six beats. Each one sets up the next, and each is defensible on its own.

1. **Card payments were built around a human clicking pay.** Every control
   assumes a person at the end of a decision.
2. **Agentic commerce removes the person and keeps the money.** An agent decides
   when, how much, and with whom — on its own.
3. **The signature is the part least likely to be wrong.** Published research
   shows a fully valid, correctly signed AP2 mandate carrying a transaction the
   user never authorised, achieved by manipulating the agent *before* anything
   was signed. Cryptography covers the signing; the attacks live upstream of it.
4. **So supervision has to read the decision, not the artifact.** Which means
   the evidence has to include how the cart was built — the tool calls, the
   alternatives, the model actually used, what the consent screen showed.
5. **Payments already approves things by testing them.** MiFID II RTS 6, EMV,
   PCI. Nobody has said what the test looks like for an AI payment agent.
6. **This is that test, built** — and next to it, a sandbox for writing the
   rules it applies, because nobody knows the right thresholds yet and shipping
   an untested one is how supervision loses credibility.

## 2 · The one-liners

- *"Supervising a click is straightforward. Supervising a decision is not."*
- *"A perfect verifier of a perfect signature over a corrupted decision passes
  everything."*
- *"An AI agent has no legal identity. It cannot be fined, sued, struck off, or
  called to a hearing. If the chain doesn't reach a human, the consumer absorbs
  the loss."*
- *"A dial set beyond an agent's operating range is not a lenient rule. It is a
  rule switched off — and the evaluation reads its silence as clean behaviour."*
- *"A sum of weights only counts what went wrong. It never counts what went
  right, so it cannot tell 49 clean runs from 2."*
- *"'We looked and it's fine' has to be distinguishable from 'we didn't look.'"*
- *"'This payment breached the cap' is true. 'And your own blocking control fired
  and was overridden 52 seconds later by a named analyst on an unverifiable
  verbal approval' is actionable."*

## 3 · The demo path

A single narrative through one dossier. Nine minutes, and every beat is a real
screen.

| # | Beat | Point it makes |
|---|---|---|
| 1 | Submit the Kestrel zip. It is verified at the door — 149 signatures, hash chains, 50 index digests | The evidence is real cryptography, and an attestation that contradicts itself is rejected |
| 2 | Start the review. Eleven specialists light up in parallel on the supervision map | This is a pipeline, not a prompt |
| 3 | Open the Mandate turn: run 0043, cart $708 against the shopper's stated $500 | A mechanical fact, citable, re-checkable |
| 4 | Open Control Assurance on the same run: the control **triggered** and was overridden by `ops-analyst-11`, 52 seconds later, on an unverifiable verbal approval | **The supervision beat.** This is the difference between detection and supervision |
| 5 | Open run 0011: the shopper asked for a vitamin C serum, the agent bought a ceramide night cream. Within budget. Every signature valid | The failure that nothing else in the industry can see |
| 6 | Open run 0034: declared `claude-sonnet-5`, observed `claude-sonnet-4-5`, blocklisted since March, still authorising payments | Regulator-held facts beating operator self-attestation |
| 7 | Show the run list — **37 clean runs** — and the disposition panel with its factor breakdown | Authorisation counts what went right; the number is a derivation, not an opinion |
| 8 | Show S3: the deployment target is v2.5.1 and no submitted run ran on it | Three field comparisons; the cheapest and most important check in the system |
| 9 | Ask a question in plain language. It narrows to one run and re-runs the relevant specialists | The officer stays in the loop analytically, not just at the end |
| 10 | Draft the report. Grounding passes. Sign it with a name | Nothing sends itself |
| 11 | Portfolio: Quickvale Direct, paid by two unrelated firms within days, disproportionate at both | The advantage only a central bank has |
| 12 | Sandbox: change a threshold, sweep, see the flips, promote with a rationale — and see the promotion on the ledger with its sweep id attached | The standard-setting half, and the second human gate |
| 13 | `GET /ledger/verify` → chain intact, N events | Auditability demonstrated, not asserted |

If time is short, the irreducible core is **4, 5, 7, 12**.

## 4 · The hard questions, answered

**"Isn't this just an LLM reading a JSON file?"**
No. Every specialist has a deterministic floor of rules evaluated in code, which
produces reproducible facts. The model reasons over those facts and can only
raise severity, never lower it; every claim it makes must cite a run that
actually exists; a deterministic critic checks the numbers it quoted against the
evidence it was given. With no model at all, the system still produces a complete
rule result.

**"How do you know the model didn't hallucinate the finding?"**
Because a finding is a projection of an assessment attached to facts, ids are
validated in code, and the report is checked by a deterministic grounding
validator — not by a second model. And the grounding check catches omission as
well as invention: a report that silently drops an inconvenient finding fails.

**"What if the firm hides the bad runs?"**
Three answers. The run index is a content attestation, so edits, deletions and
insertions after filing are detectable. Runs submitted versus runs executed is
S2. And the transaction history is wider than the runs, so a payment inside the
window with no filed run is itself a finding. What we do **not** claim is that a
content index proves unfiled executions never existed — nothing could.

**"What if the submission contains a prompt injection aimed at you?"**
Intake is code, so nothing reaches a model unparsed. Firm text reaches a model in
exactly three places, delimited by code with schema-constrained output and every
returned id validated. The drafting agent — the one producing free prose — never
sees firm text at all. Tools cannot return the injection surface. And detection
is doubled, so a manipulated semantic check does not leave injection detection
with a single point of failure.

**"Won't this drown officers in false positives?"**
`inconclusive` is a first-class verdict, confidence multiplies severity,
observations are structurally excluded from scoring, findings that are one event
seen by several detectors are de-duplicated, and a human reviews before anything
reaches a firm. On the labelled-clean runs the current false-positive rate is 1
in 54, with zero among adverse assessments — on a small corpus, which we say
every time we say the number.

**"Why not microservices, like the concept note said?"**
The swap-ability the concept note wanted comes from typed interfaces and
rules-as-data, not from network boundaries. Splitting the process would have
bought deployment independence nobody needs and made a hash-chained ledger need
distributed single-writer serialisation. The interfaces sit exactly where the
service boundaries would go, so the split stays available.

**"You built four specialists and now there are eleven. What happened?"**
Writing the failure catalogue exposed five structural assumptions in the original
design — we supervised the artifact not the decision, the transaction not the
entity, one case at a time, the payer never the payee, and never checked whether
a human was actually present. Each gap is a whole phase of the catalogue. Nothing
was unbuilt; every specialist added is one of those five answers.

**"Are these thresholds right?"**
Almost certainly not yet, and the system says so: the policy file marks itself
uncalibrated, and that status travels with every recommendation. Four rules were
already proven wrong by contact with a realistic corpus — including one that
would have breached every consumer purchase ever made. That is exactly what the
sandbox exists to find, and finding four is the argument for it.

**"How much does a review cost?"**
Roughly eleven model calls — one per specialist over the whole dossier's facts,
not per run. The deterministic floor runs first and reduces 50 run files to a
compact fact table, which is what makes one call viable.

## 5 · What to say about what is not finished

Say it first, briefly, and move on:

> *"The corpus exercises 17 of 87 failures. Most rules are asserted correct, not
> demonstrated correct, and the harness prints that caveat with its own numbers.
> The thresholds are prototype parameters. Expanding the corpus is the next
> piece of work, and it needs no new architecture."*

Volunteering that is not a weakness in a supervisory audience. It is the
credential.

## 6 · What to ask for

Three things, in order of value:

1. **Real candidate rules** from regulators, firms and standards bodies, to grow
   the rulebook past what a hackathon can cover.
2. **A route to real submissions** — an agentic-checkout channel where the run
   record is a condition of processing, so the evidence exists because the
   product demands it.
3. **Formal alignment with SAFR's Controls Repository**, so the control
   vocabulary a firm declares and the one a supervisor tests against are the same
   vocabulary.
