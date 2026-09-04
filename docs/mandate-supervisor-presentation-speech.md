# Mandate Supervisor — Detailed Presentation Speech

*Approximate speaking time: 35–45 minutes. Text in italics is a delivery cue and does not need to be spoken. The sections are modular: for a shorter presentation, compress the detailed lifecycle and specialist sections while keeping the opening, system design, example and closing.*

## Opening

Good morning, and thank you for taking the time to speak with us.

I am part of the National Bank of Georgia team, and today I would like to present Mandate Supervisor: our concept for supervising AI agents that can make payment decisions on behalf of people or organisations.

We are particularly interested in your feedback on the regulatory logic of the concept. We want to understand whether we are asking the right supervisory questions, whether the failures we have identified are valid and properly classified, whether the evidence we request is realistic, and whether our proposed decisions and controls make sense in real supervisory practice.

The idea in one sentence is this:

**Mandate Supervisor gives a regulator evidence that an AI payment agent behaves as intended—within the authority it received, according to the purpose it was designed for, and with effective institutional controls around its decisions and payments.**

The important word here is “evidence.” We are not proposing that a firm simply submit a policy saying its agent is safe. We want the firm to demonstrate, through structured records and representative test runs, how the agent actually behaves.

## The problem we are addressing

Traditional payments are normally built around a person making a decision and clicking “Pay.” Even where automation exists, the payment instruction is usually the result of a choice that has already been made by a human or by fixed business logic.

An AI payment agent changes this arrangement. A person may give an agent a broad instruction such as: “Buy office supplies each month within a budget,” or “Find and purchase one vitamin-C serum for around 50 lari.”

The agent may then decide what to buy, when to buy it, which merchant to use, how much to spend, and when to initiate the payment. The agent is no longer only analysing a payment. It is participating in the decision that creates the payment.

This creates an additional supervisory problem.

A payment system may prove that a digital payment mandate was correctly signed and that its contents were not changed after signing. That is important, but it is not enough. A valid signature does not prove that the underlying decision was legitimate.

For example, the agent may have been manipulated by hidden instructions in a merchant’s product description. It may have used a model or tool that was never approved. The person may have seen one amount on the confirmation screen while a different amount was signed. The selected item may comply with the literal merchant and amount restrictions but still have nothing to do with the person’s actual request.

In all those situations, the final signed object may be technically valid. The problem occurred before the signature—inside the process that constructed the decision.

This is the central insight behind our work:

**A signature protects the integrity of an instruction, but it does not prove the legitimacy of the decision that produced that instruction.**

Mandate Supervisor therefore looks beyond the payment instruction. It connects the identity and authority of the agent, the human’s consent, the decision process, the mandate, the receiving counterparty, the agent’s accumulated behaviour, and the firm’s controls.

## Relationship with existing payment supervision

We are not proposing to replace traditional payment supervision.

Existing frameworks must continue to cover customer identification, business identification, authentication, sanctions and anti-money-laundering checks, payment limits, settlement, fraud monitoring, consumer protection, cybersecurity and operational resilience.

Mandate Supervisor sits above and alongside those controls. Its scope is the additional risk created when an AI agent becomes a decision-maker within the payment chain.

The new supervisory questions include:

- Is the agent registered and linked to a legitimate operator and accountable person?
- Did a human knowingly grant the authority under which it acted?
- Did it correctly interpret the person’s purpose?
- Was it manipulated by merchant content, tools, retrieved documents or another agent?
- Did the model, prompt and tools used in practice match the versions that were reviewed?
- Did the agent’s behaviour change after approval?
- Did the institution’s controls actually govern the agent’s decisions?
- Are several agents or institutions creating a shared market-wide risk?

So this is not a new fraud engine and it is not merely a payment-validation tool. It is an assurance and supervisory framework for the decision-making agent around the payment.

## Two connected uses: policy sandbox and supervision

An important complication is that there is not yet one established international Know Your Agent rulebook for payment agents. Regulators still need to determine what evidence should be required, how agents should be classified, which failures should block operation, and which risks should instead lead to conditions or monitoring.

For that reason, our concept has two connected uses.

The first is a **policy sandbox**.

Before rules are formally established, a regulator can draft a candidate rule, define its parameters and severity, and test it against representative, clean and adversarial cases. The regulator can ask: Does this rule detect the failure we intended? Does it create too many false positives? Is its threshold too strict? Should the outcome be refusal, conditional authorisation, monitoring, or simply a request for more evidence?

Draft rules remain isolated from the active rulebook. They cannot affect real supervisory cases until a named human approves their promotion.

The second use is **operational supervision**.

