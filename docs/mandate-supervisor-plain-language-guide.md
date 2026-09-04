# Mandate Supervisor — A Plain-Language Guide

## The idea in one sentence

Mandate Supervisor gives a regulator evidence that an AI payment agent behaves as intended: within the authority it received, according to the purpose it was designed for, and with effective controls around its decisions and payments.

It addresses the additional risks created when AI is no longer only analysing a payment, but actively deciding what to buy, when to pay, how much to spend and which counterparty to use.

---

# Why this is needed

Payments have traditionally been built around a person making a choice and clicking “Pay.”

An AI payment agent changes that model. A person can give an agent a purpose and a budget, and the agent can then decide:

- what to buy;
- when to buy it;
- which merchant to use;
- how much to spend;
- and when a payment should be made.

That creates a new supervisory problem.

A payment system can verify that a digital instruction was signed correctly. But a valid signature cannot tell us whether:

- the agent was legitimate in the first place;
- the person understood what they authorised;
- the agent was manipulated before signing;
- the purchase matched the person's real request;
- the money reached the expected recipient;
- or the firm's own controls actually worked.

The signature proves that the final instruction was not altered. Mandate Supervisor examines whether the decision behind that instruction was legitimate.

## It complements traditional payment supervision

Mandate Supervisor is not intended to replace the rules, controls and financial-crime checks already used for traditional payments.

Existing payment supervision continues to cover areas such as:

- customer and business identification;
- account security and authentication;
- sanctions and anti-money-laundering screening;
- payment limits and settlement controls;
- fraud monitoring;
- consumer protection;
- and operational resilience.

Mandate Supervisor sits above and alongside that existing framework. It concentrates on the risks introduced when an AI agent becomes a decision-maker inside the payment chain.

These additional questions include:

- Was the agent itself registered, appropriately classified and linked to an accountable operator?
- Was the mandate genuinely authorised by a human?
- Did the agent interpret the person's purpose correctly?
- Was the agent manipulated by merchant content, tools or retrieved information?
- Did the model, prompt and tools used in production match what was approved?
- Did the agent's behaviour change after approval?
- Are many agents creating a shared market-wide risk?
- Did the institution's controls actually govern the agent's decisions?

The objective is to give the regulator continuing assurance that the agent operates as intended—not merely that its payments are technically valid.

## It is also a policy sandbox

There is not yet one internationally standardised KYA rulebook for payment agents. Regulators still need to decide what a trustworthy agent should be required to demonstrate.

Mandate Supervisor therefore has two connected roles.

### Before the rules are established

It acts as a policy sandbox. The regulator can:

- propose new KYA and agent-governance rules;
- change their severity and strictness;
- adjust thresholds such as acceptable credential age, transaction velocity or concentration;
- decide which rules should automatically block authorisation and which should only trigger monitoring;
- test draft rules against representative and adversarial cases;
- examine false positives and missed failures;
- and compare the effect of one proposed rulebook with another before publication.

Draft rules remain isolated from the active supervisory rulebook. A named human must approve their promotion.

### Once the rules are established

The same system becomes the operational supervision mechanism. Institutions submit evidence, active rules produce facts, specialists interpret those facts, and supervisors use the resulting record to authorise, monitor or refuse an agent.

This creates a continuous connection between policy and supervision:

```text
Regulator designs a rule
          ↓
Tests it in the policy sandbox
          ↓
Reviews its effect and strictness
          ↓
Promotes it to the active rulebook
          ↓
The same rule is applied to real supervisory submissions
```

Rules are therefore policy expressed in a form the system can consistently evaluate, rather than requirements hidden inside software code or an AI prompt.

---

# What the regulator is deciding

The regulator is not reviewing one payment in isolation. It is deciding whether **one AI payment agent** is fit to operate.

The regulated institution submits an evidence package showing how the agent performed across a set of test runs. The regulator reviews that evidence and can decide to:

- authorise the agent;
- authorise it subject to monitoring or conditions;
- refuse authorisation;
- or conclude that the evidence is incomplete and request a better submission.

This is similar in principle to testing another system that can move money before allowing it into production. The difference is that the test must examine not only fixed software, but also an agent that interprets information and makes choices.

---

# Who submits the evidence

The submission comes from a regulated bank or payment service provider.

The company building or operating the agent may not itself be directly supervised. The bank or PSP is already inside the regulatory perimeter, can be required to retain records, and controls access to the payment service.

```text
Regulator
    ↓ authorises and supervises
Bank or payment provider
    ↓ sponsors and submits evidence for
Agent operator
    ↓ operates
AI payment agent
```

