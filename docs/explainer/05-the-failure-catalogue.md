# 05 · The failure catalogue — the 87 things that can go wrong

Before you can supervise something you have to say what "going wrong" means.
The catalogue is that list: **87 named, stable failure modes**, `F1`–`F87`, each
with a plain-English name, an owning phase of the agent's lifecycle, and an
owning specialist. Every rule in every rulebook declares which failures its
breach establishes, so a finding always connects back to a named harm rather
than to a rule id nobody can interpret.

It lives as data (`registry/failures.json`, catalogue version 2026.1) and in
depth, with the reasoning for each entry, in `docs/coverage-model.md`.

## 1 · The seven phases

The catalogue is organised by **when in an agent's life the failure happens**,
which is also how the specialists are divided:

| Phase | What happens | Owning agent(s) | Failures |
|---|---|---|---|
| **P0** | The agent comes into existence | KYA | F1–F23 (23) |
| **P1** | A human authorises it | Consent & Harm | F24–F31 (8) |
| **P2** | The agent assembles a cart | Provenance · Injection | F32–F38 (7) |
| **P3** | The mandate is signed | Mandate | F39–F50 (12) |
| **P4** | The payment executes | Counterparty | F51–F58 (8) |
| **P5** | Many payments accumulate | Log · Drift | F59–F66 (8) |
| **P6** | Many agents act at once | Systemic | F67–F69 (3) |
| **X1** | *cross-cutting* — the firm's own controls run | Control Assurance | F70–F73 (4) |

Notice where the weight sits. **P0 has 23 failures** — almost a third of the
catalogue is about whether the agent should have existed at all, before it ever
spends anything. And **P2 has 7 failures that no amount of signature checking
can find**, because they all happen before anything is signed.

## 2 · The catalogue

Each entry below is the failure's registered name. The depth — why each is not
okay, how it presents, and how it is detected — is in `coverage-model.md`.

### P0 · The agent comes into existence → KYA

*Before an agent can pay for anything, somebody has to vouch for it. This phase
asks whether that vouching is worth anything.*

| | |
|---|---|
| F1 | The organisation that issued the credential was never approved |
| F2 | The issuer was shut down before it issued this |
| F3 | The issuer isn't trusted enough for this kind of money |
| F4 | Nobody has re-checked this issuer in years |
| F5 | The credential's dates are impossible |
| **F6** | **The chain of responsibility never reaches a person** |
| F7 | The person at the end isn't the person who authorised the payment |
| F8 | One link in the chain is forged |
| F9 | The same entity appears twice in the chain |
| F10 | The chain has too many steps |
| F11 | A middle party granted more authority than it had |
| F12 | The firm operating the agent isn't licensed |
| F13 | The firm is licensed but in trouble |
| F14 | The firm changed hands after the credential was issued |
| F15 | There's no named person at the firm to contact |
| F16 | The agent was never declared to us |
| F17 | The agent has no declared risk class |
| F18 | Nobody recorded which model made the decisions |
| F19 | The model has known vulnerabilities and is still in production |
| F20 | The agent's permissions have been quietly widening |
| F21 | Two credentials for the same agent are valid at once |
| F22 | One key is backing two supposedly different agents |
| F23 | The same credential id is used by different agents |

**F6 is the single most important check in the system.** An AI agent has no
legal identity — it cannot be fined, sued, struck off, or called to a hearing.
If authority does not terminate in a human or a legally liable entity, then when
the agent causes a loss there is literally nobody to hold accountable, and the
consumer absorbs it. That is the entire reason "Know Your Agent" exists.

Two entries show why the catalogue had to be written carefully rather than
brainstormed. **F2** cannot be checked by asking "is this issuer approved
today" — that wrongly rejects every credential the issuer legitimately issued
before its shutdown. Nor by "does the signature verify" — maths does not know
the office closed. The only correct check compares *this credential's issue
date* against *the shutdown date*. **F21** cannot be seen in a credential at
all; it needs the credential *series*, which is why `credential_history` is in
the data contract.

