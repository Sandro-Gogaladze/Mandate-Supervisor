# C:\>DIR Global 'Agentic Regulator' Hackathon — Concept Note (as submitted, 8 August 2026)

Team: NBG. Problem space: Agentic Payments & Commerce & their Oversight.

## 1. The Current State (Context)

This concept note addresses Agentic Payments & Commerce & their Oversight, closely tied to Know Your Agent (KY-A), Digital Verification & Digital Public Infrastructure. The work sits equally in Policy & Regulatory, in terms of setting KYA and mandate rules for payment agents, and in Authorisation, Supervision & Enforcement, in terms of checking agents against those rules once deployed; the solution covers both.

Card payments have always run on a person clicking pay. Agentic commerce changes that: a payment agent is given a budget and a purpose, then decides for itself when, how much, and with whom to transact, without a human present for each decision. Supervising a click is straightforward, a discrete, logged action a human took. Supervising a decision is not: no standard KYA rules exist yet for how a payment agent should decide, or for a regulator to check that decision against.

Industry has moved to fill that gap on its own. Mastercard's Agent Pay, Visa's Trusted Agent Protocol, and Google's AP2 (2025, sixty-plus partners including both major card networks) each bind a signed token to a named agent and a recorded consent. In July 2026 Singapore's MAS published SAFR, developed with Visa, Mastercard, Ant International, HSBC, and J.P. Morgan, sorting every proposed agent action into one of four dispositions before execution; SAFR describes itself as an industry reference, not supervisory guidance. These are private answers to what is really a public-infrastructure question, and the public sector has not kept pace building the equivalent.

Decision-making like this needs supervision, like any other autonomous financial process. Supervision of conventional AI and machine learning models is already uneven: most authorities stop at a policy check, and the National Bank of Georgia is one of the few that goes further, with full technical validation before a model is deployed. Agentic payments has none of this, and no supervisory framework exists. Academic red-teaming cited in this hackathon's materials shows why: a fully valid, signed AP2 mandate still carried a transaction its user never authorised, via prompt injection against the agent assembling the cart, the decision-making was compromised even though every credential checked out.

What oversight exists today was built around authorisation, licensing, and documentation review, enough for a click, one human choosing one action, but not for an agent making that same kind of choice repeatedly on its own. Without detailed KYA rules written for agents, and ongoing assessment of how each one actually behaves, agents misbehave: drifting outside their budget or purpose, transacting with unauthorised counterparties, structuring payments under reporting thresholds, or being manipulated into acting outside their mandate. A regulator needs to be able to assess this directly, not infer it from a policy document filed once a year.

Consumers bear the loss when an agent acts outside its mandate, since it has no legal identity to hold liable; firms carry fraud risk on transactions they often cannot fully inspect; and markets are exposed to correlated agent behaviour a firm-by-firm review is unlikely to catch. Regulators need a tool that does two things: lets them set and test KYA and mandate rules for payment agents in a sandbox before publishing them, and then lets them supervise agents against those rules from the batch transaction history agents actually generate, not a periodic policy review. That is what Mandate Supervisor is built to do.

## 2. The Proposed Future Agentic State (Solution)

**Workflow:** Mandate Supervisor continuously oversees how AI payment agents actually behave, not just whether their paperwork is in order: it checks an agent's real activity against what it was authorised to do, on an ongoing basis rather than once at onboarding, on synthetic data, NayaOne's where available, our own generated AP2-shaped data where it isn't.

A firm's AP2 mandate chain (Intent, Cart, Payment) and transaction logs arrive as a routine submission. Ingestion verifies each signature and normalises the record; deliberately not an agent, since the check is deterministic. The Orchestrator agent reads the case and the active KYA ruleset, decides which checks it needs, and dispatches four specialist agents in parallel (below), then combines their findings into a weighted score mapped onto SAFR's four dispositions; escalated or denied cases go to the Report drafting agent, which drafts a supervisory query grounded only in structured findings, never raw firm text, for a named human to review, edit, or block.

**Mandate agent:** Confirms the Cart stayed within the Intent's declared scope and the Payment's hash still matches.

**KYA agent:** Checks the credential's signature and issuer against the ruleset, and the delegation chain back to a human.

**Log agent:** Scans transaction history for structuring and unusual counterparty clusters.

**Drift agent:** Compares current behaviour to the agent's own baseline, catching a slow drift no single transaction would flag.

