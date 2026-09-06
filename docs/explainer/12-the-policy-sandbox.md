# 12 · The policy sandbox

## 1 · The question it exists to answer

There is no international rulebook for supervising payment agents. A regulator
writing one has to answer questions nobody has answered before:

- Should a credential older than 730 days be a breach, or 365?
- Is a delegation chain of depth 4 acceptable, or 3?
- Should "no compliance contact on record" block authorisation, or only register
  a concern?
- **Which of these rules actually catch anything, and which have never fired?**

Without a sandbox, those answers get typed into a JSON file and shipped, and
nobody can see what the change would have done. The sandbox is the answer to
*"how do we know?"* — a place to change a rulebook, run it against every
labelled submission the regulator holds, see exactly what changed, and only then
make it policy.

It is also the half of the concept note that would otherwise be a promise, and
the half that speaks to the standard-setting gap rather than the supervision
gap.

## 2 · The mental model: policy as a versioned experiment

The unit a regulator works with is a **rulebook version**. The thing they look
at is a **sweep** — one rulebook run against the whole labelled corpus,
producing a scorecard.

```
  in force  v2026.9  ──────────────────────────────────►  (applies to real reviews)
        │
        └── draft "shorter credential life"  ── sweep #12 ─┐
                    │                                       │  compare
                    └── edit max_age 730 → 365 ─ sweep #13 ─┘
                                │
                    promote (named human + rationale + sweep id)
                                │
                                ▼
                        in force  v2026.10
```

Three rules make this honest:

1. **A published version is immutable.** Editing produces a **new draft**, never
   a mutation of what a past sweep was measured against. Otherwise a scorecard
   means nothing a week later.
2. **A sweep is pinned to what produced it** — the rulebook digest, the corpus
   digest, the code revision, and the mode (mechanical or live). Two sweeps are
   comparable exactly when their non-rulebook pins match. Promoting on the
   strength of a scorecard taken against a different corpus would be *worse*
   than promoting with no evidence at all, because it would look like evidence.
3. **Promotion is a named human act on the ledger**, sitting beside the
   authorisation decision in the same event vocabulary.

## 3 · The five questions a sandbox has to answer

"Which rules work" is really five questions, and only the first two are per-rule.

| | Question | How it is answered |
|---|---|---|
| **1** | Does the rule catch what it should? | Recall, against the labels for the failures the rule declares |
| **2** | Does it fire when it shouldn't? | False positives, split into two very different kinds: firing on a **labelled-clean run** (a real false positive) versus firing on a defective run **for the wrong reason** (noise, not error) |
| **3** | **Does it fire at all?** | A rule with zero firings across the entire corpus is dead, unreachable with current data, or waiting on a defect nobody has planted. **The cheapest and most useful signal available, and it needs no labels** |
| **4** | Does the threshold matter? | Sweep a numeric parameter across a range and show where the outcome actually changes. Most thresholds have wide dead zones; the interesting number is the edge |
| **5** | **Does the case come out right?** | Not per-rule F1 — with this rulebook, does each dossier get the right **disposition**? This is the headline number, and it is the one a regulator actually cares about |

## 4 · How a sweep works

A sweep runs the **production graph**, not a simplified copy. That is the only
way its numbers mean anything.

```
   for each labelled dossier:
        load it — WITHOUT its labels
        submit it to a throwaway ledger
        run the real review pipeline, with the draft rulebook passed in
        ── graph returns ──
        only now: open ground_truth.json
        compare
```

The isolation is **structural rather than conventional**, mirroring how ground
truth is isolated everywhere else in the system:

- The pipeline loader has no code path that reads `ground_truth.json`. Labels
  are opened in the sweep runner, after the graph has returned.
- Every sweep runs against a **temporary ledger**, so a sandbox experiment can
  never touch case history or a real disposition.
- Draft rulebooks live under `registry/drafts/`, and the registry loader has **no
  function that reads that directory**. A live review cannot load a draft even
  by mistake, because there is no code path that would. Drafts reach the graph
  only as an explicit argument.

**Mechanical vs live.** A mechanical sweep runs the whole pipeline with no model
calls: seconds, free, and perfectly reproducible. A live sweep additionally runs
the judged rules, which costs real model calls and takes minutes. Mechanical is
the default; live is an explicit choice, needed only for judged rules.

## 5 · What comes back