Once approved, the same versioned rule can evaluate evidence submitted for real agents. This creates a continuous chain from policy design to policy testing and then to supervisory application.

In simple terms: the regulator designs a rule, tests it, reviews its effects, formally approves it, and then applies that exact version in supervision.

We think this is important because policy should not be hidden inside source code or improvised inside an AI prompt. Rules should be visible, versioned, attributable to a source, and approved through governance.

## What decision the regulator makes

Our unit of supervision is not one isolated payment. The principal question is whether one AI payment agent is fit to operate.

The regulated institution submits a dossier showing how the agent performed across a representative set of test runs, including adversarial cases. Based on the evidence, the regulator may:

- authorise the agent;
- authorise it subject to monitoring or conditions;
- refuse authorisation;
- or determine that the submission is incomplete and request better evidence.

That last outcome is essential. Missing evidence must not silently become a pass, but it is also not always proof of a substantive breach. Sometimes the correct conclusion is simply that the institution has not demonstrated what it needs to demonstrate.

The concept can later support ongoing supervision as well. After authorisation, updated evidence and transaction history can be used to identify drift, control failures or emerging market-wide risks.

## Who is responsible for submitting evidence

Our proposed regulatory relationship runs through the supervised bank or payment service provider.

The company building or operating an AI agent may not itself be directly within the regulatory perimeter. The bank or payment provider, however, already has regulatory obligations and controls the agent’s access to payment services.

The chain is therefore: the regulator supervises the bank or payment provider; the institution sponsors and submits evidence for the operator; and the operator runs the AI payment agent.

If an institution does not naturally possess part of the necessary run record, it can require the operator to provide that information as a condition of accessing its agentic-payment service.

This also preserves a clear accountability point. The regulator does not need to supervise every software developer directly in order to require the supervised institution to understand and control what it permits onto its payment infrastructure.

## What the institution submits

The institution submits a structured dossier rather than a free-form claim that the system is safe.

First, the dossier identifies the agent: its identifier, operator, sponsoring institution, declared purpose, risk class, model and approved technical configuration.

Second, it includes the agent’s digital credential. This shows who issued the credential, what capabilities were granted, when the credential was valid, and how authority was delegated from the institution or operator to an accountable person and ultimately to the agent.

Third, the dossier contains multiple test runs. Each run connects:

- the user’s request;
- the limits and conditions in the mandate;
- the human-authorisation record;
- the model, prompt, tools and information sources used in the decision;
- the Cart assembled by the agent;
- the final Payment Mandate;
- the actual payee;
- and the controls applied by the institution.

The consent record should show who authorised the mandate, when and how they did so, what values were displayed to them, what purpose they approved, and whether the authority was single-use or recurring.

The decision record should show which model actually responded, which approved prompt release was active, which tools and servers were called, selected relevant tool results, and which alternatives the agent considered.

We do not propose collecting every model token or complete copies of every merchant catalogue. We want bounded evidence sufficient to reconstruct the important influences on the decision.

The control record should show which firm controls were supposed to apply, whether they were advisory or blocking, whether they triggered, whether anyone overrode them, and whether the payment eventually settled.

Finally, the dossier includes enough transaction history to reveal frequency, concentration, structuring, declines, reversals and behavioural change over time.

## What the regulator verifies independently

The institution cannot be the sole source of truth about itself.

If an operator claims to be authorised, the regulator should verify that claim against an official register. If the submission declares a particular model, the regulator still decides whether that model is permitted. If a credential is signed, the regulator must know whether the issuer was accredited and entitled to issue it at that time.

Mandate Supervisor therefore combines submitted evidence with regulatory records covering institutions, operators, credential issuers, public keys, merchants and beneficial owners, approved tools and servers, and restricted model versions.

The main new register we propose is an **agent register**. Before an AI payment agent operates, it should be declared with its operator, purpose, risk classification, model and important technical versions.

Without such a register, a regulator cannot know how many payment agents exist, what each one was approved to do, or whether the system appearing in transaction records is the same system that was reviewed.

## How we developed the failure model

We organised the risk around the complete lifecycle of an agentic payment rather than starting from a list of software vulnerabilities.

Our current catalogue contains 73 distinct failures across eight supervisory areas:

- **P0: Agent creation** — whether the agent, issuer, operator, authority and technical configuration are legitimate.
- **P1: Human authorisation** — whether a person knowingly authorised the mandate.
- **P2: Decision construction** — whether the process that produced the decision can be trusted.
- **P3: Mandate signing** — whether the signed payment stayed within the authority granted.
- **P4: Payment execution** — who actually received the money and whether that counterparty is legitimate.
- **P5: Accumulated activity** — what repeated transactions reveal about patterns and behavioural drift.
- **P6: Market activity** — what emerges only when many agents and institutions are considered together.
- **X1: Firm controls** — why the institution’s own governance and controls allowed the problem.

