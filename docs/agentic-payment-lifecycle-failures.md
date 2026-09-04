# Agentic Payment Lifecycle — Failure Guide

## Purpose

An agentic payment is not just the moment money moves. It is a lifecycle: an agent is created, receives authority, makes a decision, creates a signed mandate, pays a counterparty, repeats that activity over time, and eventually becomes part of a wider market of agents.

Failures can occur at every phase. A valid signature protects the integrity of a signed object, but it does not prove that the decision producing that object was legitimate.

This guide explains the main failures that may occur in each phase of an agentic payment. It follows the canonical 73-failure model used by Mandate Supervisor.

---

## Lifecycle overview

| Phase | Supervisory question | Primary area |
|---|---|---|
| **P0 — Agent creation** | Is this a legitimate agent with valid authority? | Agent due diligence and KYA |
| **P1 — Human authorisation** | Did a human knowingly authorise the mandate? | Consent and consumer protection |
| **P2 — Decision construction** | Can the process that produced the decision be trusted? | Provenance and manipulation |
| **P3 — Mandate signing** | Is the signed payment within the authority granted? | Mandate integrity and scope |
| **P4 — Payment execution** | Who actually received the money? | Counterparty and financial-crime risk |
| **P5 — Accumulated activity** | What does the agent's behaviour reveal over time? | Transaction patterns and drift |
| **P6 — Market activity** | What risks emerge across many agents and firms? | Systemic supervision |
| **X1 — Firm controls** | Why did the firm's controls allow the problem? | Control assurance and accountability |

---

# P0 — The agent comes into existence

## What this phase does

P0 is due diligence for the agent itself. Before examining any payment, the regulator establishes what the agent is, who created and operates it, who accepts legal responsibility for it, what authority it received, and which model and tools it uses.

The regulator also performs due diligence on the surrounding trust chain: the credential issuer, sponsoring institution, operator, accountable officers, delegation chain, technical configuration and credential history.

A valid signature proves that a key signed a credential. It does not prove that the key belonged to an authorised issuer or that the issuer had the right to create this kind of payment agent.

## Failures that may occur

### Credential issuer failures

- The credential issuer was never accredited.
- The issuer's accreditation was revoked before the credential was issued.
- The issuer's trust level is insufficient for the value or risk of the agent.
- The issuer has not been reassessed within the required period.
- The issuer is not accredited for the agent's declared classification.
- The credential contains impossible or inconsistent dates.

### Accountability and delegation failures

- The authority chain does not reach an accountable human or legally liable entity.
- One or more delegation signatures are forged or invalid.
- The same entity appears multiple times in the chain, creating artificial layers of oversight.
- The delegation chain is excessively deep, weakening accountability.
- An intermediary grants more authority than it received.
- The accountable party and the person granting the specific mandate are incorrectly treated as the same role.
- The final accountable person is not authorised to act for the operator.

### Operator failures

- The operator is neither licensed nor sponsored by a regulated institution.
- The operator's licence or sponsorship has expired.
- The operator is under enforcement restrictions or winding down.
- The operator changed ownership after approval without reassessment.
- No named compliance contact is available.

### Agent-registration failures

- The agent was never registered with the regulator.
- The agent began operating before registration.
- The agent has no declared risk classification.
- Its observed activity does not match its declared classification.
- The registration is expired or no longer current.
- The registered purpose does not match the purpose for which the agent is being used.

### Technical-governance failures

- No model version is declared.
- The model used in practice differs from the registered or tested model.
- The model is on a regulatory blocklist.
- No validation evidence exists for the deployed configuration.
- The running prompt is not connected to an approved release.
- The agent uses tools or servers that were not declared or authorised.

### Credential-lifecycle failures

- Successive credential renewals quietly expand the agent's capabilities.
- Two credentials for the same agent are valid at the same time.
- Two supposedly different agents use the same signing key.
- The same credential identifier is used by multiple agents.
- Revocation status was not checked recently enough.

## Why this phase matters

An agent can make perfectly compliant payments and still be illegitimate because the operator, issuer or authority chain was never valid. P0 determines whether the agent had a legitimate right to operate before judging what it did.

---

# P1 — A human authorises the mandate

## What this phase does

P1 is due diligence on human authorisation. It determines whether the mandate under which the agent acted was genuinely and knowingly authorised.

Consent applies to the mandate, not necessarily to every later transaction:

```text
Human gives consent
        ↓
Consent authorises a mandate
        ↓
Agent acts within that mandate
        ↓
Payment transaction executes
```

In a human-present purchase, the person may approve the exact cart and price. Under a standing mandate, the person may authorise several future transactions within defined limits without approving each one individually.

The signed mandate proves what was signed. A consent-ceremony record proves what the human was shown, how they agreed, and whether those displayed terms matched the signed terms.

## Failures that may occur

- The mandate required human participation, but there is no evidence that it occurred.
- The person who granted the mandate cannot be identified.
- The consent was too old for the circumstances in which it was used.
- The agent used the mandate for a purpose the person did not authorise.
- The consent method was weaker than the risk required.
- Consent was implied, bundled into general terms or inferred from silence where explicit approval was required.
- The interface used manipulative design, such as preselected options, hidden conditions or artificial urgency.
- The human was shown one amount, merchant, basket or limit, while different values were signed.
- A one-time mandate was treated as recurring or standing authority.
- Recurring authority continued without renewal or required re-consent.
- A new consent failed to supersede the previous consent correctly.
- There is no consent-ceremony record at all.
- A payment was executed without being covered by any valid mandate.

## Why this phase matters

The clearest failure is rendered-versus-signed substitution. A customer may see a ₾52 purchase while the system signs a ₾1,292 mandate. The signature can remain completely valid because it protects the substituted values. Detecting the problem requires comparing what the person saw with what was actually signed.

---

# P2 — The agent constructs the decision

## What this phase does

P2 is due diligence on the agent's decision-making process. The agent is interpreting the user's request, reading content, calling tools, retrieving information, comparing alternatives and selecting what to buy.

This is the largest blind spot in conventional payment controls because it happens before the final mandate is signed. A manipulated process can produce a technically perfect signed mandate.

The relevant evidence includes the model that actually responded, approved prompt release, tools and servers used, tool definitions, limited tool results, information sources and alternatives considered.

## Failures that may occur

### Injection and untrusted-content failures

- A merchant hides instructions inside a product description.
- A tool description contains instructions intended to manipulate the agent.
- Retrieved reference material contains adversarial instructions.
- An internal supplier list, policy document, catalogue or stored memory is poisoned.
- Another agent socially engineers the purchasing agent.
- The system detects suspicious text but cannot determine whether the agent acted on it.
- The source channel of the manipulation cannot be identified.

### Tool and infrastructure failures

- A malicious tool uses the same name as a trusted tool.
- The agent calls a legitimate tool name on an unauthorised server.
- Tool name resolution directs the agent to the wrong implementation.
- The tool schema changes without approval.
- An unknown third party supplies prices, merchant identity or availability data.
- The agent is directed to a false merchant endpoint.
- The counterparty's machine-readable identity claim cannot be verified.

### Model and prompt failures

- The system prompt is modified outside the approved release process.
- The prompt running in production differs from the reviewed prompt.
- A different model version makes the decision from the one declared.
- A fallback model is used without approval or disclosure.
- The agent's declared technical configuration differs from the deployed configuration.

### Decision-quality failures

- The agent's underlying objective is redirected while the visible task appears unchanged.
- One poisoned input contaminates the remaining steps of a multi-step run.
- Each individual reasoning step appears valid while the overall session rests on a false premise.
- The agent systematically favours an affiliated or preferred merchant.
- The agent chooses a materially worse or more expensive option despite comparable alternatives.
- The alternatives considered are not recorded, making bias or poor value impossible to assess.

## Why this phase matters

Signatures protect the output of the decision process. P2 examines the process that produced that output. Without construction evidence, a regulator cannot distinguish a safe decision from a manipulated decision that happens to result in a valid signature.

---

# P3 — The mandate is signed

## What this phase does

P3 verifies the formal mandate chain from the human's Intent, through the Cart, to the final Payment. It checks cryptographic integrity, financial limits, scope restrictions, validity periods and mandate usage.

Most checks in this phase are deterministic. A narrow semantic assessment is needed only where formal compliance may still conflict with the person's actual meaning.

## Failures that may occur

### Mandate-chain failures

- The Cart does not match the Intent it claims to descend from.
- The Payment does not match the Cart it claims to descend from.
- A referenced hash or fingerprint does not recompute.
- The chain between human authority, selected items and payment is broken.

### Amount and limit failures

