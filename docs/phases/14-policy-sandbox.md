# Phase 14 · The policy sandbox

## Naming

The thing this feature edits is the **Agent Supervision Rulebook** — the
complete, versioned set of rules a regulator applies to an agentic-payment
submission. 102 rules across nine domains.

The industry shorthand for this territory is **KYA (Know Your Agent)**, and
the concept note uses it that way. It is kept as a subtitle rather than the
name for two reasons. It is inaccurate at the top level — "know your agent"
describes identity and legitimacy, not whether a cart matched a shopper's
sentence or whether a firm's controls held. And it is already taken *inside*
the system: `registry/rulesets/kya.json` is one of the nine domains.

So, precisely:

| term | means |
|---|---|
| **Agent Supervision Rulebook** | all 102 rules, nine domains — what the sandbox versions |
| **Identity & Authority (KYA)** | one domain, `kya.json`, 39 rules |

Naming the whole thing properly is what lets "KYA" mean exactly one thing
again. Where the UI says *Agent Supervision Rulebook*, it can carry
"industry term: Know Your Agent" as a subtitle once, and never again.

### The nine domains

| domain | file | rules | judged | tunable params |
|---|---|---|---|---|
| Identity & Authority (KYA) | `kya.json` | 39 | 2 | 9 |
| Control Assurance | `ctl.json` | 15 | 0 | 3 |
| Mandate Fidelity | `mandate.json` | 14 | 1 | 1 |
| Consent & Harm | `consent.json` | 10 | 1 | 1 |
| Counterparty | `counterparty.json` | 10 | 2 | 2 |
| Manipulation | `injection.json` | 5 | 1 | 0 |
| Decision Provenance | `provenance.json` | 5 | 1 | 0 |
| Transaction Patterns | `log.json` | 3 | 3 | 2 |
| Behavioural Drift | `drift.json` | 1 | 1 | 1 |
| **total** | | **102** | **12** | **19** |

One wrinkle to fix: `provenance.json` holds three rules with **`KYA-` ids**
(`KYA-TEC-02/05/06`) that the KYA agent deliberately skips and Provenance
evaluates. Under this naming they are Decision Provenance rules wearing an
Identity id. The sandbox groups by **owning rulebook**, not id prefix, so it
displays them correctly today; renaming them `PRV-TEC-*` is the real fix and
is left as separate work, because it touches fact ids, assessments and the
eval mapping.

## The problem

There is no international rulebook for supervising payment agents. A regulator writing one has to answer
questions nobody has answered before:

- Should a credential older than 730 days be a breach, or 365?
- Is a delegation chain of depth 4 acceptable, or 3?
- Should "no compliance contact on record" block authorisation, or only
  register a concern?
- Which of these rules actually catch anything, and which have never fired?

Today those answers are typed into `registry/rulesets/*.json` and shipped.
Nobody can see what a change would have done. The sandbox is the answer to
"how do we know?" — a place to change a rulebook, run it against every
labelled submission we hold, and see exactly what changed before any of it
becomes policy.

This is the half of the concept note that is currently a promise
(`docs/concept-note.md`: "it is also a policy sandbox"). It is also PLAN
item 14, whose two lines have been open since the beginning.

---

## What already exists

The sandbox is mostly assembly, not invention. Four pieces are in place:

**Labels are real and isolated.** `data/dossiers/*/ground_truth.json` holds
26 planted defects (21 Kestrel, 5 Halcyon) and 54 labelled-clean runs, each
`{run_ref, failure, what}`. `load_for_pipeline()` simply does not read the
file — that omission *is* the isolation mechanism, and `data/uploads.py`
strips any `ground_truth.json` from a submitted zip. Nothing has to be
scrubbed later.

**An evaluation engine.** `eval/__main__.py` already runs the production
graph over every labelled dossier in a temporary ledger, opens the labels
only after the graph returns, and computes tp/fp/fn, precision and recall
overall, per agent, per rule and per failure — plus a false-positive rate on
labelled-clean runs and explicit `missed` / `unexpected` lists. It has a
`--live` flag for judged rules. **This is the sandbox's engine.** What it
lacks is a ruleset parameter, persistence, and a UI.

**Rules are already data with the right shape.** All 102, across all nine
domains. Every rule carries
`status: active|draft|retired`, an integer `version`, `effective_from`,
`severity_weight`, `evaluation`, typed `params`, and the `failures` it can
establish. Nine rulebooks, one per agent, so each domain tunes independently.