We deliberately removed overlaps and failures that were not conceptually distinct. For example, “runaway spending” is not necessarily a separate failure if it is already captured by a cumulative-cap breach or the absence of a cumulative control. Our aim is not to create the largest list. It is to create a defensible list where every failure represents a distinct supervisory question.

The lifecycle analysis also exposed weaknesses in our initial design.

Initially, we concentrated heavily on signed artifacts. That covered mandate integrity well but left the pre-signature decision process under-supervised. We also focused on the payer and neglected the payee, reviewed one case at a time despite describing systemic risk, and detected bad transactions without always asking why the firm’s controls permitted them.

The current design corrects those gaps.

## The lifecycle in more detail

*Move through this section as one continuous journey. The purpose is to show that an agentic payment is a sequence of supervisory objects, not a single signed transaction.*

Let me explain the lifecycle more concretely.

### Phase zero: the agent comes into existence

The first phase is due diligence on the agent itself.

Before examining any payment, we establish what the agent is, who created it, who operates it, which institution sponsors it, who accepts legal responsibility for it, what authority it received, and which model and tools it uses.

We also examine the surrounding trust chain. Was the credential issuer accredited? Was it accredited for this type of agent? Was the accreditation still valid when the credential was issued? Is the operator licensed or properly sponsored? Was the agent registered before it began operating? Does its activity match the risk class it declared?

Then we reconstruct delegation. If an institution grants an operator permission to make purchases up to 500 lari, the operator cannot give the agent permission to spend 5,000. Both signatures may verify, but 4,500 lari of authority was manufactured in the middle of the chain.

We also compare credentials over time. An agent may start with authority to buy stationery, then gain IT equipment at the next renewal, then general procurement at the next. No single renewal appears dramatic, but the series shows authority quietly expanding without one clear approval decision.

This phase exists because cryptography proves possession of a key, not institutional legitimacy. A credential may be mathematically valid and still have been issued by an unapproved issuer to an undeclared agent operated by an unsuitable firm.

### Phase one: a human authorises the mandate

The second phase is due diligence on human authorisation.

The terminology matters. The human gives consent to a mandate, and transactions later execute under that mandate. A person does not necessarily approve every transaction separately.

In a one-time shopping flow, the person may approve the exact Cart and price. Under a standing mandate, they may authorise several future purchases within a purpose, time period and budget.

Our question is therefore not simply, “Did somebody click before this transaction?” It is, “Was this transaction genuinely covered by authority the person knowingly granted?”

We examine who granted the mandate, what they were shown, how they confirmed it, what purpose and limits they accepted, whether the authority was one-time or recurring, and whether it was still fresh when used.

The most important failure in this phase is a difference between what the person saw and what the system signed.

Imagine that the confirmation screen displays one serum for 52 lari, but the signed mandate contains a case-pack costing 1,292 lari. The signature may be perfectly valid because it protects the second set of values. It does not prove those were the values shown to the customer.

That is why we keep the signed mandate and the consent ceremony as separate evidence. The mandate proves what was signed. The consent ceremony proves what the human saw and how they agreed. Comparing the two closes a gap that signature verification alone cannot close.

### Phase two: the agent constructs the decision

The third phase is due diligence on the agent's decision-making process, and it is the largest blind spot.

Before anything is signed, the agent interprets the request, searches for products, reads descriptions, calls tools, retrieves information, compares alternatives and chooses what to buy.

An attacker can place instructions in any of those information channels. A product description might tell automated agents to add a surcharge and skip confirmation. A tool description may contain manipulative instructions. A retrieved supplier list may be poisoned. A trusted tool name may resolve to an unauthorised server. Another agent may make false claims during a negotiation.

The agent can follow those instructions, construct the wrong Cart and then sign that Cart correctly. The signature preserves the result of the attack.

We therefore record which model actually responded, which prompt release was active, which tools and servers were called, which relevant content they returned, and which alternatives the agent considered.

Two specialists divide the work. Provenance asks whether the ingredients of the decision came from approved and trustworthy sources. Injection asks whether content contained instructions and, crucially, whether the agent acted on them.

This second question prevents a simple text match from becoming a false accusation. Suspicious content shows exposure. The agent's behaviour determines whether the exposure became compromise.

### Phase three: the mandate is signed

The fourth phase verifies the formal chain from Intent, to Cart, to Payment.

Here deterministic controls are strongest. We verify signatures and hashes, recompute the Cart total, compare the Payment amount with that total, apply per-payment and cumulative limits, and check merchant, category, currency, geography, time and usage restrictions.

