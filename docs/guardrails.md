# Guardrails

The hackathon judges against four mandatory guardrails: **human-in-the-loop,
auditability, safety and governance, and cyber risk.** Every one is enforced in
code — graph topology, function signatures, static maps, database triggers —
rather than asked for in a prompt.

That distinction is the whole point. A prompt instruction is a request a model
may decline, forget, or be talked out of. A guarantee that lives in the type
system or the graph cannot be argued with.

---

## 1 · Human-in-the-loop

**Nothing leaves the system without a named human approving it.**

The single `interrupt()` in the codebase sits at `human_gate`, the last node of
the drafting graph (`pipeline/graph.py`). It is not a prompt asking the model to
pause — it is graph topology. There is no edge from `draft_report` to anything
that issues a report, so no amount of model confidence can route around it.

```
load_record → draft_report ⇄ grounding_check → human_gate (interrupt) → END
```

The decision payload is validated server-side; a malformed one re-interrupts
with an error rather than falling through. The gate records a named decision to
the ledger as `authorisation_decided`.

**What the gate guards, and what it does not.** It guards the *artifact* — a
report cannot issue without a named decision, a pause of minutes, exactly what a
checkpointer is for. It does not guard the *case*, which stays open for weeks
and is therefore a ledger state, not a held-open process.

A reviewer can send a report back for re-analysis, capped at
`_MAX_REVIEWER_ROUNDS = 3`; past that they must approve or reject. The cap is
belt-and-braces — the real control is that an explicit named decision is the
only exit.

**Rule promotion is gated the same way.** A sandbox draft becomes policy only
through an explicit promotion (`sandbox/`, `POST /sandbox/promote`). No rule
changes itself.

---

## 2 · Auditability

**Every step lands on a hash-chained, append-only ledger.**

`ledger/store.py`:

- The class **exposes no update and no delete method at all.** The SQL triggers
  are defence in depth for anything that reaches the database another way — the
  primary control is that the capability does not exist in the API surface.
- SHA-256 chain, reusing `data/canonical.py::payload_hash` — the same canonical
  serialization that signs the mandate corpus. One definition of "the bytes of
  this object" across signing and chaining; no second implementation to drift.
- The chain is **global across all cases**, linking by `seq` rather than per
  case. A deleted or reordered event anywhere breaks verification everywhere —
  the stronger property for an audit record.
- Appends serialize under a per-path process lock plus `BEGIN IMMEDIATE` with
  `MAX(seq)` re-read inside the transaction. Specialists finishing simultaneously
  in a fan-out must not fork the chain.

Anyone can check it:

```bash
python -m ledger.verify
```

Exit 0 and "intact", or exit 1 listing every broken link. Also exposed at
`GET /ledger/verify`, because "prove the record has not been tampered with" is a
thing a supervisor should be able to do on demand.

### What is recorded

Event types are a **closed vocabulary validated on write** (`ledger/events.py`),
and every actor is typed `<kind>:<name>`. Facts, assessments, findings,
observations, scores, narrations, critic checks, dispatch plans and decisions
each get their own event and their own sequence number.

The one worth calling out is `dispatch_recorded`: it stores **the exact composed
context each agent received**, byte for byte. Any finding can therefore be traced
back to the precise input that produced it — which is the difference between an
audit trail and a log.

Model-written prose is recorded like any other model output and is explicitly
**never citable evidence**. `specialist_narrated` holds a specialist's briefing
line for the officer; the report cites assessments, never a paraphrase of them.

> **The ledger is not the checkpointer.** LangGraph's checkpointer is disposable
> resume plumbing in a separate store. Delete it, lose in-flight resumability.
> Delete the ledger, lose the audit trail. The separation exists so the second
> one never quietly becomes a source of truth.

---

## 3 · Safety and governance

### Rules are data, and changing them is a supervised act

