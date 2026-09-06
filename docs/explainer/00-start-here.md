# Mandate Supervisor — the complete explainer

This directory explains the whole product in plain language: the idea, the data,
the rules, the agents, the architecture, the decision it produces, and the
tooling around it. It is written to be read by someone who will never open the
code — a supervisor, a policy lead, a judge, an executive — and to be complete
enough that after reading it you can answer any question about the system.

Nothing here is aspirational. Everything described is either **built** (and
says so) or explicitly marked as **not yet built**. Section 15 lists the known
weaknesses on purpose, because a pitch that only lists strengths is not
credible to the audience this is aimed at.

---

## The one-paragraph version

An AI payment agent is given a budget and a purpose and then decides for itself
when, how much, and with whom to transact. No regulator has a way to check what
one of those agents actually did against what it was allowed to do. Mandate
Supervisor is the regulator's side of that: an operator submits a **dossier** —
the agent's identity credential, the mandates it operated under, the controls
its firm claims to run, and the complete record of the runs it executed — and
the system reviews it. Eleven specialist agents each answer one supervisory
question, each backed by a deterministic rulebook that produces facts a human
can re-check, plus at most one contained language-model call for the part that
genuinely needs judgement. The findings are combined by a versioned, published
policy into one of four dispositions: **authorise, monitor, refuse, or
incomplete submission**. Nothing leaves the system without a named human
approving it, and every step is written to a hash-chained, append-only ledger.
Beside the review sits a **policy sandbox** where a regulator can edit a
rulebook, run it against the entire labelled corpus, see exactly what changed,
and only then promote it into force.

---

## The one-sentence version

**Payments already approves things by testing them; nobody has said what the
test looks like for an AI payment agent, and this is that test, built.**

---

## How to read this

The documents stand alone but are ordered as an argument. If you read them in
order you get the case from first principles; if you need one topic, jump.

| # | Document | What it answers |
|---|---|---|
| 01 | [The problem](01-the-problem.md) | Why agentic payments break existing supervision, and why this is a real regulatory regime rather than an invented one |
| 02 | [What the product does](02-what-the-product-does.md) | The regulatory act, who submits, who decides, the journey end to end |
| 03 | [The data](03-the-data.md) | What a dossier contains, what the regulator holds instead, AP2, and why the split matters |
| 04 | [The corpus and its realism](04-the-corpus-and-realism.md) | The synthetic evidence: two dossiers, 70 runs, 154 transactions, 26 planted defects, and what makes it believable |
| 05 | [The failure catalogue](05-the-failure-catalogue.md) | The 87 things that can go wrong, in seven phases, and why each is not okay |
| 06 | [The rulebooks](06-the-rulebooks.md) | 103 rules across nine domains, rules-as-data, and four rules the corpus proved wrong |
| 07 | [The agents](07-the-agents.md) | The eleven specialists and six support agents: what each owns, what is deterministic, what the one model call does |
| 08 | [The architecture](08-the-architecture.md) | How a review actually runs, node by node, and the constraints that shape it |
| 09 | [Facts, assessments, findings](09-facts-and-findings.md) | The output vocabulary: what the system says and how confident it is allowed to sound |
| 10 | [The decision](10-the-decision.md) | Hard gates, weighed judgement, the four dispositions, and why clean runs count |
| 11 | [The report and the human gate](11-report-and-human-gate.md) | Drafting, grounding, and the named sign-off |
| 12 | [The policy sandbox](12-the-policy-sandbox.md) | Editing a rulebook, sweeping it against labelled evidence, and promoting it |
| 13 | [The audit ledger](13-the-audit-ledger.md) | Hash chain, event vocabulary, replay, and independent verification |
| 14 | [Safety and guardrails](14-safety-and-guardrails.md) | Prompt injection, tool permissioning, and the four mandatory guardrails |
| 15 | [The console](15-the-console.md) | What a case officer actually sees and does |
| 16 | [Evidence and honest limits](16-evidence-and-limits.md) | Tests, evaluation, the independent verifier, and what we do not yet know |
| 17 | [Pitch notes](17-pitch-notes.md) | The narrative, the demo path, and the hard questions with answers |

---

## Where this sits relative to the other docs

`docs/` already holds the working documents the build was made from —
`HANDOFF.md` (the authoritative engineering state), `coverage-model.md` (the
failure catalogue in depth), `kya-ruleset.md`, `synthetic-data-spec.md`,
`migration-plan.md`, and one spec per build phase under `docs/phases/`. Those
are written for whoever is building next.

**This directory is written for whoever is being told about it.** Where the two
disagree on engineering detail, `HANDOFF.md` is right and this should be
corrected.