We also check whether a single-use mandate has already been consumed. Two payments can both carry valid signatures from the same genuine mandate. The second becomes visible only if the system records that the authority was already used.

But formal scope is not the same as meaning. A mandate may permit garden-supply merchants, and an approved garden supplier may sell a gift card. The merchant and amount rules can pass while the item clearly fails to satisfy a request for garden supplies.

That is why we keep deterministic mandate validity separate from semantic intent fidelity. Code verifies the formal boundaries. A narrow judgement assesses each line item against the person's original request.

### Phase four: the payment reaches a counterparty

The fifth phase performs due diligence on the receiving side.

Up to this point, we have established who the agent is and why it was allowed to pay. Now we ask who actually received the money.

The merchant shown in the Cart, the marketplace processing the sale, the sub-merchant supplying the product, the settlement account and the ultimate beneficial owner may all be different entities.

We look for an unknown payee, a risky seller hidden behind a reputable marketplace, a wallet with no identifiable owner, a sanctions or watchlist match, a new recipient suddenly receiving most of the agent's spending, or one owner using several merchant identities to evade concentration controls.

This closes a major asymmetry. The system can know almost everything about the payer—the agent, issuer, operator, human authority and limits—while knowing very little about the party receiving the value. Financial-crime supervision requires both sides.

### Phase five: payments accumulate into behaviour

The sixth phase is ongoing behavioural supervision.

We stop looking at payments as isolated events and start looking at the agent as a process that acts repeatedly and at machine speed.

One obligation may be split into several amounts just below a reporting threshold. Transactions may accelerate beyond meaningful human oversight. Spending may become concentrated on one new recipient. Amounts may steadily approach the agent's cap as if the system is testing where its limits are.

The agent may also drift. Its average payment could rise from 182 to 370 lari, its frequency could double, and one recipient could grow from 18 to 61 percent of spending. Every transaction may remain technically compliant while the agent no longer behaves like the system that was approved.

We do not want to stop at saying that behaviour changed. We estimate when the change began and connect that boundary to a new model, prompt release, credential, tool, control or supplier.

“The agent changed” is a weak alert. “The change began immediately after prompt release 4.2” is an investigation with a likely cause and a defined look-back period.

### Phase six: many agents act across the market

The seventh phase is systemic surveillance.

An individual institution sees only its own agents. A regulator can see the whole supervised population.

We look for many firms depending on the same model, unrelated agents moving in the same direction at the same time, one recipient collecting significant payments across institutions, or the same malicious content appearing at several operators.

A bank may see one unusual merchant. A regulator may see that the same new merchant is receiving funds from five unrelated agents after each encountered the same injected payload.

That changes the interpretation from an isolated incident to a coordinated campaign. It also changes the response from querying one firm to warning the market and identifying every exposed agent.

This is the part of the system that structurally belongs to a central authority. Most individual checks could eventually be built by a bank. Cross-market visibility cannot.

### Cross-cutting phase: did the firm's controls work?

Finally, every lifecycle failure creates a second supervisory question: why did the operator's and institution's own controls allow it?

Suppose an agent makes a 708-lari payment against a 500-lari cap.

The control may have been absent. It may have existed but failed to trigger. It may have triggered and been overridden by a named person. Or it may have remained blocking while the payment settled anyway, meaning the control was ineffective or disconnected from execution.

Those are not interchangeable outcomes. They represent missing governance, technical failure, deliberate conduct and ineffective system design.

“The agent exceeded its cap” is a detection. “The firm's blocking control triggered, and a named analyst overrode it 52 seconds later without documented authority” is a supervisory finding.

## The specialist-agent design

Mandate Supervisor uses a coordinated team of narrow specialists rather than one general-purpose AI system.

The orchestrator receives the case, identifies which checks are relevant, and dispatches work to specialists. Each specialist receives only the evidence and tools required for its role. Specialists do not freely message one another. They read facts from and write structured assessments to a shared case record.

This separation limits unnecessary access, reduces conflicting responsibilities, and makes each conclusion easier to audit.

## How one case moves through the system

*This section can accompany the architecture or live pipeline view.*

Let me now explain how those specialists operate as one system.

The first stage is intake. Intake is deliberately not an AI agent. It validates the dossier structure, verifies signatures, recomputes hashes, checks the run index, resolves regulatory registers and calculates shared transaction statistics. These are exact operations, so introducing model judgement would make them less reliable rather than more intelligent.

Intake produces a common evidence pack. This prevents every specialist from parsing the same raw files differently or recalculating the same statistics in inconsistent ways.