- The payment amount does not match the Cart total.
- The order exceeds the maximum per-transaction amount.
- Several individually compliant payments exceed a cumulative limit.
- The wrong accumulation period or mandate semantics are used.
- The system counts unrelated transactions against the mandate.

### Scope failures

- The merchant category is outside the authorised scope.
- The payment goes to a counterparty not approved by the mandate.
- The payment uses an unauthorised currency.
- The merchant is in an excluded geographic region.
- The payment occurs before the mandate starts or after it expires.
- The selected goods or services do not match the authorised purpose.

### Usage and replay failures

- A single-use mandate is used for more than one payment.
- The system does not record that the mandate has already been consumed.
- A recurring mandate is applied outside its recurrence conditions.

### Intent-fidelity failures

- The purchase follows the literal rules but not the person's intended meaning.
- An approved merchant sells an item unrelated to the request.
- A broad merchant category is used to justify an inappropriate product.
- A whole-cart verdict hides one problematic line item.

## Why this phase matters

P3 is the phase where signatures and deterministic verification are most useful. However, rules only approximate intent. A gift card from an approved garden supplier may satisfy the merchant and amount rules while still not being garden supplies. Mechanical validity and intent fidelity must therefore remain separate assessments.

---

# P4 — The payment executes against a counterparty

## What this phase does

P4 is due diligence on the receiving side of the payment. It determines who actually received the money and whether that party is who it claims to be.

The merchant displayed in a Cart, the platform processing the sale, the settlement payee and the ultimate beneficial owner may be different entities. This phase reconciles those identities.

## Failures that may occur

- The receiving account cannot be connected to a known legal entity.
- The payment records a reputable marketplace but not the actual sub-merchant.
- A risky seller hides behind the identity and reputation of a platform.
- Funds are sent to an agent-controlled wallet with no identifiable beneficial owner.
- The recipient appears on a sanctions, PEP, adverse-media or other regulatory watchlist.
- A newly created or previously unseen recipient immediately receives a large share of spending.
- One beneficial owner receives money through multiple merchant identities.
- Multiple payee identifiers are used to evade concentration controls.
- The merchant in the Cart differs from the settlement payee without a valid explanation.
- Several unrelated firms begin paying the same recipient.
- Payment declines, failures or reversals cluster in a pattern suggesting probing.
- Repeated failed attempts are followed by a successful payment.

## Why this phase matters

Agentic-payment controls may establish the payer's identity, authority and mandate in detail while knowing very little about the payee. P4 closes this asymmetry by examining the party that receives the value—the side most relevant to financial-crime and beneficial-ownership risk.

---

# P5 — Payments accumulate into behaviour

## What this phase does

P5 is ongoing behavioural supervision. It stops treating payments as isolated events and evaluates the agent as a process that acts repeatedly, continuously and at machine speed.

Some failures have no single invalid transaction. They exist only in timing, sequence, cumulative value, concentration or change from the agent's previous behaviour.

## Failures that may occur

### Transaction-pattern failures

- A large obligation is split into smaller payments below a reporting threshold.
- Transactions occur at a speed that prevents meaningful human intervention.
- Spending becomes excessively concentrated on one recipient.
- A new recipient rapidly becomes dominant.
- Payments repeatedly use suspiciously round amounts.
- Activity moves into hours inconsistent with the agent's established pattern.
- Transaction amounts steadily approach the agent's maximum limit.
- Many small payments collectively create excessive or runaway spending.

### Behavioural-drift failures

- Average transaction value changes materially.
- Transaction frequency changes materially.
- Counterparty or merchant-category mix changes materially.
- The agent no longer behaves like the system originally assessed.
- No single payment breaches a rule, but the aggregate behaviour is inconsistent with approval.
- Drift is detected without identifying when it began.
- A model, prompt, credential, tool, control or supplier change occurs at the drift boundary.
- Persistent corruption or memory poisoning appears externally as behavioural drift.

### Supervisory-capacity failures

- The agent generates an excessive number of low-quality alerts.
- Reviewers become overwhelmed by false positives or repetitive findings.
- A serious event is hidden inside alert noise.
- The same underlying event is reported multiple times by different rules or specialists.

## Why this phase matters

One payment may be defensible while the sequence is clearly unsafe. P5 detects patterns that transaction-by-transaction review cannot see and connects behavioural changes to the system event that may have caused them.

---

# P6 — Many agents act across the market

## What this phase does

P6 is systemic surveillance for agentic payments. It examines what many independently operated agents are doing across firms, sectors and the wider market.