Ten versioned JSON rulebooks (`registry/rulesets/`), a versioned failure
catalogue, a versioned scoring config, and a versioned authorisation policy.
Nothing is hardcoded — including the systemic sweep's thresholds, because a dial
living in a Python default is the one dial the sandbox cannot tune, sweep or
promote.

The policy sandbox is the governance loop: **draft → sweep the labelled corpus →
diff → promote.** A supervisor sees exactly which findings a proposed rule change
would have added, removed or altered across all 143 runs *before* it becomes
policy. Drafts and sweeps are gitignored on purpose — a draft is a candidate and
a sweep is an experiment; neither should arrive in a checkout looking like law.

What makes the diff mean anything is that each sweep records what it stood on,
content-addressed (`schemas/sandbox.py::SweepPins`): the corpus and its labels,
every policy input on disk — the other nine rulebooks, the scoring weights, the
failure catalogue, the regulator's own registries — and the detection code
itself. Two sweeps are diffed exactly when all of that matches and only the
rulebook differs, so a difference cannot be attributed to a draft that some
other input produced. A mechanical sweep is reproducible to the byte, which is
what makes a flip evidence; a live sweep is not, so flips on model-judged rules
are marked and excluded from the verdict rather than being read as policy.

Nothing in that store is ever deleted, and a version whose rulebook, corpus,
policy and engine are all unchanged is not swept twice — it is handed the
scorecard it already has, which is the same answer at no cost. Promotion is
refused on any scorecard that no longer describes today's conditions.

### The decision cannot be influenced by a model

`pipeline/scoring.py` is a pure function. Same findings in, same score out. When
a firm challenges the number, the answer is a printable derivation: these
findings × these ruleset severity weights, tiered by this config version.

**Observations — unverified model hunches — are excluded from scoring by the
function's signature**, not by convention. That is the strongest available way to
keep "never scored" true permanently, and it is why the type distinction between
`Finding` and `Observation` exists at all.

Hard gates precede weighed judgement (`pipeline/authorisation.py`), so a refusal
for acting on injected content cannot be outvoted by a pile of clean runs. And
adequacy precedes judgement, so a thin submission returns
`incomplete-submission` rather than being quietly authorised because nothing was
found in evidence that was never filed.

### Two deterministic checks on the model tier

**The critic** (`agents/critic.py`) asks: did the specialist quote numbers that
actually appear in the evidence it was given? Answered by value matching against
the recorded dispatch context — no second model judging the first. Scope is
deliberately the model-judged tier only; floor assessments quote values straight
out of facts by construction. It is conservative about what counts (decimals of
any size, integers ≥ 100) so it does not flag "3 payments" as a hallucination.

Critic failures are **recorded and surfaced, never suppressed**. A false negative
in the critic must not be allowed to delete a real finding — the officer sees the
flag and judges.

**The grounding validator** (`agents/grounding.py`) is pure Python and checks the
drafted report: every cited finding id must exist, every confirmed failure must
be cited by some section, observations may appear only in their labelled note (required when
observations exist, forbidden when none do), and a section's declared character
must match the verdicts it cites. Problems are surfaced directly; drafting does
not regenerate the report.

Neither check is a model reviewing a model. That was the alternative, and it was
rejected: a second model can hallucinate in agreement with the first.

### Evidence discipline

`agents/context.py` makes three invariants mechanical:

- **The evidence floor** — the canonical base is always fully present.
  `compose_context()` starts from it and can only add.
- **No summarization** — extra blocks are inserted whole, exactly as fetched.
  The orchestrator *names* blocks; it never authors their content.
- **What was sent is what was recorded** — the composed dict is both what lands
  in `dispatch_recorded.context_blocks` and what the reasoning function
  serializes into its message, byte for byte.

---

## 4 · Cyber risk

### Injection is contained at the entry point

Ingestion is **deterministic and never touches a model** (`ingestion/`). A
schema-invalid submission raises at the door; garbage that cannot be normalised
is a different failure class from a submission with something wrong inside it,
which comes back as facts. No model sees an unparsed submission, ever.