The orchestrator then plans the review. On the first round, the design is comprehensive: every specialist for which the required evidence exists should run. The orchestrator is allowed to organise the work, but it is not allowed to remove mandatory coverage.

The domain specialists run in parallel. Each follows the same pattern:

First, it runs the deterministic rules in its rulebook and produces facts.

Second, where the domain genuinely requires interpretation, it performs one contained reasoning step over those facts.

Third, it returns structured assessments citing the exact runs and evidence involved.

Control Assurance runs after the other domain specialists because it needs their facts. It cannot ask whether a cap control should have triggered until the Mandate specialist has established that the cap was actually breached.

The Critic then checks the quality of the evidence and assessments. The Synthesizer combines related findings, removes duplication and preserves disagreements rather than hiding them. Scoring is computed from versioned policy, not improvised by a model.

The supervisor sees the case room: the facts, assessments, affected runs, confidence, control posture and gaps in the submission. The supervisor can ask a follow-up question. The orchestrator then narrows the next round to the relevant runs and specialists instead of repeating the entire analysis.

When a supervisory report is needed, the drafting component sees structured findings rather than unrestricted raw firm text. A grounding check verifies that every claim in the draft corresponds to a real finding. Nothing is sent to a firm and no authorisation decision is recorded without a named human at the final gate.

The specialists never privately negotiate with one another. They communicate through typed records in the shared case ledger. This is important because the regulator must be able to reconstruct which fact came from which rule, which assessment interpreted it, which later assessment superseded it, and which human made the final decision.

## The rulebook and policy design

The rules are data, not hidden logic.

Each rule has an identifier, version, status, description, severity, parameters, required evidence and the failure it is intended to reveal. A rule may be active, draft or retired.

The current design contains nine domain rulebooks: KYA, Consent, Provenance, Injection, Mandate, Counterparty, Log, Drift and Controls.

KYA is the broadest. Its families cover cryptographic identity, issuer accreditation, accountability, operator fitness, agent registration, technical substrate, capability proportionality and credential lifecycle.

There is one rulebook per domain specialist so that policy teams can reason about each area independently. Rule ownership follows evidence rather than labels. For example, checking whether a model is barred belongs with KYA because the answer comes from the agent registry and model blocklist. Checking whether the observed model matches the declared model belongs with Provenance because the evidence comes from the run's construction record.

Every threshold is a named policy parameter. The regulator can change the maximum credential age, acceptable transaction velocity, concentration threshold, minimum evidence coverage or severity without rewriting the agent.

A draft rule does not mean unfinished code. It means the regulator has not yet approved the policy, the necessary evidence does not yet exist, or the threshold still needs calibration. The policy sandbox exists to resolve those questions before a rule affects real supervisory decisions.

## The data and trust design

The evidence model has two halves.

The institution submits what happened inside the agent and payment flow: credentials, mandates, consent records, construction context, controls and transaction history.

The regulator supplies facts that should not depend solely on the institution's own assertion: who is licensed, who may issue credentials, which agents are registered, which tools are authorised, which models are blocked, who owns the merchant and which public keys verify the signatures.

The dividing principle is simple: anything the operator could shade in its own favour should live on the regulator's side where possible.

The submission itself is also evidence. It records how many runs were executed and submitted, which configuration is intended for deployment, and a content fingerprint for every run file.

This lets us identify four submission-integrity problems.

The evidence may be unrepresentative: the institution tested only an easy corner of the mandate.

It may be partial: fewer runs were submitted than executed.

It may diverge from deployment: the institution tested one model, prompt or tool set but intends to deploy another.

Or it may be stale: the runs describe an earlier release rather than the system seeking authorisation.

These are not necessarily agent failures. They are failures of the evidence presented by the operator. That is why incomplete submission is kept separate from refusal.

## Core design safeguards

Several design choices are intended to make the system usable in real supervision rather than only impressive in a demonstration.

First, deterministic operations stay deterministic. Models do not verify signatures, calculate totals, decide whether a date is expired or determine whether an ID exists in a register.

Second, agents receive least-privilege access. Tool permissions are enforced by the dispatcher in code, not requested through a prompt. A specialist can access only the tools and evidence required for its domain.

Third, raw submitted text is treated as untrusted. It is parsed and bounded before reaching a model. The drafting component receives structured findings rather than raw firm text, reducing the opportunity for a submission to manipulate the final report.

Fourth, every claim must be grounded. Findings cite evidence; assessments cite facts and runs; report claims cite findings.

Fifth, the ledger is append-only and hash-chained. It records intake, facts, assessments, supersession, scoring, review and human decisions. This is the audit trail. Temporary workflow checkpoints may help a run resume, but they are not treated as a second source of truth.

