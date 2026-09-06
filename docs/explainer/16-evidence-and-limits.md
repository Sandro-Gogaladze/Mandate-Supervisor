# 16 · Evidence, and honest limits

A supervisory tool asks other people to justify their systems. It should hold
itself to the same standard. This document is what we can actually show, and
what we cannot.

## 1 · What is built

- The dossier schema and loader; **both dossiers** signed and independently
  verified
- **Six regulator registries** and the keystore
- **Nine rulebooks, 103 rules** (97 active), rules-as-data end to end
- **Ten specialists**, each with a deterministic floor and at most one
  contained model call
- The **orchestrator**, skills registry, investigator, deterministic critic,
  synthesizer, drafting agent and deterministic grounding validator
- **Systemic's cross-firm findings**, firing on the corpus inside the first pass
- The **hash-chained ledger**, its projection, its verifier and its export
- **Versioned authorisation policy**: hard gates, weighed judgement, adequacy,
  four dispositions, full derivation
- **Intake** with signature, chain and index verification, and zip upload
  rejected at the door on any contradiction
- The **policy sandbox**: draft store, parameterised sweeps, comparison,
  promotion gate, and its API
- The **console**: overview, case queue, case review with per-type renderers,
  execution runs, portfolio, supervision map, authorisation panel, sandbox page
- The **evaluation harness**, with label isolation
- The **independent verifier**, forbidden from importing any of the above

**446 automated tests pass.**

## 2 · The independent verifier

`scripts/verify_dossier.py` is written from the failure catalogue, not from the
checkers, and **must not import from `agents/`**. The reason is specific: in an
earlier corpus, ground truth was hand-written and then revised four times to
match what the implementation produced — so every evaluation number measured
agreement with a target the implementation had helped write. That property dies
the moment the verifier shares code with the thing it verifies.

Run today, on both dossiers:

```
DOSSIER-KST-2026-001 · 50 runs · 102 transactions · 21 planted · 37 clean
  signatures verified 149, hash chain intact
  ground truth reproduced independently: 19/19 computable  (+2 judged)
  PASS

DOSSIER-HAL-2026-001 · 20 runs · 52 transactions · 5 planted · 17 clean
  signatures verified 62, hash chain intact
  ground truth reproduced independently: 4/4 computable  (+1 judged)
  PASS
```

**211 signatures verify. Every computable planted defect is reproduced by an
independent implementation.** The judged ones are reported separately rather
than being quietly counted — see §5.

The verifier also reports realism, and it is honest about its own statistics:
on Halcyon it notes that at n=52 the standard error on the leading-digit share
is around 6.4 percentage points, *"so this is only meaningful as a smell test."*

## 3 · The evaluation harness

`python -m eval` runs the **production graph** over every labelled dossier in a
throwaway ledger, opens the labels only after the graph returns, and computes
precision and recall overall, per agent, per rule and per failure — plus a
false-positive rate on labelled-clean runs and explicit `missed` and
`unexpected` lists.

### Current result, mechanical mode (no model calls)

```
  overall              tp 17 · fp 5 · fn 3     precision 0.77   recall 0.85
  adverse assessments  tp 17 · fp 4 · fn 3     precision 0.81   recall 0.85
  clean runs           54, of which 1 false positive       FP rate 1.9%
                       0 false positives among adverse assessments
```

Per agent, in mechanical mode:

| Agent | tp | fp | fn | Precision | Recall |
|---|---|---|---|---|---|
| Mandate | 4 | 3 | 0 | 0.57 | 1.00 |
| KYA | 1 | 0 | 1 | 1.00 | 0.50 |
| Provenance | 4 | 0 | 0 | 1.00 | 1.00 |
| Injection | 0 | 0 | 3 | — | **0.00** |
| Counterparty | 1 | 2 | 0 | 0.33 | 1.00 |
| Consent & Harm | 2 | 0 | 0 | 1.00 | 1.00 |
| Control Assurance | 5 | 0 | 0 | 1.00 | 1.00 |
| Log / Drift | 0 | 0 | 0 | — | — |

### How to read that table honestly

- **Injection's 0.00 recall is expected in this mode, not a defect.** All three
  misses are F32, and *acting* on an injection is a **judged** rule — the model
  never runs in mechanical mode, so the rule returns inconclusive by design.
  Mechanical mode measures the deterministic floor; it is not the system's
  detection rate.
- **Log and Drift have no numbers at all** for the same reason: all four of
  their rules are judged. A mechanical sweep tells you almost everything about
  Identity & Authority and Control Assurance and nothing about Transaction
  Patterns and Behavioural Drift.
- **The "false positives" are mostly not errors.** They are detections with no
  corresponding label — for example a cumulative-cap finding on the same run
  where a per-transaction cap breach was labelled. The harness cannot tell a
  false positive from a missing label, and it says so rather than choosing.
- **Per-rule metrics are diagnostic, not validation.** The labels say "this run
  had F42", not "rule `MND-CAP-01` should fire here." Per-rule numbers inherit
  the labels of the failures a rule declares.

That paragraph of caveats is printed by the harness itself as a `coverage_note`,
so the numbers cannot travel without it.

## 4 · Known weaknesses — stated, not discovered later

**The corpus exercises 17 of 87 failures (20%).** 97 active rules, 26 planted
defect instances. Most rules have never fired on anything: they are
*asserted*-correct, not *demonstrated*-correct. Expanding the corpus is the
single highest-value follow-on task, and it needs no new architecture.

**The evaluation set is two dossiers.** Any rate on screen rests on a handful of
examples. Every rate is shown with its n, and anything under about five is
labelled insufficient evidence rather than given a number that invites trust.

**Thresholds are uncalibrated.** The policy file declares itself
`prototype_uncalibrated` and that status travels with every recommendation.

**Two rules duplicate each other on single-task mandates by construction** —
where a cumulative cap equals a per-transaction cap, two rules produce two facts
about one event. The synthesizer's same-event handling and the decision
function's de-duplication both exist to contain that, and it is still a known
sharp edge.

**Two failures are judged, not computable.** No deterministic check can
reproduce "the cart is not what the shopper meant" or "the agent is quietly
choosing worse options." The verifier reports them separately rather than
pretending, and their absence from a mechanical result is a property of the
mode, not a detection failure.

## 5 · What we deliberately do not claim

- Not real-world precision or recall. The data is synthetic and ours.
- Not calibration. The thresholds are prototype policy parameters.
- Not that a passing content index proves no unfiled executions exist.
- Not that no regex hit means no injection. Triage narrows; it does not clear.
- Not that a fact proves an operator's self-attestation is true. A fact is a
  mechanical result **about submitted evidence**.

## 6 · Why the honesty is load-bearing

The audience is supervisors. A system that reports 100% recall on its own
synthetic corpus and does not say why that number is weak will be dismissed by
exactly the people it is built for. A system that surfaces `absent`, keeps
`inconclusive` as a verdict, prints its own coverage caveat, and marks its
policy uncalibrated is making a different claim — **that it is built to be
argued with** — and that is the claim a regulator can actually act on.