### P1 · A human authorises it → Consent & Harm

*The concept note opens on consumer loss. This phase is the part of the system
that is actually about the consumer.*

| | |
|---|---|
| F24 | A human was required to be present and wasn't |
| F25 | The consent is old |
| F26 | The agent spent it on something the person didn't agree to |
| F27 | The consent was obtained in a way that isn't strong enough |
| F28 | The consent screen was designed to get a yes |
| **F29** | **The person approved one thing and signed another** |
| F30 | A one-time yes became a standing authority |
| F31 | There's no record that a human was ever involved |

F29 is only detectable because the run carries `rendered_values` — what the
screen actually showed. Comparing that against the signed cart is a two-field
check that no amount of cryptography substitutes for.

### P2 · The agent assembles a cart → Provenance · Injection

*The phase where the published research says the attacks actually live, and
where signed artifacts are structurally blind.*

| | |
|---|---|
| **F32** | **The agent acted on instructions hidden in content it read** |
| F33 | The agent called a tool nobody authorised |
| F34 | The agent transacted with a counterparty it couldn't verify |
| F35 | The agent's objective was redirected, and stayed redirected |
| F36 | The agent's instructions were changed outside any review |
| F37 | A different model made the decisions than the one declared |
| F38 | The agent is quietly choosing worse options |

F32 is prompt injection, and the supervisory question is not only *whether* it
happened but **through which channel** — a product listing, a tool result, a
merchant page, the user prompt itself. That is where a firm's sanitisation is
leaking, and it is what makes the finding actionable rather than merely
alarming.

F38 — "quietly choosing worse options" — is the detectable signature of an agent
tuned toward merchants that pay for placement. It is visible only because runs
carry `selection_context`: the alternatives the agent considered and rejected.

### P3 · The mandate is signed → Mandate

*The classic scope questions: did the agent stay inside what the human actually
authorised?*

| | |
|---|---|
| F39 | The cart doesn't match the authorisation it claims to come from |
| F40 | The payment doesn't match the cart it claims to come from |
| F41 | The payment amount isn't the cart total |
| F42 | The order is bigger than the person allowed |
| F43 | Individually fine, collectively over the limit |
| F44 | The agent bought from the wrong kind of business |
| F45 | The agent paid someone not on the approved list |
| F46 | The currency isn't the one authorised |
| F47 | The payment happened outside the mandate's lifetime |
| F48 | The merchant is in a region the mandate excludes |
| **F49** | **Technically within the rules, but not what the person meant** |
| F50 | The same authorisation was used twice |

**F49 is the failure that justifies the entire human-present data model.** The
shopper asked for a vitamin C serum; the agent bought a ceramide night cream,
inside the budget, from an approved merchant, with every signature valid. Every
mechanical rule passes. The only thing that catches it is comparing the cart
against *this shopper's sentence* — which is possible only because the Intent
Mandate lives on the run and carries natural language.

### P4 · The payment executes → Counterparty

*We verified the payer exhaustively and never once checked the payee. AML has
always been about the other side of the transaction.*

| | |
|---|---|
| F51 | Nobody knows who was paid |
| F52 | A platform is hiding who actually sold the goods |
| F53 | The money went to a wallet with no identifiable owner |
| F54 | The recipient is on a list they shouldn't be paid from |
| F55 | A brand-new recipient is suddenly getting most of the money |
| F56 | One recipient is masquerading as several |
| **F57** | **The same recipient is being paid by firms that have nothing to do with each other** |
| F58 | Reversals and declines are clustering oddly |

F57 is structurally invisible to any single firm and visible to a supervisor for
free. So is F52 in its worst form: a marketplace listing with no sub-merchant
disclosed means every check runs against the platform's reputation while the
actual seller stays anonymous.

### P5 · Many payments accumulate → Log · Drift