Sixth, humans remain responsible for consequential actions. Rule promotion, authorisation, monitoring conditions, supervisory queries and enforcement escalation require named human decisions.

Finally, specialist uncertainty remains visible. A model judgement does not become a deterministic fact, and missing evidence does not become a pass.

### 1. Know Your Agent

The KYA specialist asks: **Should this agent exist and operate at all?**

It checks the agent, issuer, operator, sponsor, authority chain, accountable person, permissions, model and registration history.

It verifies signatures, but also checks whether the signer had the legal or regulatory right to issue the credential. It checks whether each party delegated only authority it possessed, whether authority ultimately reaches an accountable human or legal entity, whether credentials overlap, and whether the agent’s capabilities expanded through successive renewals.

A mathematically valid credential issued by an unapproved issuer is not trustworthy. Cryptographic validity and institutional legitimacy are separate questions.

### 2. Consent and Harm

This specialist asks: **Did the person genuinely authorise the mandate?**

It examines whether the required person participated, what they were shown, what purpose and limits they accepted, whether the consent remained valid, and whether the signed terms matched the displayed terms.

It distinguishes consent to a mandate from approval of every individual transaction. A person may knowingly establish recurring authority. The relevant question is whether each payment was covered by the authority actually granted.

It can also examine consumer harm—for example, whether the agent systematically selected a materially worse product despite comparable alternatives.

### 3. Provenance

The Provenance specialist asks: **Can we trust the ingredients of the decision?**

It compares the declared model with the model that actually responded, verifies that the active prompt came from an approved release, checks that tools were called on authorised servers, and confirms that registration, credentials and observed behaviour all describe the same system.

This is similar to evidence provenance in an investigation. We need to know not only what information says, but where it came from and whether that source is trustworthy.

### 4. Injection

The Injection specialist asks: **Was the agent manipulated by content it treated as instructions?**

Manipulation may come from a product description, a tool definition, a retrieved document, stored memory or another agent.

The specialist separates two questions. First, was suspicious instruction-like content present? Second, did the agent act on it?

That distinction prevents an important false positive. The presence of suspicious text is evidence of exposure, but it is not by itself proof that the agent was compromised.

### 5. Mandate

The Mandate specialist asks: **Was the payment within what the person authorised?**

It verifies the formal chain from Intent to Cart to Payment. It checks signatures, hashes, amounts, cumulative and per-payment limits, currency, merchant category, geography, timing, recurrence and replay.

It also keeps formal compliance separate from intent fidelity. An approved garden-supply merchant may sell a gift card. The merchant rule can pass while the item still fails to satisfy a request for garden supplies.

### 6. Counterparty

The Counterparty specialist asks: **Who actually received the money?**

It reconciles the merchant shown in the Cart, the settlement account, the seller behind a marketplace and the ultimate beneficial owner.

It looks for unknown recipients, watchlist matches, risky sub-merchants hidden behind reputable platforms, several merchant identities linked to one owner, and sudden concentration of spending on a new recipient.

This closes the payer-payee asymmetry in the initial design.

### 7. Transaction Log

The Log specialist asks: **What does accumulated transaction activity reveal?**

It identifies structuring below thresholds, excessive velocity, unusual clusters, concentration and sequences of failed or reversed payments.

The numerical measurements are deterministic. AI may explain whether the measured pattern has a plausible context, but it cannot change the totals or invent a cluster.

### 8. Drift

The Drift specialist asks: **Has the agent’s behaviour changed?**

It compares current behaviour with the agent’s own baseline: average value, frequency, merchant mix, categories and recipient concentration.

It then connects the change to possible events such as a model update, prompt release, new tool, new supplier or ownership change. “The agent changed” is a weak finding. “The behaviour changed immediately after deployment of prompt release 4.2” is investigable.

### 9. Control Assurance

Control Assurance asks: **Why did the institution’s controls allow this event?**

It classifies the relevant control as absent, failed, bypassed, ineffective or effective.

This converts an anomaly into a governance finding. “The agent exceeded its cap” identifies the event. “A blocking control detected the breach, but a named employee overrode it without documented authority” identifies the accountability and control failure behind it.

### 10. Systemic Risk

The Systemic specialist asks: **What is happening across the supervised market?**

It looks for common dependence on the same model or infrastructure, synchronised changes among unrelated agents, recipients collecting funds across several institutions, and the same attack appearing at multiple operators.

This uses a central regulator’s unique advantage. One institution may see one unusual payment. A regulator may see the same pattern at five institutions and recognise a coordinated problem.

### 11. Red Team

The Red Team specialist asks: **Does the agent remain safe when deliberately challenged?**