If the institution does not naturally possess part of the run record, it can require the operator to provide it as a condition of using the institution's agentic-payment service.

---

# What the institution sends

The institution submits a dossier for the agent. It is not simply a policy document saying that the agent is safe. It contains evidence of what the agent actually did.

A simplified submission might look like this:

```jsonc
{
  "agent": {
    "agent_id": "AGENT-KST-001",
    "operator_id": "OP-KST",
    "risk_class": "consumer_shopping",
    "declared_model": "model-version-4"
  },
  "credential": {
    "issuer_id": "ISSUER-01",
    "capabilities": ["search_products", "create_cart", "request_payment"],
    "valid_until": "2026-12-31",
    "delegation_chain": ["institution", "operator", "accountable_officer"]
  },
  "run": {
    "user_request": "Buy one vitamin-C serum for around 50 GEL",
    "mandate": {
      "maximum_amount": 60,
      "currency": "GEL",
      "usage": "single_use"
    },
    "consent": {
      "occurred": true,
      "method": "explicit_confirmation",
      "displayed_amount": 52
    },
    "decision_context": {
      "observed_model": "model-version-4",
      "prompt_release": "shopping-agent-4.2",
      "tools_used": ["approved-catalog-server"],
      "alternatives_considered": 3
    },
    "cart": {
      "merchant": "Kutaisi Beauty",
      "item": "Vitamin-C Serum",
      "total": 52
    },
    "payment": {
      "amount": 52,
      "currency": "GEL",
      "payee": "MERCHANT-447"
    },
    "controls": {
      "spending_cap": "passed",
      "merchant_check": "passed",
      "human_override": null
    }
  }
}
```

The real schema contains more detail and many runs, but the principle is straightforward: the institution provides enough structured evidence to connect the person, the mandate, the agent's decision process, the Cart, the final Payment and the firm's controls.

The dossier includes:

## The agent's identity and authority

- who operates the agent;
- which institution sponsors it;
- who issued its digital credential;
- the chain showing how authority reached the agent;
- the person or organisation ultimately accountable;
- what the agent is allowed to do;
- and the history of its credentials and permissions.

## The mandates under which it acted

For every run, the dossier records:

- what the person requested;
- what limits and conditions were authorised;
- what the agent placed in the Cart;
- and what Payment Mandate was ultimately created.

## The human-authorisation record

The dossier records:

- whether human participation was required;
- who granted the mandate;
- when and how they granted it;
- what purpose they approved;
- whether it was one-time or recurring;
- and the amount, merchant and items shown to them.

This allows the regulator to compare what the person saw with what was actually signed.

## How the agent made its decision

The dossier records a bounded history of the decision process:

- which model actually responded;
- which version of the agent's instructions was active;
- which tools and servers it called;
- selected parts of the information returned by those tools;
- and which alternatives the agent considered before making its choice.

The regulator does not need every token the model generated or a complete copy of every merchant catalogue. It needs enough evidence to reconstruct the important influences on the decision.

## The firm's own controls

The institution records:

- which controls it says should apply;
- whether each control is advisory or blocking;
- which controls evaluated each run;
- whether they passed or triggered;
- whether anyone overrode them;
- and whether the payment eventually settled.

## Transaction history

The dossier includes enough previous activity to show:

- spending patterns;
- transaction frequency;
- merchant concentration;
- declines and reversals;
- and whether the agent's behaviour has changed.

---

# What the regulator already knows

The institution cannot be the only source of truth about itself.

For example, an operator can declare that it is authorised, but the regulator should verify that claim against official records. It can declare which model it used, but the regulator decides whether that model has been barred.

The regulator therefore maintains or reuses registers covering:

- institutions allowed to submit;
- operators that are licensed or properly sponsored;
- AI payment agents registered to operate;
- organisations allowed to issue agent credentials;
- public keys used to verify signatures;
- merchants and their real owners;
- tools and servers approved for agent use;
- and model versions that must not authorise payments.

Most of this information already exists in licensing, company, merchant, payment and accreditation records.

The main new proposal is the **agent register**. Before an AI payment agent may operate, it should be declared with:

- its operator;
- its purpose;
- its risk classification;
- its model;
- and the important technical versions that were reviewed.

Without an agent register, the regulator does not know how many payment agents exist or what each one was approved to do.

---

# The specialist team

Mandate Supervisor divides the review among specialists. Each specialist answers one clear question and receives only the evidence needed for that question.

