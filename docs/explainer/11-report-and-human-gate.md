# 11 · The report and the human gate

Nothing this system produces reaches a supervised firm without a named human
approving it. This document explains the last stretch of the pipeline: how the
report is written, how it is verified, and how it is signed off.

## 1 · The drafting agent has the most restricted input in the system

It is the only agent whose entire output is free prose — which is precisely why
its **input** is the narrowest anywhere in the pipeline.

It receives **the structured record only**: typed findings, observations, the
dispatch plan, the escalation round, the score. It never receives the raw
submission. No firm-authored text — not the natural-language intent, not
line-item descriptions, not a prompt playback, not a tool result — can reach it.

**There is nothing here for an injected instruction to ride in on.** The firm's
name and the case id are the only submission-derived strings it sees, and they
are included as identifiers.

That is the concept note's promise about the drafting agent, kept literally.

## 2 · A report is structure, not prose

The output is a typed object: sections, each with a title, a body, and
`cited_finding_ids`.

That structure is what makes grounding **checkable by a deterministic
validator** rather than by a second model judging the first. A model checking a
model can hallucinate alongside it; a validator matching citation ids against
graph state cannot.

**Observations never appear inside sections.** Mixing an unverified hunch into
cited prose would launder it into looking like a finding. They get exactly one
clearly labelled slot — an open-observations note — and nowhere else.

## 3 · The grounding check

Pure Python, no model. It returns a list of human-readable problems; an empty
list means grounded. The rules it enforces map one-to-one onto the guardrails
that were promised:

| Rule | Guardrail it makes true |
|---|---|
| Every cited finding id must exist | *"Every claim cites a real finding"* — no invented citations |
| When findings exist, every section must carry at least one citation | No free-floating prose |
| Every finding must be cited by some section | **A report that silently drops an inconvenient finding is as ungrounded as one that invents evidence** |
| Observations may appear only in their labelled slot | Hunches cannot masquerade as findings |
| That slot is **required** when observations exist | A report that hides open questions misleads the officer |
| That slot is **forbidden** when none exist | A note summarising nothing is fabrication |

The third row is the one people do not expect, and it is the one that matters
most for supervisory integrity: grounding is not only about not inventing, it is
about not omitting.

### The retry loop

If grounding fails, the validator's **exact complaints are appended verbatim to
the drafting prompt** and the report is regenerated — capped at two retries in
the graph, in code. The model fixes the actual problems rather than re-rolling
blind. If it still fails, the report is **blocked**, and the block itself is
recorded as an event.

## 4 · The human gate

The graph pauses at the gate. This is the one `interrupt()` left in the system,
and it guards the **artifact**, not the case: a report cannot issue without a
named decision.

The officer has four options:

| Decision | Effect |
|---|---|
| **Approve** | The report is issued, with the deciding person's name on the record |
| **Edit** | The officer's own text is recorded alongside the draft; the change is visible, not silent |
| **Block** | The report does not issue, and the reason is recorded |
| **Re-run** | A directive: the officer names which specialists to re-examine, what to look at, and optionally which runs |

Three properties of the gate:

- **The decision is validated server-side.** A malformed payload re-interrupts
  with an error rather than being accepted; the client cannot talk the gate into
  a bad state.
- **The decision is a named human.** Actors on the ledger are typed by prefix,
  so a finding recorded by `agent:drift` and a decision recorded by
  `human:Ana Dvaladze` are distinguishable a year later without parsing a
  payload.
- **A re-run request records the directive and ends the run.** It does not
  silently loop; the caller then starts a new, recorded, directed review.

## 5 · Two different loops, and why the distinction is deliberate

| | Machine escalation | Human directive |
|---|---|---|
| Triggered by | Unresolved or under-evidenced specialist output | The officer |
| Cap | 1 extra round, in code | None — it is a person asking |
| Can produce assessments? | **No** — observations only | Yes, it is a full review round |
| Free-text instruction reaches a prompt? | No | **Yes** |

That last row is a security statement. The officer's instruction is
**regulator-authored** — trusted-principal input — so it may legitimately reach
a specialist's prompt as free text. **The same is never true of anything the
firm submitted.** The trust boundary is drawn around who wrote the words, not
around where they end up.

## 6 · The second human gate

The report is one of two places a named human must act. The other is **rulebook
promotion**: a draft rulebook becomes policy only through a named person, with a
written rationale, and with the sweep that justified it attached as evidence
(document 12).

Two gates, both on the ledger, both requiring a name:

```
   draft report ──▶ HUMAN ──▶ issued to the firm
   draft rulebook ──▶ HUMAN ──▶ in force as policy
```

Neither is a checkbox on a form. Both are ledger events with an actor, a
timestamp, a rationale and the evidence they rested on.