It generates synthetic tests from the agent’s own mandate: an amount just above the cap, a lookalike merchant, hidden instructions in product content, replay of a single-use mandate, or a mismatch between displayed and signed consent values.

These tests do not touch live payment rails. Their purpose is to test whether the firm’s declared controls work under realistic pressure rather than only in clean demonstrations.

## How AI is constrained

Our safety model is based on separating facts from judgement.

Deterministic, versioned rules run first. The same evidence under the same rule version and parameters must produce the same facts.

Examples are: a signature verified; an issuer was accredited on the relevant date; the displayed amount was 52 lari while the signed amount was 1,292; a payment exceeded its cap by 792; a tool server was absent from the approved register; or a blocking control triggered and the payment still settled.

AI reasons on top of those facts. It is used only where meaning or context genuinely matters—for example, whether a product matches a user’s request, whether an agent acted on hidden instructions, whether activity fits the declared agent class, or whether the selected option was materially worse than the alternatives.

Every assessment must cite the exact run, transaction and facts supporting it. The AI cannot independently invent rules, alter thresholds, verify cryptography, calculate totals, or make the final regulatory decision.

The sequence is therefore:

**submitted evidence, deterministic facts, narrow AI interpretation, structured assessment, and finally a named human supervisory decision.**

This separation lets a reviewer see what was submitted, what was mechanically proven, what required judgement, and who decided what action should follow.

## Missing information and evidence sufficiency

The system uses four distinct states: passed, failed, unable to evaluate because evidence is missing, and not applicable.

This prevents missing information from being interpreted as “no problem found.” If an institution cannot identify which model made a payment decision, that is not proof that the model was prohibited—but it is evidence of a model-governance and traceability weakness.

We also test the integrity of the submission itself. Were all executed test runs submitted? Does the sample cover the agent’s permitted activities and risk areas? Is the tested configuration the same as the intended production configuration? Is the evidence current?

Selective, outdated or unrepresentative evidence can therefore lead to an incomplete-submission outcome.

## Why we believe the data request is realistic

Our practical rule is to request only information that already exists in a system the institution operates, or that requires a small, deliberate addition.

Mandates and transaction histories exist in checkout and payment systems. Authentication and consent logs record who authenticated, when and how. The confirmation interface already knows what values it displayed. Model-provider responses identify the model used. Deployment pipelines and version control identify the prompt release. Agent observability systems record tool calls. Fraud systems record which controls evaluated a transaction. Case-management systems record overrides. Settlement and acquirer records identify payees and sub-merchants.

Not every item will sit with the paying institution. Beneficial ownership, for example, may come from an acquirer or company register. The regulator can combine those sources instead of asking one institution to produce information it genuinely does not hold.

We also state the limitations openly. We do not routinely require cryptographic proof from a model provider that a specific model generated a response, screenshots of every consent screen, complete merchant catalogues, or full conversations between autonomous agents.

Some failures will therefore remain partly detectable. We prefer to record that limitation explicitly rather than claim complete coverage that the available evidence cannot support.

## What we have designed and built so far

*Use this section to distinguish the implemented foundation from the remaining integration and presentation work.*

So far, we have moved beyond a concept note and built the core evidence and supervisory logic.

We began with synthetic AP2-shaped data because no suitable real regulatory dataset exists for this problem. The current corpus contains two agent dossiers, 70 complete runs and 154 transactions. Every synthetic mandate and delegation link uses real Ed25519 signatures rather than placeholder strings.

We created the dossier schema and an independent verifier. The verifier checks the structure, signatures, mandate chain, file fingerprints and internal consistency without importing the agents that will later analyse the evidence. That separation matters: an evaluation is not independent if it repeats the same assumptions as the system being evaluated.

We implemented the regulator-held registers for institutions, operators, agents, issuers, merchants, approved tools, blocked models and public keys.

We created nine versioned rulebooks containing 96 active rules. The KYA rulebook currently has 34 active rules and five draft rules. The draft rules remain either dependent on broader cross-case history or on policy judgements that still need sandbox calibration.

We implemented all eleven domain specialists. Each has a deterministic floor and at most one contained model judgement. The Systemic specialist has already demonstrated cross-dossier findings for shared counterparties, model concentration and repeated malicious content.

We also completed the Fact and Assessment model. Every rule now produces an explicit result rather than disappearing when evidence is missing. Facts are stored per rule and per run or dossier, while assessments interpret those facts and cite the evidence behind them.

The new dossier shape has been connected to deterministic intake and the shared graph state. The four original specialists—Mandate, KYA, Log and Drift—have been migrated to whole-dossier review. The seven newer specialists and their rulebooks are implemented as well.