**Architecture:** Orchestrator-worker pattern, built as microservices rather than a monolith, so each agent, and the mandate protocol or KYA ruleset it reads, can be swapped or upgraded independently, AP2 today, a different protocol later, without touching the rest of the pipeline. Agents never message each other directly; each reads and writes typed records to a shared, append-only case ledger, which makes every run replayable and every finding citable.

**Tools & data:** Each agent calls only the tools its role needs (mandate verification, credential lookup, pattern analysis, ruleset lookup), permissioned per agent. Rules are not code: the registry holds versioned KYA/mandate rulesets tagged by source and status (active, draft, retired).

**Autonomy boundaries:** Agents choose which checks to run and in what order, but tool access is dispatcher-permissioned, not prompt-instructed, and no drafted action reaches a firm without named human sign-off. Policy sandbox mode runs this same pipeline in an isolated environment against an editable, draft copy of the rules registry, so a regulator can iterate on candidate KYA rules before promoting them to active; only the ruleset changes, never the agents.

**Models & grounding:** The drafting agent sees only structured findings and score factors, never a firm's free-text submission, closing the main prompt-injection route. A grounding check confirms every claim cites a finding that actually exists.

**Evaluation:** Precision and recall of each specialist agent against the labelled dataset's ground truth; false-positive rate on a clean control firm; adversarial testing of the drafting agent to confirm the grounding check holds.

**End users:** Payments/fintech supervision case officers, who triage a prioritised queue instead of a raw transaction dump, and the policy team that owns KYA rule-setting, who use policy sandbox mode to test a candidate rule before publication, answering the standard-setting gap in section 1.

## 3. Approach & Delivery Plan

By 8 September we can realistically build: ingestion/validation against synthetic AP2 data, NayaOne's where available, our own generated data where it isn't; the Orchestrator and all four specialist agents, rule logic driven by the rules registry rather than hardcoded thresholds; the risk-scoring agent emitting SAFR-shaped dispositions; the drafting agent with its grounding check; a minimal human-review queue; and the audit ledger. Policy sandbox mode needs no new agents, since it is the same pipeline pointed at an editable, isolated ruleset copy, making it the first extension we would add.

Cut first if short on time: the cross-agent correlation check, and dashboard polish.

Post-hackathon, the priority is expanding the KYA ruleset library well beyond what a hackathon can cover, bringing in real candidate rules from regulators, firms, and standards bodies, alongside integrating with an actual regulatory reporting channel and pursuing formal alignment with SAFR's Controls Repository.

## 4. Risks & Guardrails

**Hallucination:** The drafting agent could invent a finding. Mitigated by grounding: it sees only structured findings, never raw text, and a check confirms every claim cites an existing finding ID.

**False positives & bias:** Explainable, factor-level scoring rather than an opaque number, reviewed by a human, so a wrong flag is caught before it reaches a firm.

**Prompt injection:** A firm's submission could contain manipulative text. Ingestion is deterministic, not an LLM, so it never reaches a model at entry; agents treat submitted content as data, not instructions.

**Over-reliance:** No action leaves the system without named human sign-off, and ruleset promotion requires a separate human decision.

**Data sensitivity:** Synthetic data only; no live rail access.

**Guardrails:** Human-in-the-loop at two gates (draft-to-send, ruleset promotion); auditability via a hash-chained, append-only ledger; safety via dispatcher-enforced, least-privilege tool permissions, plus a manual stop on any run.

## 5. Team

National Bank of Georgia. Sandro Gogaladze (Senior AI Engineer) and Tatia Tsiklauri (Senior AI & Data Engineer) build the agent pipeline; Ana Dvaladze (Lead Specialist), Mariam Kvaratskhelia (Chief Specialist), David Bochorishvili (Head of R&D Division), Varlam Ebanoidze (Head of Fintech and Suptech Development Department), and Vasil Shengelia (Head of Open Finance Ecosystem and Financial Innovation Development Division) bring the regulatory and research perspective.

## Diagram note

Figure 1 (multi-agent system architecture) in the original submission shows: Synthetic regulatory data → Ingestion & validation (deterministic) → Orchestrator agent (reads rules registry) → four parallel specialists (Mandate, KYA, Log, Drift) → Risk scoring agent → Report drafting agent → Human supervisor review (approves/edits/blocks, informed by the audit log) → Supervisory action sent (only a human can send). The Rules registry and Policy sandbox run alongside as oversight tooling, feeding the Orchestrator.
