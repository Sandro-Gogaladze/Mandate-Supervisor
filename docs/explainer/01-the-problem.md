# 01 · The problem

## 1 · Card payments were built around a human clicking "pay"

Every control in the payments stack assumes a person at the end of a decision.
Authentication proves *that person* is present. Consent is *that person* seeing
a price and agreeing to it. Dispute rights exist because *that person* can say
"I never authorised this." Supervision inherits the same assumption: a payment
is a discrete, logged action that a named human took, and the supervisory
question is whether the firm handled that action correctly.

Agentic commerce breaks the assumption at the root. A payment agent is given a
budget and a purpose, and then decides for itself when to transact, how much to
spend, and who to pay — with no human present for each decision.

**Supervising a click is straightforward. Supervising a decision is not.** A
click is an event you can log. A decision is a process: the agent read
something, chose between options, constructed a cart, and had it signed. The
signature at the end of that process is the only part conventional oversight
can see, and it is the part least likely to be wrong.

## 2 · The gap is not detection, it is standard-setting

There are, today, no KYA (Know Your Agent) rules written for payment agents.
There is no defined test a regulator can apply. There is no shared vocabulary
for what "this agent behaved acceptably" even means.

Industry has moved to fill the gap on its own:

- **Google's AP2** (2025, sixty-plus partners including both major card
  networks) defines a chain of signed mandates binding an agent's action to a
  recorded consent.
- **Mastercard Agent Pay** and **Visa's Trusted Agent Protocol** each bind a
  token to a named agent.
- **Singapore's MAS SAFR** (July 2026, developed with Visa, Mastercard, Ant
  International, HSBC, J.P. Morgan) sorts every proposed agent action into one
  of four dispositions before execution — and describes itself explicitly as an
  *industry reference, not supervisory guidance*.

These are private answers to what is really a public-infrastructure question.
The public sector has not built the equivalent. That is the gap this product
sits in: not "can we detect fraud," but **"what is the supervisory test, and who
runs it."**

## 3 · Why signatures are not enough — the structural fact

The single most important technical fact in this whole design:

> *"Valid mandate signatures alone do not ensure that an agent-mediated
> transaction reflects the user's intent when its pre-authorization context is
> manipulated."*
> — *Beyond the Mandate: A Systematic Security Analysis of AP2*

AP2's cryptography covers the moment of signing. But an AP2 mandate is the
**output** of a decision process, and the attacks target the process — the step
*before* anything is signed. Academic red-teaming cited in this hackathon's own
materials demonstrated a fully valid, correctly signed AP2 mandate carrying a
transaction the user never authorised, achieved by prompt-injecting the agent
while it was assembling the cart. Every credential checked out. The decision was
already compromised.

The consequence is the design's founding constraint:

**A submission that contains only signed artifacts is structurally incapable of
revealing this class of failure, however good the reviewing agent is.** You
cannot reason your way to a finding when the evidence containing it was never
filed. This is why the data contract (document 03) is as important as the
detection logic — it is the part that makes detection *possible at all*.

## 4 · What goes wrong when nobody is checking

Left unsupervised, agents fail in ways that map to real regulatory harm:

- **Drifting outside budget or purpose** — the agent buys something the shopper
  did not ask for, or spends beyond what was authorised.
- **Paying unauthorised counterparties** — money reaches an entity nobody
  verified, sometimes through a marketplace that hides the real seller.
- **Structuring** — payments split under reporting thresholds, which no single
  transaction reveals.
- **Manipulation** — the agent obeys an instruction hidden in a product page, a
  tool result, or a merchant's returns policy.
- **Slow behavioural drift** — nothing is wrong on any given day, and the agent
  is a different agent by the end of the quarter.
- **Accountability evaporating** — the delegation chain never reaches a human,
  so when a loss occurs there is nobody to hold responsible.

That last one is the whole reason "Know Your Agent" exists. **An AI agent has no
legal identity.** It cannot be fined, sued, struck off, or called to a hearing.
If authority does not trace back to a human or a legally liable entity, the
consumer absorbs the loss by default.

## 5 · Who bears the cost

| Party | Exposure |
|---|---|
| **Consumers** | Bear the loss directly when an agent acts outside its mandate, with no liable counterparty |
| **Firms** | Carry fraud risk on transactions they often cannot fully inspect |
| **Markets** | Exposed to correlated agent behaviour that a firm-by-firm review is structurally unlikely to catch |

The third line is worth pausing on: it is the one advantage a central bank has
that no vendor has — **seeing every supervised firm at once.** A single firm
cannot tell that the merchant it just started paying is also being paid, in the
same week, by three other firms' agents. A supervisor can. This is why the
system has a portfolio layer (document 07, agent E2).

## 6 · Why this is a real regulatory regime, not an invented one

The most common objection is: *"regulators don't approve algorithms."* They do,
and they have for years.

| Precedent | What it already requires |
|---|---|
| **MiFID II RTS 6** | Investment firms must test algorithms in a non-live environment before deployment, self-certify the result, and retain records the regulator can demand. **The closest analogue in existence: an algorithm that moves money, tested before it is allowed to.** |
| **EMV / PCI PTS** | Defined test suites, run by the vendor, results submitted for approval. Payments already certifies by testing. |
| **EU AI Act** | Conformity assessment before a system is placed on the market. |
| **SR 11-7 / ECB TRIM** | Supervisors review the *validation itself*, not just the policy the firm filed about it. |

So the claim is deliberately modest:

> We did not invent agent approval. **Payments already approves things by
> testing them. Nobody has said what the test looks like for an AI payment
> agent.** This is that test, specified and built.

There is also a national anchor. Supervision of conventional AI and machine
learning models is uneven everywhere; most authorities stop at a policy check.
The National Bank of Georgia is one of the few that goes further, performing
full technical validation before a model is deployed. Extending that posture to
agentic payments is a natural continuation, not a leap.

## 7 · Why the *institution* submits, not the operator

Agent operators are not regulated entities in any jurisdiction. An obligation
has to attach to someone inside the supervisory perimeter, so it attaches to the
bank or PSP that sponsors the agent:

```
NBG ──authorises the agent──▶ Institution (bank / PSP)   ← regulated. SUBMITS.
                                    │ sponsors
                                    ▼
                              Operator (not regulated)
                                    └── Agent  ← the subject of the decision
```

The obvious follow-up is: *how does the institution obtain run-level data it
does not natively hold?* Through its own API, as a **commercial condition of
the agentic-checkout product** — the PSP requires the run record in order to
process the payment. This is exactly how PSP onboarding conditions already
work. The data exists because the product demands it, not because a regulator
wished for it.

## 8 · What a regulator actually needs

Two things, and the product does both:

1. **A place to set and test the rules before publishing them** — because
   nobody knows yet whether a credential older than 730 days should be a breach
   or 365, and shipping an untested threshold into supervision is how
   supervision loses credibility. → the **policy sandbox** (document 12).

2. **A way to supervise agents against those rules using the evidence agents
   actually generate** — the batch run and transaction record — rather than
   inferring behaviour from a policy document filed once a year. → the
   **review pipeline** (documents 07–10).

Everything else in this system is in service of those two sentences.