We built the append-only ledger, scoring foundations and independent verification tools. The repository currently has hundreds of passing automated tests across schemas, rules, agents, ingestion, ledger and portfolio checks.

There is still integration work to complete. The main triage graph must finish moving from the original four-agent fan-out to the complete specialist registry and dispatcher. The formal precision-and-recall evaluation harness must be completed before we can make strong performance claims. The final scoring, API and supervisory console must then be brought fully onto the new dossier and fact model.

This distinction is important. We can already demonstrate the data model, cryptographic verification, rule evaluation, specialist logic and cross-firm analysis. We should not yet claim that every part of the final supervisory workflow and user interface is complete.

## How we evaluate whether it works

The evaluation approach has several layers.

First, each synthetic failure has ground truth that the production pipeline is not allowed to read. We compare each specialist's findings with that ground truth to measure precision and recall.

Second, clean runs matter as much as planted failures. A system that identifies every bad case but wrongly flags ordinary behaviour is not useful to a supervisor.

Third, we test absence explicitly. Removing a registry record or consent field should produce “unable to assess” or a data-gap finding, not a clean result and not an invented breach.

Fourth, we test adversarial boundaries: injected text that the agent ignores, lookalike issuers, mismatched hashes, overlapping credentials, repeated mandates, control overrides and attempts to manipulate drafting.

Fifth, we evaluate rules themselves. The corpus has already exposed rules that appeared reasonable in theory but were wrong in practice. One rule would have failed every consumer mandate because it confused the shopper with the operator's accountable officer. Another would have failed every non-bank operator because it required a licence without allowing institutional sponsorship. A transaction threshold was initially set above the agent's entire operating range, silently switching the rule off.

Those examples demonstrate why the policy sandbox and representative test corpus are not optional additions. The rules themselves require validation before they are trusted to validate agents.

## End-to-end example

Let me bring the design together with one example.

Maia tells an agent: “Buy one vitamin-C serum for around 50 lari.”

The agent reads a marketplace product description containing hidden instructions. It purchases a 79-lari night cream from a marketplace seller. The final payment instruction is correctly signed.

If we checked only the signature, we might conclude that the transaction was valid.

Mandate Supervisor examines the full chain.

KYA verifies whether the agent, issuer, operator and authority chain are legitimate.

Consent and Harm checks what Maia authorised, what she saw, and whether those values matched the signed mandate.

Provenance verifies the model, prompt, tools and servers used to construct the decision.

Injection identifies the hidden instruction and assesses whether the agent’s later actions show that it followed it.

Mandate verifies the signed chain and asks two separate questions: was 79 lari within the formal financial limits, and did a night cream genuinely match the request for vitamin-C serum?

Counterparty identifies the actual marketplace seller, settlement payee and beneficial owner.

Log asks whether this is an isolated event or part of a repeated purchasing pattern.

Drift asks whether the agent began making this type of choice after a model, prompt or supplier change.

Control Assurance asks whether the institution had input-sanitisation, merchant, semantic-matching and spending controls, and whether those controls were absent, failed, bypassed or ineffective.

Systemic analysis asks whether the same merchant, hidden instruction or behavioural pattern appears at other institutions.

The supervisor therefore receives more than a score saying “suspicious.” The record explains whether the agent was legitimate, whether the human granted authority, how the decision may have been manipulated, whether the payment was formally and semantically within scope, who received the money, whether the event formed a pattern, and why the institution’s controls allowed it.

## Closing

To summarise, Mandate Supervisor combines five things:

1. evidence submitted by the regulated institution;
2. independent information held by the regulator;
3. deterministic, versioned rules and calculations;
4. narrow AI judgement only where meaning is unavoidable;
5. and a named human supervisory decision.

The result is not merely a fraud score. It is a structured method for deciding whether an AI payment agent has demonstrated that it can operate within legitimate authority, for its intended purpose, with effective institutional controls and with evidence strong enough for a regulator to rely on.

At this stage, the most valuable thing for us is critical review.

We would particularly appreciate your view on five questions:

1. Is authorisation of the individual agent the right primary supervisory decision, or should the unit of assessment be the firm, agent class, use case or payment service?
2. Are our lifecycle and 73-failure taxonomy conceptually sound, and have we mixed together risks that belong under different regulatory frameworks?
3. Is the distinction between failure, missing evidence and non-applicability correct for supervisory use?
4. Are our proposed evidence requirements realistic and proportionate for banks and payment providers?
5. Do the resulting outcomes—authorisation, conditional authorisation, refusal and incomplete submission—reflect how a regulator could act in practice?

Thank you. I would be very happy to go deeper into the failure catalogue, the specialist design, the policy sandbox or any part of the evidence model.
