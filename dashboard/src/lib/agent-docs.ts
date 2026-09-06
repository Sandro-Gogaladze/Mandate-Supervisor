/**
 * Reference pages for the ten specialists — docs/explainer/07-the-agents.md
 * and 05-the-failure-catalogue.md, written for a reader who will never open
 * the code.
 *
 * Only the prose lives here. Everything countable — the rules each one runs,
 * their thresholds, the failures it owns — is fetched live from the registry
 * (`/sandbox/rulebook/<domain>` and `/failures`) so these pages cannot drift
 * out of step with the rulebook actually in force.
 */
export interface AgentDoc {
  /** The one supervisory question this specialist owns. */
  question: string
  /** Lifecycle phase from the failure catalogue, and what happens in it. */
  phase: { id: string; title: string }
  /** Rulebook ref for the live rule table — null where the agent has none. */
  rulebook: string | null
  /** Key used by the failure catalogue's `domain` field. */
  failureDomain: string | null
  /** Which blocks of the submission it is given. */
  receives: string[]
  /** What it decides in code, with no model involved. */
  floor: string
  /** Its single contained model call, or null where it makes none. */
  model: string | null
  /** What it hands back to the case record. */
  produces: string
  /** Things a reader should know that the rule table cannot show. */
  notes: string[]
}

