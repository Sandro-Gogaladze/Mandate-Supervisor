# 13 · The audit ledger

Auditability is one of the four mandatory guardrails, and it is the one most
easily faked with a log file. This document explains what is actually built.

## 1 · What it is

A single SQLite database in which every consequential thing that happens to a
case is appended as a typed **event**, each event hashed together with the hash
of the one before it, forming a chain.

```
  seq 1 ─┐
         └─ hash = H(event 1 + genesis)
  seq 2 ─┐
         └─ hash = H(event 2 + hash of 1)
  seq 3 ─┐
         └─ hash = H(event 3 + hash of 2)
              …
```

Change any event, delete one, or reorder two, and every hash after it stops
matching. The tampering is not prevented — it is made **detectable**, which is
the honest property a hash chain provides.

## 2 · Three layers of "append-only"

1. **The store class exposes no update method and no delete method at all.**
   This is the primary control: there is no API through which the application
   could modify history, because none was written.
2. **SQL triggers** abort any update or delete that reaches the database by
   another route — defence in depth for anything bypassing the class.
3. **The hash chain** makes any modification that somehow succeeded visible
   afterwards.

The chain is **global across all cases** — events link by sequence number, not
per case — so a deleted or reordered event anywhere breaks verification
everywhere. That is the stronger property for an audit record: you cannot
quietly excise one case's history and leave the rest verifying.

## 3 · Every event has a typed actor

`actor` is mandatory and typed by prefix — `system:` , `agent:` , `human:`. A
finding recorded by `agent:drift` and a decision recorded by
`human:Ana Dvaladze` must be distinguishable a year later **without parsing the
payload**, and they are.

`run_id` groups the events of one bounded run — a triage, an investigation, a
drafting pass — so two runs of the same case can be compared
directly. Case-level events (submitted, opened, closed) carry none.

## 4 · The event vocabulary

Events are the **only** representation of a case. Status and every projection
derive from them, never the other way around.

| Group | Events |
|---|---|
| Submission | `dossier_submitted` · `case_submitted` · `case_opened` · `case_closed` |
| Evidence | `fact_recorded` · `assessment_recorded` · `finding_recorded` · `observation_recorded` · `failure_occurrence_recorded` · `control_posture_recorded` |
| Orchestration | `run_started` · `dispatch_planned` · `dispatch_recorded` · `escalation_round_started` · `run_completed` · `specialist_failed` |
| Checks | `critic_checked` · `correlation_recorded` · `grounding_checked` |
| Decision | `score_computed` · `authorisation_computed` · `run_evaluated` · `authorisation_decided` · `decision_recorded` · `case_watched` |
| Officer | `question_asked` · `orchestrator_replied` · `investigation_completed` · `report_drafted` · `report_blocked` · `review_history_cleared` |
| Portfolio | `portfolio_sweep_started` · `portfolio_sweep_completed` · `portfolio_finding_recorded` |
| Policy | `ruleset_promoted` |

**One finding per event, never a batch.** "Every finding citable" requires each
finding to have its own sequence number, its own timestamp, and its own
producing actor.

**`dispatch_recorded` carries the exact composed context an agent received.**
That is what makes a review reproducible and what lets the deterministic critic
check an agent's quoted numbers against something real.

## 5 · Status is computed, never stored

A case's status is derived from its event history by a pure function. There is
no status column.

The reason is simple: a stored status can disagree with the events. A derived
one cannot. The same principle governs the risk score, which is recomputed from
current findings rather than read back from a saved number.

The projection also de-duplicates using **the same definition of "the same
finding"** as the pipeline's state reducers — one definition shared across both,
so a re-triage that re-derives an identical finding does not double it in the
record.

## 6 · "Clear history" in a tamper-evident world

An officer sometimes needs to set aside a review and start again from the
submission alone. In an append-only ledger you cannot delete, so the system does
the only honest thing:

`review_history_cleared` is itself an event, carrying the reason and the
sequence number cleared through. Nothing is deleted; the chain is untouched;
every earlier event is still readable and still verifying. The projection simply
stops carrying work recorded before the marker — and **who reset it and when is
itself on the record.**

## 7 · Verification is a first-class action

```bash
python -m ledger.verify
```

Walks the entire chain and either prints *"chain intact — N events verified"* or
exits non-zero listing every broken link. The same check is exposed over the API
at `GET /ledger/verify`, because "prove the record has not been tampered with"
is a thing a supervisor demonstrates, not just a maintenance task.

The ledger can also be exported per case as JSONL for handing to an external
party.

## 8 · One hash definition across the system

The chain hashes reuse the **same canonical serialisation** that signs the
mandate corpus. One definition of "the bytes of this object" across signing and
chaining means there is no second implementation that could drift from the
first — and it means a signature check and a chain check are talking about the
same bytes.

## 9 · Concurrency, because a fan-out is the normal case

Eight specialists finishing simultaneously in a fan-out is the real concurrent
case, and it must not fork the chain. Appends serialise through a per-database
process lock plus an immediate transaction, with the current maximum sequence
re-read **inside** the transaction. Combined with deterministic ids on facts and
assessments, a retried node cannot double-count and a parallel node cannot
create a branch.

## 10 · What the ledger is not

It is **not** the LangGraph checkpointer, which lives in a separate database.
The checkpointer is disposable resume plumbing: delete it and you lose in-flight
resumability of a paused run, nothing more. Delete the ledger and you lose the
audit trail. Only one of those is allowed to matter, and keeping them in
different databases is how that stays true rather than becoming a convention
someone forgets.