*No single transaction is wrong. The set is.*

| | |
|---|---|
| F59 | One payment was split to stay under the reporting threshold |
| F60 | Too many payments too fast |
| F61 | Nearly all the money goes to one recipient |
| F62 | Suspiciously round numbers |
| F63 | Payments at hours the business doesn't operate |
| F64 | The agent is feeling for its limit |
| **F65** | **The agent doesn't behave like it used to — and something specific changed it** |
| F66 | Someone is generating noise to exhaust the reviewers |

F65 carries a deliberate second clause. Detecting that behaviour changed is
statistics; **finding the change-log event sitting at the onset boundary** —
the model repin, the prompt release, the control change — is what turns it into
something a supervisor can write a letter about.

### P6 · Many agents act at once → Systemic

*The one structural advantage a central bank has over any vendor.*

| | |
|---|---|
| F67 | Everyone is running the same model |
| F68 | Independent agents are all moving together |
| F69 | The same attack is running at several firms at once |

F69 is the cheapest cross-firm win in the catalogue: once one firm's injected
tool-result excerpt has been read and understood, **the same content digest
appearing at another firm identifies the same payload with no further
analysis.**

### X1 · The firm's own controls → Control Assurance

*The difference between a detection tool and a supervision tool.*

| | |
|---|---|
| F70 | The firm has no control for a risk its own mandate creates |
| F71 | A control existed, should have fired, and didn't |
| F72 | A control fired and someone switched it off |
| F73 | A control fired, held, and the breach happened anyway |

These four are the second half of every other finding. "This payment breached
the shopper's cap" is true; **"and your own blocking control fired and was
overridden 52 seconds later by a named analyst on an unverifiable verbal
approval" is actionable.** F73 — a control held and the payment settled anyway
— is severe enough to be a hard refusal gate on its own (document 10).

## 3 · How the catalogue was disciplined

It started at 87 and was **cut to 73** after an audit for duplication and
realism, which is worth knowing because it shows the list is engineered rather
than brainstormed:

- **Eight pairs were one failure seen from two angles** — rendered-versus-signed
  and constraint-mutation; the four injection channels; drift and memory
  poisoning; herding, synchronised timing and sector drift. Each pair collapsed
  into one entry, because two ids for one harm means double-counting in the
  score.
- **Three were cut as not real.** *Cryptographic aging* (Ed25519 is not aging in
  2026), *stale-mandate reuse* (a mandate used inside its own validity window is
  valid — it is the window check or it is nothing), and *runaway spending* (it
  is either the cumulative-cap breach or the missing cumulative control, never a
  third thing).

## 4 · What the catalogue revealed about the original design

The concept note's design — deterministic ingestion, four specialists, a score,
a grounded report — was sound, and structurally all of it survived. But writing
the catalogue exposed five assumptions that were wrong, and each explains a
whole phase of missing coverage. This is the honest origin story of why there
are eleven agents rather than four:

1. **We supervised the artifact, not the decision.** All four original
   specialists read signed objects. The attacks target the process that produced
   them. *(explains all of P2 — 7 failures)*
2. **We supervised the transaction, not the entity.** Every finding was about a
   payment; a supervisor's actual question is about the firm. *(explains X1 — 4
   failures)*
3. **We supervised one case at a time.** The concept note itself names
   correlated agent behaviour as a risk "a firm-by-firm review is unlikely to
   catch" — and then reviewed firm by firm. *(explains P6 — 3 failures)*
4. **We verified the payer and never the payee.** *(explains P4 — 8 failures)*
5. **We never checked whether a human was actually there.** `human_presence_required`
   was in the schema and no rule read it. *(explains P1 — 8 failures)*

A sixth was about output shape rather than coverage: **verdicts where
supervision needs instances.** "concentration: true" is unusable; *this
counterparty, these seven transactions, this share, this window* is a finding.
That correction is document 09.