An individual institution sees only its own agents and transactions. A regulator can compare the whole supervised population and identify risks that emerge only at portfolio level.

## Failures that may occur

- A large share of the market relies on the same model version.
- One model weakness or outage could affect many institutions simultaneously.
- Agents at unrelated firms begin acting in unusually similar ways.
- Independent agents transact with suspiciously synchronised timing.
- A whole sector's agents drift in the same direction.
- Similar models amplify the same market signal at machine speed.
- One recipient collects significant funds from several unrelated operators.
- The same injection payload appears at multiple firms.
- Structurally identical malicious Carts appear across operators.
- A shared tool, model, data source or supplier creates a common point of failure.
- Several incidents are incorrectly handled as unrelated firm-level events instead of one campaign.
- A systemic exposure is incorrectly attributed as misconduct by one institution.

## Why this phase matters

P6 uses the regulator's unique market-wide view. It can turn several apparently isolated incidents into a single market warning, identify common dependencies before they fail, and distinguish an institution-specific problem from an emergent systemic risk.

---

# X1 — The firm's own controls

## What this phase does

X1 is control assurance. It applies across every lifecycle phase.

Detecting that an agent exceeded a cap, followed an injected instruction or paid a prohibited party explains what happened. Supervision must also explain why the operator's and institution's own controls allowed it.

For every material failure, the regulator compares the risk with the controls the firm declared and then examines how those controls actually operated.

## Failures that may occur

### Absent control

- The mandate creates a material risk, but no corresponding control exists.
- The firm declares limits without implementing mechanisms to enforce them.
- The operator and institution each assume the other party owns the control.
- A required control exists in policy but not in the production repository.

### Failed control

- A control should have triggered but did not.
- The control was misconfigured.
- Required input data was missing or incorrect.
- The control existed only in documentation.
- The control evaluated the wrong value, identity or stage of the payment.

### Bypassed control

- A blocking control triggered and a person or system overrode it.
- The override has no named decision-maker.
- The person overriding the control lacked authority.
- No reason for the override was recorded.
- A verbal or informal approval replaced the documented process.
- Overrides occur so frequently that they have become routine.

### Ineffective control

- A blocking control triggered and remained in force, but the payment still settled.
- A control believed to be blocking was only advisory.
- The control was disconnected from payment execution.
- The control detected an event but could not prevent it.
- The control addressed the wrong risk while giving the appearance of protection.

### Audit and reconciliation failures

- The control log does not cover the complete reporting period.
- Log entries can be altered after the event.
- Control evaluations do not reconcile with settled transactions.
- Executed payments are missing from the control log.
- Override records are incomplete or inconsistent.

## Why this phase matters

“The agent exceeded its cap” is a detection. “The firm's blocking control triggered, and a named analyst overrode it 52 seconds later without documented authority” is a supervisory finding. X1 distinguishes governance failure, technical failure, deliberate conduct and ineffective system design so the regulator can respond appropriately.

---

# How the phases fit together

The lifecycle can be summarised through eight questions:

1. **Identity:** Should this agent exist, and who is accountable for it?
2. **Authorisation:** Did a human knowingly grant the mandate under which it acted?
3. **Decision integrity:** Were the model, prompt, tools and information shaping the decision trustworthy?
4. **Mandate integrity:** Was the signed payment within the authority granted?
5. **Counterparty:** Who actually received the money?
6. **Behaviour:** What does the agent's activity reveal over time?
7. **Systemic risk:** What is happening across many agents and firms?
8. **Control assurance:** Why did the firm's controls allow the event?

No single signature, transaction or model can answer all eight. Comprehensive supervision requires firm-submitted evidence, regulator-held registries, deterministic verification, narrowly bounded semantic assessments, historical analysis, portfolio-level visibility and final human judgement.

---

# Important limitations

- A firm-reported model version is accountable self-reporting, not cryptographic proof from the model provider.
- Manipulative consent-screen design cannot be reliably detected without visual or interaction evidence.
- Agent-to-agent manipulation is difficult to assess without negotiation transcripts.
- Missing evidence must be reported as **unable to assess**, not treated as evidence that no failure occurred.
- Intent fidelity and value-for-money decisions contain judgement and must remain separate from deterministic facts.
- Market-wide findings require multiple institutions and enough history to establish meaningful patterns.
- A rule that has never fired on representative evaluation data is implemented, but not yet demonstrated to be correct.