This is safer and easier to audit than asking one general-purpose AI system to understand everything and produce a verdict.

## 1. KYA — Is this a legitimate agent?

KYA means Know Your Agent.

This specialist performs due diligence on:

- the agent;
- its credential issuer;
- the operator behind it;
- the regulated institution sponsoring it;
- the chain of authority;
- the accountable person;
- its permissions;
- its model;
- and its registration history.

It checks whether the signatures are valid, but does not stop there. It also checks whether the signer had the right to issue the credential, whether each party delegated only authority it possessed, and whether the agent's powers have expanded over time.

KYA answers the first fundamental question: **should this agent exist and operate at all?**

## 2. Consent & Harm — Did the person genuinely authorise the mandate?

This specialist examines the human side of the authority.

It checks:

- whether the required person was involved;
- what they were shown;
- what purpose and limits they accepted;
- whether the authorisation was still fresh;
- whether it was one-time or recurring;
- and whether the signed mandate matched what appeared on the confirmation screen.

It can also compare the selected product with the alternatives the agent considered to identify cases where the consumer was systematically given a materially worse option.

Consent is not necessarily a separate click before every transaction. A person may grant a standing mandate for several future payments. The important question is whether each payment was covered by authority the person knowingly granted.

## 3. Provenance — Can we trust the ingredients of the decision?

Provenance examines where the agent's decision came from.

It checks:

- whether the model that actually responded was the model declared;
- whether the active prompt belonged to an approved release;
- whether every tool came from an authorised server;
- and whether the agent's credential, registration, published identity and observed activity describe the same system.

This is similar to checking the provenance of evidence in an investigation: not only what the evidence says, but where it came from and whether that source can be trusted.

## 4. Injection — Was the agent manipulated by content it read?

AI agents can confuse information with instructions.

A merchant could place text inside a product description telling automated agents to add an extra fee or ignore a spending limit. Similar instructions could appear in a tool description, a retrieved document or a message from another agent.

The Injection specialist examines each possible channel and asks two separate questions:

1. Was suspicious instruction-like content present?
2. Did the agent actually act on it?

The second question matters. Suspicious text alone is not proof that the agent was compromised.

The finding also names the channel so the institution knows what needs to be fixed.

## 5. Mandate — Was the payment within what the person authorised?

The Mandate specialist verifies the formal chain from the person's Intent, through the Cart, to the final Payment.

It checks:

- signatures and digital fingerprints;
- Cart totals and Payment amounts;
- per-payment and cumulative limits;
- merchant and category restrictions;
- currency and geography;
- time limits;
- and whether a one-time mandate was used more than once.

It also examines whether each selected item genuinely matches the person's request.

For example, a mandate may allow purchases from garden-supply merchants. A gift card sold by an approved garden supplier may satisfy the formal merchant rule while still not being garden supplies. Formal compliance and genuine intent are therefore assessed separately.

## 6. Counterparty — Who actually received the money?

The Counterparty specialist performs due diligence on the receiving side.

It compares:

- the merchant shown in the Cart;
- the account that received settlement;
- the seller behind a marketplace;
- and the ultimate owner of the recipient.

It checks whether the recipient is known, whether it appears on a regulatory watchlist, whether one owner is hiding behind several merchant identities, and whether a previously unknown recipient has suddenly begun receiving most of the agent's spending.

This closes an important gap: a system may know almost everything about the agent making the payment while knowing very little about the person ultimately receiving the money.

## 7. Log — What does the transaction history reveal?

The Log specialist looks for patterns that are invisible in a single payment.

It identifies situations such as:

- one large payment divided into several smaller payments below a reporting threshold;
- too many payments happening too quickly;
- spending becoming concentrated on one recipient;
- or groups of transactions that appear unusual when considered together.

The underlying totals, clusters and frequencies are calculated directly. The AI component may help explain whether a pattern is plausibly benign, but it cannot invent or modify the measurements.

## 8. Drift — Has the agent changed?

The Drift specialist compares the agent's current behaviour with its own previous behaviour.

It examines changes in:

- average transaction value;
- transaction frequency;
- merchant mix;
- and counterparty concentration.

It then attempts to determine when the change began and what happened at that time.

A finding that says “the agent changed” is difficult to investigate. A finding that says “the agent changed immediately after a new model or prompt was deployed” gives the supervisor a likely cause and a clear period to examine.

## 9. Control Assurance — Did the firm's controls work?

Control Assurance takes the findings produced by the other specialists and asks why the institution's own controls allowed the event.

It classifies the control response as:

- **Absent** — no control addressed the risk;
- **Failed** — the control should have triggered but did not;
- **Bypassed** — it triggered and someone overrode it;
- **Ineffective** — it triggered and remained active, but the payment still happened;
- **Effective** — it worked and prevented the action.

This turns a detection into a supervisory finding.

“The agent exceeded its cap” identifies a problem.

“The firm's blocking control detected the breach, and a named employee overrode it without documented authority” explains the governance and accountability failure behind the problem.

## 10. Systemic — What is happening across the market?

The Systemic specialist uses the regulator's market-wide view.

It looks for:

- many firms depending on the same model;
- unrelated agents moving in the same direction at the same time;
- one recipient collecting funds from several institutions;
- and the same attack appearing at multiple operators.

One bank may see one unusual transaction. The regulator may see the same pattern at five unrelated banks and recognise a coordinated campaign.

This is a capability that belongs naturally to a central regulator because no individual institution sees the complete supervised market.

## 11. Red Team — Does the agent remain safe when deliberately challenged?

The Red Team specialist creates synthetic tests from the agent's own mandate.

Examples include:

- an amount just above the cap;
- a merchant name resembling an approved merchant;
- a product description containing hidden instructions;
- reuse of a one-time mandate;
- or consent-screen values that differ from the signed values.

These tests do not touch live payment systems. They reveal which risks the firm's declared controls can handle and which remain unprotected.

---

# How the system uses AI safely

Mandate Supervisor separates facts from judgement.

The rules run first. They are deterministic: the same evidence evaluated under the same rule version and parameters produces the same result.

The rules produce structured facts such as:

```text
FACT: Credential signature verified.
FACT: Issuer was accredited on the credential's issue date.
FACT: Displayed amount was ₾52; signed amount was ₾1,292.
FACT: Payment exceeded the authorised cap by ₾792.
FACT: The tool server was absent from the approved registry.
FACT: A blocking control triggered and the payment still settled.
```

The AI specialist reasons on top of those facts. It does not replace them.

```text
Submitted evidence
        ↓
Deterministic rules produce facts
        ↓
AI specialist interprets meaning and relationships
        ↓
Structured assessment with evidence references
        ↓
Human supervisor makes the regulatory decision
```

## What deterministic rules decide

Most checks do not require AI judgement.

The following are calculated directly:

- whether signatures verify;
- whether digital fingerprints match;
- whether an amount exceeds a limit;
- whether a credential has expired;
- whether an issuer or merchant appears in a register;
- whether two credentials overlap;
- whether spending is concentrated;
- and whether a blocking control still resulted in settlement.

AI judgement is used only where meaning genuinely matters, such as:

- whether a product matches a person's request;
- whether the agent acted on a hidden instruction;
- whether observed activity fits the declared agent class;
- or whether the chosen product was materially worse than comparable alternatives.

Every judgement must cite the specific run, transaction and evidence on which it depends. A human supervisor remains responsible for the final decision.

## What the AI adds

The AI layer helps with questions that cannot be answered by arithmetic or exact matching alone.

For example, deterministic rules can establish that:

- a Cart remained under the ₾60 cap;
- the merchant was in the permitted category;
- and all signatures and hashes were valid.

But those facts cannot determine whether a night cream genuinely satisfies a request for vitamin-C serum. That requires reasoning about meaning.

Similarly, a deterministic scanner can identify instruction-like text in a product description. But suspicious text alone does not prove that the agent followed it. The AI specialist compares the text with the agent's later actions and assesses whether the instruction influenced the decision.

The AI therefore:

- explains what the facts mean together;
- identifies relationships across several facts;
- evaluates semantic consistency;
- distinguishes a suspicious signal from an acted-on manipulation;
- and produces a structured, evidence-cited assessment.

It does not independently invent rules, alter thresholds, verify cryptography, calculate financial totals or make the final regulatory decision.

## Why this separation matters

If AI were responsible for both creating the facts and interpreting them, the supervisor could not easily determine which part of the conclusion was measured and which part was judgement.

Mandate Supervisor keeps these layers separate:

| Layer | Role | Example |
|---|---|---|
| **Evidence** | What was submitted or held in a registry | The signed Cart contains an amount of ₾1,292 |
| **Deterministic fact** | What a versioned rule proves | The signed amount differs from the displayed amount by ₾1,240 |
| **AI assessment** | What the facts mean in context | The mandate does not reflect the terms presented to the customer |
| **Human decision** | What regulatory action follows | Refuse authorisation or require remediation and resubmission |