Firm-authored free text — the place an injection actually lives — reaches a model
in exactly one contained way. `agents/mandate_reasoning.py` passes merchant line
item descriptions and the agent's own attestation through `_delimit()`, wrapping
them in explicit typed markers, with the model's output schema-constrained on the
other side. The same text is separately regex-triaged by the Injection
specialist.

### The injection triage is honest about being a net

`agents/injection_checks.py` states it plainly: the regex rules are **triage, a
net, not a detector.** The lesson is recorded in the module itself — the first
version of the independent verifier's net was written against the two injections
already in the corpus, and missed the third the moment it was phrased
differently. A pattern tuned on attacks you already know is worth very little
alone.

So the net flags candidates cheaply and deterministically, and *whether the agent
acted on what it read* is the judged rule. That verdict names the channel — the
listing signed into the cart, the shopper's prompt, retrieved reference material,
or the tool's own description checked by hash — because the supervisory question
is where sanitisation leaks.

The Injection module's patterns are deliberately **not shared** with
`scripts/verify_dossier.py`. Sharing them would make the verifier a mirror rather
than a second opinion.

### Tool access is permissioned in code

`agents/tools.py` holds a static agent→allowed-tools map:

```python
"investigator": frozenset({ "get_transactions", "get_run", "get_rule", … }),
"mandate":   frozenset(),   "kya":        frozenset(),
"injection": frozenset(),   "counterparty": frozenset(),
"drafting":  frozenset(),   "orchestrator": frozenset(),   # … all empty
```

**The investigator is the only agent with callable tools.** Every specialist has
an empty set — they judge the evidence they are briefed with; they do not go
looking for more. Every `_*_TOOL` elsewhere in `agents/` is an output-schema
constraint, not a capability.

`tools_for()` is the only way any agent obtains a tool definition, and
`execute_tool()` **re-checks the map on every call** — permissioning enforced at
both ends.

Every tool is read-only, deterministic and non-LLM. None writes to the ledger,
mutates a ruleset, or makes a model call. And none returns
`line_items[].description`, `user_prompt` or `result_excerpt` — the firm-authored
free text where an injection lives. Transaction rows come back structured, so the
injection surface stays closed. Where a result does contain firm-authored strings
(counterparty and firm names), they are delimited exactly as the mandate
reasoning delimits merchant text.

### Other surfaces

- **The graph reads submissions from the ledger by case id**, never from a
  client-supplied path.
- **The run index is verified against file digests** at the door, so a dossier
  cannot omit an inconvenient run. Rebuilt from the ledger there are no files, so
  the rebuild re-validates schema and index membership and the hash chain vouches
  for the rest.
- **Same-origin by construction** — nginx serves the console and proxies both
  backends on one port, so there is no CORS surface.
- **No key ships with the repo.** `ANTHROPIC_API_KEY` is the user's and is billed
  to them; the system degrades to its deterministic floor without one and says so
  rather than failing open.
- **Intake is token-gated when exposed.** `MANDATE_INSTITUTION_TOKENS` unset
  means open intake, which is fine on localhost and must be set before exposing
  the service further.

---

## Summary

| Guardrail | Enforced by | Not by |
|---|---|---|
| Human sign-off before anything issues | Graph topology — the only exit from drafting is an `interrupt()` with a validated named decision | A prompt asking the model to check first |
| Immutable audit trail | No update/delete methods, SQL triggers, global SHA-256 chain, closed event vocabulary | Convention about not editing rows |
| Model cannot influence the decision | Pure scoring function; observations excluded by signature | Instructions telling the model not to score |
| Model output is checked | Deterministic critic + deterministic grounding validator | A second model reviewing the first |
| Injection contained | Model-free ingestion; delimited text in one place; structured tool results; empty tool sets | Telling agents to ignore suspicious instructions |
| Least privilege | Static map, checked at definition and again at execution | A prompt listing which tools to use |
| Rules cannot drift silently | Versioned JSON, sandbox sweep over labelled evidence, human-gated promotion | Editing thresholds in Python |