export const AGENT_DOCS: Record<string, AgentDoc> = {
  mandate: {
    question: 'Was this within what the human signed?',
    phase: { id: 'P3', title: 'The mandate is signed' },
    rulebook: 'mandate',
    failureDomain: 'mandate',
    receives: [
      'The Intent Mandate — the shopper’s sentence, the authorisation scope (caps, currency, categories, counterparties, geography, validity window), and its signature',
      'The Cart Mandate — merchant, line items, total, the agent’s attestation, and its hash link back to the Intent',
      'The Payment Mandate — amount, method, settlement status, and its hash link back to the Cart',
    ],
    floor:
      'Every computable rule in the Mandate Fidelity rulebook: spending caps, scope of category and counterparty, currency, the validity window, single-use draw, and the integrity of each hash link in the chain.',
    model:
      'Per-line-item intent fidelity — does this cart answer this shopper’s sentence? It sees the sentence and the line items, nothing else, and returns one verdict per run. Code does the enforcing: a run id the model invents is dropped and logged, and a run it declines to judge is recorded as inconclusive rather than quietly passed.',
    produces:
      'A fact per rule evaluated, plus judged assessments that must cite the runs they are about — an assessment naming no run is rejected by the schema.',
    notes: [
      'The semantic check is deliberately independent of the floor’s line-item injection heuristic. Two mechanisms, so a manipulated semantic check does not leave injection detection with a single point of failure.',
      'Checking a cart against a three-month spending envelope is nearly vacuous — almost anything passes. Checking it against “vitamin C serum, around $50” is not. This is why the mandate lives on the run.',
    ],
  },
  kya: {
    question: 'Is authority traceable to a human?',
    phase: { id: 'P0', title: 'The agent comes into existence' },
    rulebook: 'kya',
    failureDomain: 'kya',
    receives: [
      'The agent’s identity credential — issuer, validity dates, revocation check, granted capabilities, and its Ed25519 signature',
      'The delegation chain, level by level, with the capabilities granted at each',
      'The credential history for this agent',
      'The regulator’s own registers: accredited issuers, the agent register, operator records, and the public keystore',
    ],
    floor:
      'The largest rulebook in the system, organised into eight families so a rule id is readable: IDN (is the identity cryptographically sound), ISS (is the issuer accredited and current), ACC (does authority trace to an accountable human), OPF (is the operator fit), REG (is the agent declared and classified), TEC (is the technical substrate declared), CAP (are its capabilities proportionate), LIF (is the credential lifecycle sound). Signatures are verified with real Ed25519, not string comparison.',
    model:
      'Two narrow judgements only: whether an issuer name closely resembles an accredited one without being it, and whether observed activity fits the classification the agent was declared under.',
    produces: 'Facts for every rule in the rulebook, plus the credential-series pass across the agent’s credential history.',
    notes: [
      'An AI agent has no legal identity. It cannot be fined, sued, struck off or called to a hearing. If authority does not trace back to a human or a liable entity, the consumer absorbs the loss by default — which is the whole reason this specialist exists.',
      'Almost a third of the failure catalogue sits in this phase: whether the agent should have existed at all, before it spends anything.',
    ],
  },
  provenance: {
    question: 'Were the inputs to this decision trustworthy?',
    phase: { id: 'P2', title: 'The agent assembles a cart' },
    rulebook: 'provenance',
    failureDomain: 'provenance',
    receives: [
      'The construction context — the declared model version beside the version actually observed, the prompt release reference and its hash',
      'Every tool call: server id, schema hash, arguments, and a digest of the result',
      'The published agent card and its hash',
      'The regulator’s register of authorised tool servers and barred models',
    ],
    floor:
      'The provenance half of the TEC family, which keeps its original rule ids, plus the tool-server and prompt-release checks. Ownership here is assigned by evidence, not topic: TEC-01/03/04 are answered from the agent register and belong to KYA; TEC-02/05/06 are answered from the construction context and belong here.',
    model:
      'Reconcile four sources that should agree — the agent card, the credential, the regulator’s register, and the tool calls actually observed — and name the odd one out.',
    produces: 'Facts on the declared-versus-observed substrate, and one judged reconciliation naming which source disagrees.',
    notes: [
      'One field carries most of the weight: `observed_version` sitting beside `declared_version` turns “we use an approved model” from an assertion into a check.',
      'Splitting rules by evidence rather than topic removed a real double-count before it existed — the same failure asserted twice by two agents and scored twice.',
    ],
  },
  injection: {
    question: 'Was it manipulated by what it read — and through which channel?',
    phase: { id: 'P2', title: 'The agent assembles a cart' },
    rulebook: 'injection',
    failureDomain: 'injection',
    receives: [
      'Four channels of firm-authored text, each delimited: the customer prompt, tool-call result excerpts, line-item descriptions, and merchant policy text',
      'The schema hash recorded for each tool call',
      'The selection context — what the agent searched for, what it chose, and what it passed over',
    ],
    floor:
      'Regex triage across all four text channels, plus comparison of each tool call’s schema hash against the one on record.',
    model:
      'Whether the agent actually acted on what it read, and through which channel — because the supervisory question is not “was there a payload” but “where is sanitisation leaking”.',
    produces: 'A fact per channel triaged, and a judged assessment naming the channel through which an instruction reached the decision.',
    notes: [
      'Valid signatures cannot catch this. AP2’s cryptography covers the moment of signing, and this attack lands on the step before anything is signed — a fully valid, correctly signed mandate carrying a transaction the customer never asked for.',
      'This is the one place firm-authored free text reaches a model. It is delimited, the output is schema-constrained, and it is separately flagged by heuristics that need no model at all.',
    ],
  },
  counterparty: {
    question: 'Who received this money?',
    phase: { id: 'P4', title: 'The payment executes' },
    rulebook: 'counterparty',
    failureDomain: 'counterparty',
    receives: [
      'The payee block — settlement account, scheme, country, and beneficiary name',
      'The cart’s merchant: id, MCC, country, region, and any sub-merchant',
      'The wider transaction ledger, for concentration and decline history',
      'The regulator’s merchant register, including who really owns each merchant',
    ],
    floor:
      'Payee checked against the merchant register, sub-merchant disclosure, concentration statistics across the ledger, and decline timelines.',
    model:
      'Whether this payee is what it appears to be — name-against-account mismatch, a front — and whether the declines cluster into probing rather than bad luck.',
    produces: 'Facts on payee resolution and concentration, plus judged assessments on apparent fronting and decline patterns.',
    notes: [
      'Who the merchant was and where the money actually went are two different questions. A marketplace can hide the real seller, so the payee block is checked separately from the cart.',
      'Merchant ownership is held regulator-side. An operator submits what it paid; it does not get to supply who owns the recipient.',
    ],
  },
  consent: {
    question: 'Was the human actually there, and is the consumer worse off?',
    phase: { id: 'P1', title: 'A human authorises it' },
    rulebook: 'consent',
    failureDomain: 'consent',
    receives: [
      'The consent ceremony — whether it occurred, its scope, method, the values actually rendered on screen and their hash, and any superseded consent',
      'The signed cart, to compare against what was shown',
      'The selection context — what the agent considered and what it chose',
    ],
    floor:
      'The rendered values checked against the signed cart, ceremony scope against what was authorised, and consent supersession.',
    model:
      'Value for money assessed against the selection context — the detectable signature of merchant-bias tuning, where the agent had a cheaper equivalent in front of it and chose otherwise.',
    produces: 'Facts on the ceremony and the rendered-value comparison, plus a judged assessment on consumer detriment.',
    notes: [
      'The consent screen said $54.99; the signed cart says $329.00. Nothing else in the mandate chain can catch that — only the values actually rendered, recorded and hashed at the moment of consent.',
    ],
  },
  log: {
    question: 'What does the history reveal?',
    phase: { id: 'P5', title: 'Many payments accumulate' },
    rulebook: 'log',
    failureDomain: 'log',
    receives: [
      'The full transaction ledger — deliberately broader than the runs submitted for review',
      'Timestamps, amounts, counterparties and outcomes for every transaction in the window',
    ],
    floor:
      'Statistics, computed with pandas and no model at all: structuring under reporting thresholds, velocity, roundness, off-hours activity, and counterparty concentration.',
    model:
      'Narrate numbers that have already been computed, and judge whether a given cluster is benign. The measurements are mechanical; only the verdict is judged.',
    produces: 'Measurement facts for every statistic computed, and judged assessments that must cite them.',
    notes: [
      'Every rule in this domain is judged rather than computable — structuring, concentration and velocity are patterns where the numbers are mechanical and the verdict is not. Every judged rule has measurements standing behind it, and the critic enforces that contract.',
      'No single payment reveals structuring. That is the point of submitting the wider ledger rather than only the runs under review.',
    ],
  },
  drift: {
    question: 'What changed, and when did it start?',
    phase: { id: 'P5', title: 'Many payments accumulate' },
    rulebook: 'drift',
    failureDomain: 'drift',
    receives: [
      'The transaction history, split into a baseline period and a comparison period',
      'The agent’s change log — model updates, prompt releases, policy changes, with dates',
    ],
    floor: 'The baseline/comparison split and change-point detection over amounts, cadence and counterparty mix.',
    model: 'Which change-log event sits at the onset boundary — what changed about the agent at the moment its behaviour did.',
    produces: 'A measurement fact for each detected change point, and a judged assessment linking onset to a change-log entry.',
    notes: [
      'Nothing is wrong on any given day, and the agent is a different agent by the end of the quarter. Drift is the failure mode no per-transaction check can see, because every individual transaction is fine.',
    ],
  },
  control_assurance: {
    question: 'Did the firm’s own controls work?',
    phase: { id: 'X1', title: 'Cross-cutting — the firm’s own controls run' },
    rulebook: 'control_assurance',
    failureDomain: 'controls',
    receives: [
      'The controls the operator and the institution each declare they run',
      'Per-run control outcomes — passed, triggered, or not applicable — and any override, with who, why and when',
      'The breach facts every other specialist produced on this submission',
    ],
    floor:
      'The Control Assurance rulebook, evaluated against the peers’ facts. Posture is computed, not judged: absent (the mandate creates a risk and no declared control addresses it), failed (a control rejected the action and the payment settled anyway), bypassed (a control fired and a named person overrode it into settlement), ineffective (a control recorded a pass on a run where its own risk breached), or effective (it fired and held).',
    model: null,
    produces: 'A posture per declared control, with the peer facts that establish whether the risk materialised.',
    notes: [
      'This is the one that makes the system a supervision tool. Every other specialist asks whether the agent misbehaved; this one asks whether the firm’s declared controls did their job — which is the question a supervisor is actually empowered to act on.',
      'Posture falls out of the facts, so no model is needed to decide it and none is called. A control that rejected an action and saw the payment settle anyway failed; one overridden into settlement was bypassed, by a named person; one that recorded a pass on a run where its own risk breached was ineffective.',
      'It runs after the peer fan-out, never inside it. Its central rule asks whether a control that should have fired did, which means knowing the risk materialised — somebody else’s finding. Given no peer findings it stays silent, and there is a test asserting exactly that.',
      'It learns what materialised purely from the peers’ breach facts, through each rule’s own failure declaration. No agent messages another.',
    ],
  },
  systemic: {
    question: 'What is true across the whole portfolio?',
    phase: { id: 'P6', title: 'Many agents act at once' },
    rulebook: null,
    failureDomain: 'systemic',
    receives: [
      'Every submission on record, not just the one under review',
      'Payees, model identifiers and prompt digests across all of them',
    ],
    floor: 'Shared-payee, model-monoculture and shared-digest sweeps across submissions. No rulebook of its own — its detectors are the sweeps themselves.',
    model: null,
    produces: 'Cross-submission findings, recorded on every case they span — each one naming the other submissions it rests on.',
    notes: [
      'This is the only specialist whose question cannot be asked of one submission — and the one capability a supervisor has that no single firm does. A firm cannot tell that the merchant it just started paying is also being paid, that same week, by three other firms’ agents.',
      'The hard part is not finding shared counterparties; most are shared, because popular retailers are popular. Separating suspicious overlap from ordinary commerce is done by reading concentration and recency, not mere presence — which is why the sweep needs no model.',
      'Everything it reports is computable from submissions already filed. It asks nothing new of any firm; it only needs somewhere to look from.',
    ],
  },
}