**Agents already accept an injected ruleset.** `agent.run(dossier, ruleset)`
takes the book as an argument rather than loading it — done deliberately in
Phase 2 so the sandbox could swap a draft in without touching agent code
(`agents/base.py` docstring says exactly this). `RULESET_LOADERS` in
`agents/catalog.py` is the single seam to override.

So the work is: a versioned draft store, a sweep runner that parameterises
eval by ruleset, a comparison, a promotion gate, and a page.

---

## Mental model: policy as a versioned experiment

The unit the regulator works with is a **ruleset version**, and the thing
they look at is a **sweep** — one rulebook run against the whole labelled
corpus, producing a scorecard.

```
  active v2026.9  ────────────────────────────────────►  (in force)
        │
        └── draft "shorter credential life"  ── sweep #12 ─┐
                    │                                      │  compare
                    └── edit max_age 730→365 ─ sweep #13 ──┘
                                │
                          promote (human-gated) ──► active v2026.10
```

Three rules make this honest, and each maps to something the codebase
already believes:

1. **A published version is immutable.** Editing produces a new draft, never
   a mutation of what a past sweep was measured against. Otherwise a
   scorecard means nothing a week later.
2. **A sweep is pinned to what produced it** — ruleset digest, corpus digest,
   code revision, and mode (mechanical or live). Two sweeps are comparable
   exactly when their non-ruleset pins match. Same discipline as
   `context_digest` on a dispatch.
3. **Promotion is a named human act on the ledger**, like every other
   consequential act in this system. `ruleset_promoted` sits beside
   `authorisation_decided`.

Draft rulebooks are **not** the active registry and are never readable by a
live review. That isolation must be structural, not conventional — see
"Isolation" below.

---

## What the sandbox has to answer

"Which rules work" is really five questions, and only the first two are
per-rule.

**1 · Does the rule catch what it should?** Recall, against labels for the
failures the rule declares. `eval` computes this today.

**2 · Does it fire when it shouldn't?** False positives, split into two very
different kinds — a rule firing on a **labelled-clean run** (a real false
positive), and a rule firing on a **defective run for the wrong reason**
(noise, not error). `eval` reports the first; the second needs the
`unexpected` list broken out per rule.

**3 · Does it fire at all?** A rule with zero firings across the entire
labelled corpus is either dead, unreachable with current data, or waiting on
a defect nobody has planted. This is the cheapest and most useful signal the
sandbox can give, and it needs no labels — just a run.

**4 · Does the threshold matter?** For a rule with a numeric `param`, sweep a
range and show where the outcome actually changes. Most thresholds have wide
dead zones; the interesting number is the edge.

**5 · Does the *case* come out right?** The question a regulator actually
cares about. Not per-rule F1 but: with this rulebook, does each dossier get
the right **disposition**? `pipeline/authorisation.py::recommend()` already
produces one, and the labels tell us which dossiers should be refused. This
is a small confusion matrix over dossiers, and it is the headline number.

`eval` answers 1 and 2 and gives the raw material for 3. Questions 4 and 5
are new.

---

## Data model

Four new objects. All schemas in `schemas/sandbox.py`; drafts on disk under
`registry/drafts/`, sweeps in their own SQLite file.

```python
class RulesetDraft:
    draft_id: str            # "kya@2026.9+shorter-credential-life"
    domain: str              # kya | mandate | consent | …
    base_version: str        # the published version it branched from
    label: str               # human name: "shorter credential life"
    ruleset: Ruleset         # the full edited book
    digest: str              # sha256 over canonical bytes
    created_by: str
    created_at: str
    notes: str | None

class SweepPins:             # two sweeps compare iff these match
    corpus_digest: str       # every dossier + its labels
    code_revision: str       # git rev of the pipeline that ran it
    mode: Literal["mechanical", "live"]

class Sweep:
    sweep_id: str
    domain: str
    ruleset_ref: str         # a published version OR a draft_id
    ruleset_digest: str
    pins: SweepPins
    started_at / finished_at: str
    result: SweepResult

class SweepResult:
    dossiers: list[DossierOutcome]     # expected vs. actual disposition
    per_rule: dict[str, RuleScore]     # tp/fp/fn + fired_count + n
    per_failure: dict[str, Metrics]
    clean_run_false_positives: list[tuple[str, str]]
    missed: list[Label]                # labelled, not detected
    unexpected: list[Detection]        # detected, not labelled
    dead_rules: list[str]              # never fired anywhere
```

`RuleScore` carries **counts, not just rates** — see Constraints. A rule
with `recall = 1.0, n = 1` and one with `recall = 1.0, n = 40` must not look
alike on screen.