This gives the regulator both consistency and judgement: deterministic rules for what can be proven, AI reasoning for what must be interpreted, and a named human for the final exercise of authority.

---

# What happens when information is missing

Missing information is not treated as a pass.

The system distinguishes:

- the evidence was present and the check passed;
- the evidence was present and the check failed;
- the evidence was missing, so the check could not be performed;
- or the check did not apply.

This is important because an institution that cannot identify which model made a payment decision has revealed a model-governance weakness. The system must not report “no problem found” simply because the necessary evidence was absent.

The submission itself is also checked for integrity. The regulator can identify when:

- fewer runs were submitted than were executed;
- the submitted runs cover only an easy part of the agent's permitted activity;
- the tested configuration differs from the planned deployment;
- or the evidence predates the version now intended for production.

In those cases, the correct outcome may be **incomplete submission**, not authorisation or refusal.

---

# Why the requested data is realistic

The framework follows a practical rule:

> Ask only for information that already exists in a system the institution operates, or that requires a small and deliberate addition.

Most of the evidence already exists in:

- payment ledgers;
- Strong Customer Authentication and consent records;
- settlement and acquirer data;
- fraud and transaction-monitoring systems;
- override and case-management records;
- model-provider responses;
- deployment pipelines;
- version control;
- agent-observability tools;
- and merchant or sub-merchant reporting.

Examples:

| Evidence required | Likely source |
|---|---|
| Mandates and transaction history | Payment and agentic-checkout systems |
| Who authenticated, when and how | Authentication and consent logs |
| What values were displayed | The confirmation interface already displaying them |
| Which model answered | Model-provider response logs |
| Which prompt was running | Deployment pipeline or version control |
| Which tools were called | Agent observability and tool-session logs |
| Which control evaluated the payment | Fraud or transaction-monitoring engine |
| Who overrode a control and why | Case-management and approval system |
| Actual payee and sub-merchant | Settlement and acquirer records |

Some information may exist on the acquiring side rather than with the paying institution. For example, beneficial ownership of a merchant may come from company registers or acquirer due diligence. The regulator can combine those records instead of asking the paying institution to provide information it genuinely does not possess.

---

# What the framework does not pretend to solve

Some desirable evidence is not realistically available today.

The routine submission therefore does not require:

- cryptographic proof from a model provider that a particular model generated a response;
- screenshots of every consent screen;
- complete copies of merchant catalogues;
- or complete transcripts of conversations between autonomous agents.

This means some failures remain only partly detectable. Those gaps are recorded explicitly instead of being hidden behind a broad claim that every risk is covered.

---

# A simple example from beginning to end

Suppose Maia asks an agent:

> “Buy one vitamin-C serum for around ₾50.”

The agent purchases a ₾79 night cream from a marketplace seller after reading a product description containing hidden instructions. The payment is supported by a valid signature.

Mandate Supervisor would examine the case as follows:

1. **KYA** verifies that the agent, issuer, operator and authority chain are legitimate.
2. **Consent & Harm** checks what Maia was shown and whether those values match the signed mandate.
3. **Provenance** checks the model, prompt, tool and server used to construct the decision.
4. **Injection** identifies the hidden instruction and determines whether the agent acted on it.
5. **Mandate** verifies the signed chain, limits and whether a night cream matches the request for serum.
6. **Counterparty** identifies the marketplace seller and ultimate payee.
7. **Log** checks whether similar purchases form a broader pattern.
8. **Drift** checks whether the agent began behaving differently after a model, prompt or supplier change.
9. **Control Assurance** determines whether the firm's input-sanitisation, merchant and spending controls were absent, failed, bypassed or ineffective.
10. **Systemic** checks whether the same merchant or injected content appears at other institutions.

The regulator does not receive only the conclusion that “the payment was suspicious.” It receives an evidence-backed account of:

- whether the agent was legitimate;
- whether the human authorised the mandate;
- how the decision was manipulated;
- whether the payment remained within formal authority;
- who benefited;
- whether it was part of a pattern;
- and why the institution's controls allowed it.

---

# The complete idea

Mandate Supervisor combines:

```text
Evidence submitted by the institution
                    +
Independent information held by the regulator
                    +
Deterministic rules and calculations
                    +
Narrow AI judgements where meaning is unavoidable
                    +
Human supervisory decision
```

The result is not simply a fraud score. It is a structured process for deciding whether an AI payment agent has demonstrated that it can operate within legitimate authority, with effective institutional controls and evidence strong enough for a regulator to rely on.