A sweep result carries, per dossier, the expected disposition against the actual
one; per rule, true/false positives and negatives **with counts, not just
rates**, plus how often the rule fired at all; per failure, the same; the list of
false positives on labelled-clean runs; the **missed** list (a labelled defect no
rule caught, carrying the label's own description so you can see whether it is a
rule gap or a data gap); the **unexpected** list (a detection with no label —
either a false positive or a wrong label, and the sandbox cannot tell you which);
and the **dead rules** list.

Compare mode shows the same shape with before/after columns and, most
importantly, **the flips**: which specific (run, failure) pairs moved from caught
to missed, or from clean to false positive. **A rulebook change is judged by what
it changed, not by its absolute score.**

## 6 · The page

A top-level section beside Overview, Case queue and Portfolio, in three panes,
because the work has three phases — choose a version, edit it, see what it did.

**Left · version history.** A vertical graph per domain, newest at top: the book
in force with who promoted it and when, every draft beneath it with its headline
delta against its base, and every superseded published version still readable on
disk. A draft with no sweep says so plainly rather than showing zeros. Selecting
two nodes enables Compare.

**Centre · the rulebook**, as a table rather than raw JSON. One row per rule with
its status, severity, parameters, how often it fired in the last sweep, and how
much of what it should have caught it caught. Editable in place: **status**,
**severity weight**, and **typed parameters** — a numeric threshold gets a number
input, an allowlist gets a token list. Description and the failures a rule
declares are **not** editable here: changing what a rule *means* is a code
change, not a policy tuning. **Any edit forks a new draft** rather than mutating
the current one — which is the "like git" property the feature actually needs:
not branches and merges, but *nothing you are looking at can change under you*.
A row that never fires is greyed out, which answers question 3 without anyone
asking it.

**Right · the scorecard.** The headline dossier-disposition matrix first, then
corpus totals with counts beside every rate, then the per-rule table sorted by
what changed, then the two lists that actually teach you something — `missed` and
`unexpected`. Below it, when a draft beats its base: **Promote**, disabled
without a sweep on current pins, and gated on a named reviewer plus a rationale,
exactly like the authorisation gate.

## 7 · Promotion

Promotion is the one act in the sandbox that is real supervision rather than
rehearsal, so it is the one thing that reaches the ledger. It is refused unless:

- the sweep measured **this exact draft as it now stands** (digest match),
- the sweep actually produced a result,
- the **corpus has not changed** since that sweep, and
- a **rationale** was written.

Then the outgoing book is copied aside so every published version stays readable
on disk (the version graph is a fact, not something reconstructed from git), the
new version is written into force, and one ledger event is appended:

```
ruleset_promoted  { domain, from_version, to_version, draft_id,
                    ruleset_digest, sweep_id, rationale, edits,
                    evidence: {overall metrics, clean-run false positives,
                               dossiers correct} }
                  actor: human:<name>
```

**The sweep id is the point.** The evidence a promotion rested on is part of the
promotion record. A future regulator asking *"what did you know when you
tightened this rule?"* gets an answer instead of a commit message.

## 8 · The constraints the page states rather than buries

These are the difference between a sandbox and a slot machine, and they belong
on screen next to the numbers, not in a footnote:

- **The corpus is tiny.** 26 planted defects, 54 clean runs, 2 dossiers. Most
  per-rule metrics rest on one or two examples. A rule at "100% recall" over
  n=1 has told you almost nothing. Every rate carries its n, and anything under
  about five is labelled *insufficient evidence* rather than given a number that
  invites trust.
- **Labels are not per-rule annotations.** They say "this run had F42", not
  "rule `MND-CAP-01` should fire here." Per-rule metrics inherit the labels of
  the failures the rule declares — diagnostic, not independent validation.
- **Mechanical sweeps cannot evaluate judged rules**, and the coverage is very
  unevenly spread: Identity & Authority is nearly fully mechanical, Control
  Assurance entirely so, while Transaction Patterns and Behavioural Drift are
  entirely judged and a mechanical sweep says nothing about them. The page
  reports which domains its numbers actually cover rather than showing one
  total.
- **A sweep measures the corpus, not the world.** It can prove a rule is dead or
  a threshold inert. It cannot establish a false-positive rate a regulator could
  rely on.

## 9 · Why this is only possible because of an early decision

Agents take their rulebook **as an argument** rather than loading it themselves —
a decision made deliberately during the build, before the sandbox existed, so
that a draft could be swapped in without touching agent code. There is one seam
in the whole system where a rulebook override is applied.

That is why the sandbox is mostly assembly rather than invention, and why its
numbers come from the real pipeline instead of a parallel implementation that
would inevitably drift from it.