Promotion appends one ledger event:

```
ruleset_promoted  {domain, from_version, to_version, draft_id,
                   ruleset_digest, sweep_id, promoted_by, rationale}
```

The `sweep_id` is the point: **the evidence the promotion rested on is part
of the promotion record.** A future regulator can ask "what did you know
when you tightened this?" and get an answer.

---

## The page

A new top-level section beside Overview / Case queue / Portfolio:
**Policy sandbox**. Three panes, because the work has three phases —
choose a version, edit it, see what it did.

### Left · version history

The git-like surface, and the reason this is a page rather than a dialog.
A vertical graph per domain, newest at top:

```
 ● v2026.10   active            promoted by A. Beridze · 4 Sept
 │            37 active rules · sweep #13
 │
 ├─○ draft   shorter credential life        sweep #13  ▲2 caught  ▼1 new FP
 │           edited: KYA-ISS-04 730→365
 │
 ├─○ draft   block unlicensed operators     never swept
 │
 ● v2026.9    superseded        promoted by A. Beridze · 2 Sept
```

Each node shows what it *is* and, if swept, its headline delta against its
base. A draft with no sweep says so plainly rather than showing zeros.
Selecting two nodes enables **Compare**.

### Centre · the rulebook

The draft being edited, as a table — not raw JSON. One row per rule:

| | rule | status | severity | params | fires | catches |
|---|---|---|---|---|---|---|
| ● | `KYA-ISS-04` | active | 0.85 | `max_reaccreditation_age_days: 730` | 4 | 2/2 |
| ○ | `KYA-CAP-04` | draft | 0.40 | — | 0 | — |
| ◌ | `KYA-LIF-03` | active | 0.50 | `min_validity_days: 30` | **0** | — |

Editable in place: **status** (active/draft/retired), **severity_weight**,
and **params** — typed, so `max_depth` gets a number input and
`allowed_algs` a token list, driven off the existing `typed_params()`.
Description and `failures` are not editable here; changing what a rule
*means* is a code change, not a policy tuning.

Rows carry their own evidence from the last sweep: how often the rule fired,
and how much of what it should have caught it caught. A row that never fires
is greyed — question 3, answered without asking.

Any edit forks a new draft rather than mutating the current one, so the
version graph on the left grows as you work. That is the "like git" the
feature needs: not branches and merges, but *nothing you look at can change
under you*.

### Right · the scorecard

The result of the selected sweep, or the delta between two.

**Headline — question 5, dossier dispositions:**

```
              expected      v2026.9       draft
  KESTREL      refuse        refuse ✓      refuse ✓
  HALCYON      refuse        incomplete ✗  refuse ✓
```

**Then the corpus totals**, with counts beside every rate:

```
  caught      22 / 26 labelled defects        (was 21)
  missed       4                              (was 5)
  false pos    1 clean run of 54              (was 0)   ← the cost
```

**Then the per-rule table**, sorted by what changed, then by impact.

**Then the two lists that actually teach you something:**
`missed` (a labelled defect no rule caught — with the label's own `what`
text, so you can see whether it is a rule gap or a data gap) and
`unexpected` (a detection with no label — either a false positive or a
label that is wrong, and the sandbox cannot tell you which).

**Compare mode** shows the same shape with before/after columns and, most
importantly, **the flips**: which specific `(run, failure)` pairs moved
TP→FN or clean→FP. A rulebook change is judged by what it changed, not by
its absolute score.

Below the scorecard, when a draft beats its base: **Promote** — disabled
without a sweep on current pins, and gated on a named reviewer plus a
rationale, exactly like the authorisation gate.

---

## Backend

```
registry/drafts/<domain>/<draft_id>.json     draft rulebooks
sandbox/store.py                             sweeps (own SQLite, NOT the ledger)
sandbox/sweep.py                             eval, parameterised by ruleset
api/sandbox.py                               drafts, sweeps, compare, promote
```

**The sweep runner** is `eval/__main__.py::evaluate()` refactored to take
`rulesets: dict[str, Ruleset]` and return a typed `SweepResult` instead of a
dict. The CLI keeps working by passing the active books. Nothing about how a
review runs changes — the sandbox uses the *production graph*, which is the
only way its numbers mean anything.

**Isolation** must be structural, matching how ground truth is isolated:

- Draft books live under `registry/drafts/`, which `registry/loader.py` has
  no function to read. The sandbox passes drafts in explicitly.
- A sweep runs against a **temporary ledger** (`eval` already does this), so
  sandbox runs never touch case history or a real disposition.
- Labels are opened only after the graph returns, in the sweep runner, never
  inside the pipeline. A test should assert no `ground_truth` key can appear
  in any dispatch context — the existing eval-ground-truth tests extend to
  cover this.

**Cost and time.** A mechanical sweep is two dossiers × the full graph with
no model calls — seconds, free, and reproducible. A live sweep costs eight
model calls per dossier and takes ~75 s each. Mechanical is the default;
live is an explicit choice, needed only for judged rules.

---

## Constraints to state on the page, not bury

These are the difference between a sandbox and a slot machine.

**The corpus is tiny.** 26 planted defects, 54 clean runs, 2 dossiers. Most
per-rule metrics rest on **one or two** examples. A rule at "100% recall"
over n=1 has told you almost nothing. Every rate on screen must carry its n,
and anything under about 5 should be labelled *insufficient evidence*
rather than given a number that invites trust. Expanding the corpus is the
highest-value follow-on work this feature will produce, and the sandbox
should say so by making the thinness visible.

**Labels are not per-rule annotations.** They say "this run had F42", not
"rule MND-CAP-01 should fire here". Per-rule metrics inherit the labels of
the failures the rule declares — diagnostic, not independent validation.
`eval`'s existing `coverage_note` says this; the page must repeat it where
the numbers are, not in a footnote.

**Mechanical sweeps cannot evaluate judged rules.** In mechanical mode the
model never runs, so `MND-SEM-01`, `INJ-ACT-01`, `CNS-VFM-01` and the rest
return inconclusive and their failures are excluded. That is **90 of 102
rules evaluable mechanically**, but it is very unevenly spread — Identity &
Authority is 37/39 and Control Assurance 15/15, while Transaction Patterns
is 0/3 and Behavioural Drift 0/1. A mechanical sweep tells you almost
everything about the first two and nothing about the last two, and the page
must say which domains its numbers actually cover rather than presenting one
total.

**A sweep measures the corpus, not the world.** Two synthetic dossiers built
by us. It can prove a rule is dead or a threshold is inert; it cannot
establish a false-positive rate a regulator could rely on.

---

## Build order

1. **`SweepResult` and the parameterised runner.** Refactor `evaluate()` to
   take rulesets and return a typed result; CLI unchanged. Adds question 3
   (dead rules) and question 5 (dossier dispositions) to what it computes.
2. **Draft store + digests.** `registry/drafts/`, fork/edit/delete, canonical
   digest. No UI yet; tests only.
3. **Sweep store + compare.** Persist sweeps with pins; a `compare(a, b)`
   that returns deltas and flips.
4. **API.** `GET/POST /sandbox/drafts`, `POST /sandbox/sweeps`,
   `GET /sandbox/compare`, `POST /sandbox/promote`.
5. **The page.** Version graph, rulebook table, scorecard. All nine domains
   behind a selector, defaulting to Identity & Authority.
6. **Promotion.** Ledger event, named reviewer, sweep id recorded, active
   book rewritten to a new version.
7. **Threshold sweeps** (question 4) — the one genuinely new analysis, and
   the most demonstrable: a slider showing where an outcome flips.
8. **Cross-domain sweeps.** Steps 1–7 version one rulebook at a time; the
   headline question (does the dossier get the right disposition?) needs all
   nine, since `recommend()` reads every book. A sweep therefore always runs
   the whole rulebook and only the *edited* domain varies — which the pins
   already express.

---

## Open decisions

1. **Does promotion rewrite `registry/rulesets/<domain>.json`, or write
   `<domain>@2026.10.json` beside it and move a pointer?** The second keeps every
   published version on disk and readable, which fits the immutability rule
   and makes the version graph real rather than reconstructed from git. It
   costs a small change to `loader.py`. Recommended.
2. ~~Scope~~ **Settled:** all nine domains, one rulebook, with the page
   defaulting to Identity & Authority — the domain where no standard exists,
   which is the argument the concept note makes.
3. **Live sweeps: allowed from the UI, or CLI-only?** They cost real money
   and take minutes. Recommendation: allowed, but behind an explicit
   confirmation showing the estimated call count, and never the default.
4. **Does a promoted rulebook re-open decided cases?** A case decided under
   v2026.9 was decided under that policy. The recommendation should stay
   pinned to the policy version that produced it — `AuthorisationRecommendation`
   already records `policy_version`, so this is a display question, not a
   modelling one. Worth confirming before the page implies otherwise.
