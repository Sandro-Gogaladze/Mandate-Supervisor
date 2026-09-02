# KYA rules and the policy sandbox — what's real, who sets it, and what we can honestly claim

Positioning note. Answers four questions that determine how we should write and speak about this
project: is "KYA" a real term, who sets KYA rules, is the sandbox claim defensible, and where SAFR
sits relative to us.

**Short version.** KYA is a real and current term, but it is **vendor-originated industry vocabulary,
not regulatory language, and no regulator anywhere has published KYA rules.** That vacuum is the
entire opportunity and it validates the concept note's central claim. The sandbox is defensible —
it is standard AML rule-tuning practice pointed at the regulator's own rulebook — but **two phrases in
the proposal overclaim and should change.**

---

## 1 · Is "KYA" even a term?

**Yes, and it's current.** Know Your Agent is established enough in 2026 to have vendor products,
analyst coverage and trade-press explainers behind it: Experian, Nuvei and PYMNTS all publish on it,
and there are practitioner "blueprints" circulating.

**But note where it came from.** The term originated as *product naming* — Skyfire's KYAPay in 2024 —
and broadened into an ecosystem label from there. Visa, Mastercard and Cloudflare solve the same
identity problem in their own specifications without using the label.

**What this means for us, precisely:**

- **"Know Your Agent" as a concept** — real, recognisable, safe to use.
- **"KYA rules" as a rulebook** — **does not exist anywhere.** There is no KYA standard, no standards
  body owns it, and no financial regulator has published KYA requirements. What exists is *emerging
  industry consensus*, borrowing structure from NIST's AI Risk Management Framework (governance
  vocabulary) and NIST SP 800-63 (identity assurance levels) — neither of which is KYA-specific.

**Recommendation on language.** Keep "KYA" as the shorthand, because the audience recognises it. But
in formal or regulatory-facing text, lead with what it actually is — **agent identity and
accountability requirements**, or **agent due diligence** — and introduce KYA as the industry term for
it. A central bank adopting a vendor's product name as its regulatory vocabulary is a small
credibility cost for no gain, and the descriptive phrase also says what the rules *do*.

---

## 2 · Who sets KYA rules today?

**Nobody, in any binding public sense.** The de-facto setters, in rough order of influence:

| Who | What they set | Status |
|---|---|---|
| **Card networks** — Visa Trusted Agent Protocol (live Oct 2025), Mastercard Agent Pay (US rollout Nov 2025) | Agent identity bound into the network token; scheme participation requirements | **Scheme rules** — contractually binding on participants, but private ordering, not public regulation |
| **Protocol authors** — Google AP2 | The mandate structure itself: Intent, Cart, Payment, signatures | Open specification, voluntary adoption |
| **Vendors** — Skyfire, Cloudflare, Experian | Product-level identity checks and the KYA label | Commercial |
| **Industry consortia** — MAS/BuildFin's SAFR | The runtime control architecture | **Explicitly not regulation** (see §4) |
| **Borrowed public standards** — NIST AI RMF, NIST SP 800-63 | Governance vocabulary; identity assurance levels | General-purpose, predates agentic payments |

**No financial regulator has published KYA rules.** That is the finding, and it is worth stating
plainly in the pitch, because it is exactly what the concept note already argues:

> *"These are private answers to what is really a public-infrastructure question, and the public sector
> has not kept pace building the equivalent."*

The research supports that sentence as literally accurate rather than rhetorical. **The vacuum is
real.** Card schemes are writing the closest thing to binding agent-identity rules that exists, and
scheme rules bind only scheme participants, are not published for public scrutiny, and answer to
commercial rather than supervisory objectives.

**So who *should* set them?** The defensible position, and the one our architecture already implements:
the **regulator sets a floor** and the **industry standards supply the vocabulary**. Our registry —
versioned rules, `draft`/`active`/`retired` status, human-gated promotion, everything traceable to an
issuing authority — is a governance model for exactly that. **That mechanism, not the specific 33
rules in it, is the contribution.**

---

## 3 · Is the sandbox claim rational and correct?

The proposal says the tool lets a regulator *"set and test KYA and mandate rules… in a sandbox before
publishing them"* and iterate to find good policy. Assessed honestly, in three parts.

### What is fully defensible

**Testing a candidate rule against data before publishing it is established practice with a name.**
In AML it is called **rule simulation or backtesting**, and threshold tuning is done by **above-the-line
/ below-the-line (ATL/BTL) testing** — run the candidate threshold over historical data in a test
environment, generate the alerts it would have produced, and measure what you get. Regulators already
*promote* this and expect firms to do it periodically.

So the sandbox is not a novel or risky idea needing defence. **It is a discipline regulators already
require of supervised firms, turned around and applied to the regulator's own rulebook.** That is a
much stronger framing than novelty, and it is also a slightly pointed one: firms are expected to tune
and evidence their monitoring rules; rulebooks are usually published without the same evidence.

There is also a direct precedent hook: SAFR's own adoption path runs through **industry pilots and
sandbox experimentation** via Singapore's Future of Finance Institute. Sandboxing agent controls is on
the roadmap of the framework we align with.

### What overclaims, and should change

**"Find the best policy measures" does not survive contact with the data.** You cannot discover optimal
policy from seven synthetic cases. Optimality needs real base rates, real volumes, and an explicit
loss function weighing a missed breach against a false positive — none of which exists here. "Best"
also implies an objective nobody has defined: best for whom? Fewest false positives? Highest recall?
Lowest firm burden? Those trade off against each other and the trade is a policy choice, not a
computation.

**Say instead:** the sandbox is a **policy impact assessment** tool. Not *"we find the right rule"* but
*"we see what a candidate rule would do before we publish it."* That is a lower claim, it is true, and
it is the one regulators recognise — **regulatory impact assessment before publication is a formal
requirement in most jurisdictions.**

### One more distinction worth getting right

**Do not call it a "regulatory sandbox."** That term already means something specific and different: a
supervised environment where *firms* test products under temporary regulatory relief. NBG's audience
knows the term in that sense, and using it for something else will read as imprecision.

`CLAUDE.md` already says **"policy sandbox"**, which is right. Keep it. *"Rule impact simulation"* is an
even more literal alternative.

### And a legal precision point

The note says the tool lets a regulator *"set"* rules. **Setting rules is a legal act requiring legal
authority; a tool cannot confer it.** What the tool does is support the *process* — drafting, impact
testing, versioning, promotion with an audit trail. Worth phrasing carefully so a lawyer in the room
doesn't raise it.

### What synthetic data can and cannot demonstrate

| Can prove | Cannot prove |
|---|---|
| **The mechanism works** — change a threshold, re-run, see different findings, with the ledger showing exactly what changed and who changed it | That any specific threshold is correct |
| **Governance works** — draft → test → human-gated promotion → active, fully auditable | Real-world false-positive rates |
| **Rules are genuinely data** — the same pipeline produces different verdicts under a different ruleset with no code change | Firm compliance burden |

Demonstrate the first column. Say plainly that the second needs real submissions. **That honesty is
itself a credibility win** in front of supervisors, who have seen plenty of tools that claim
calibration from toy data.

---

## 4 · What SAFR says, and where we sit relative to it

**SAFR's four components** are agent identity, a **controls repository**, a **disposition engine**, and
an **audit log**. The disposition engine evaluates a proposed action **deterministically** against the
relevant controls and returns one of four outcomes: execute, escalate to a human, reject, or allow
with monitoring.

Three things follow.

**1 · SAFR is explicitly not regulation.** The paper states it *"does not constitute regulatory guidance
or supervisory expectations, nor does it prescribe or anticipate future directions for such guidance
or expectations."* It is an industry framework, developed jointly by financial institutions under MAS's
BuildFin.ai initiative.

**So do not say "we implement SAFR" or "we comply with SAFR."** Say we **align** with it — and then make
the sharper point: **SAFR is the industry's answer, and it explicitly leaves the supervisory layer
empty. That empty layer is what we are building.** SAFR itself disclaiming any supervisory role is the
strongest available evidence that a supervisory tool is needed and that nobody is building it.

**2 · SAFR sits inside the firm; we sit outside it.** SAFR is a runtime checkpoint between the agent and
execution — it stops a bad action *before* it happens, at the firm. Mandate Supervisor reviews what
actually happened, at the regulator, afterwards. **These are complementary, not competing**, and the
relationship maps exactly onto our Control Assurance agent (E1): SAFR is the control, and we check
whether the control worked. A firm running SAFR produces precisely the controls-repository and
audit-log data our `controls` submission block asks for.

**3 · The controls repository is the same idea as our registry**, one layer down. SAFR's stores the
rules used to evaluate agent actions inside a firm; ours stores the rules used to evaluate a firm's
agents from outside. The public material doesn't specify who populates SAFR's repository, but the
architecture implies the institution does — which is exactly why the supervisory question *"did your
controls fire?"* has no answer without someone outside asking it.

**One concrete alignment gap to close.** SAFR's disposition engine has **four** outcomes and our
scoring has three tiers. Adding `monitor` (per the coverage model) makes the alignment claim literally
true rather than approximately true — and a judge from MAS or a SAFR contributor will know the
difference.

---

## Recommended wording changes

| Current | Change to | Why |
|---|---|---|
| "KYA rules" *(in formal text)* | "agent identity and accountability requirements (industry term: KYA)" | KYA is vendor-originated product naming; the descriptive phrase also says what the rules do |
| "find the best policy measures" | "assess the impact of a candidate rule before publishing it" | Seven synthetic cases cannot establish optimality; impact assessment is the recognised regulatory frame |
| "regulatory sandbox" *(if used)* | "policy sandbox" or "rule impact simulation" | "Regulatory sandbox" already means firms testing products under relief |
| "set … rules" | "draft, test, version and publish rules" | Setting rules is a legal act; the tool supports the process |
| "we implement SAFR" *(if used)* | "we align with SAFR, and supervise the layer it explicitly leaves empty" | SAFR disclaims any regulatory status — the disclaimer is our argument, not our problem |

## Two lines worth having ready

> **On the vacuum.** "Visa's Trusted Agent Protocol went live in October 2025. Mastercard's Agent Pay
> rolled out that November. Google's AP2 defines the mandate. Not one of them is a public rule — they
> are scheme rules and open specifications, binding on participants and answerable to commercial
> objectives. No financial regulator anywhere has published agent identity requirements. That is the
> gap."

> **On SAFR.** "SAFR is the best thing in this space and it says, in its own words, that it is not
> regulatory guidance and does not anticipate any. It puts a control inside the firm. Nobody is
> checking whether that control worked. We are."

---

## Sources

- [Know Your Agent (KYA) in 2026: the practical standard](https://stablecoininsider.org/know-your-agent-kya-in-2026/) — no standards body owns KYA; NIST AI RMF and SP 800-63 borrowed for structure; no regulator-mandated requirements
- [Nuvei — Know Your Agent: the new control point for agentic commerce](https://www.nuvei.com/posts/know-your-agent-kya-agentic-commerce) · [Experian — What is Know Your Agent?](https://www.experian.com/blogs/insights/what-is-know-your-agent-kya/) · [PYMNTS — The KYA moment](https://www.pymnts.com/artificial-intelligence-2/2026/the-kya-moment-why-knowing-your-agent-is-becoming-table-stakes/)
- [MAS — Safeguards for Agentic Finance at Runtime (SAFR)](https://www.mas.gov.sg/publications/monographs-or-information-paper/2026/safeguards-for-agentic-finance-at-runtime) · [Baker McKenzie analysis](https://www.bakermckenzie.com/en/insight/publications/2026/07/singapore-mas-publishes-agentic-ai-safeguards-for-financial-institutions) — the non-binding disclaimer · [Fintech Singapore](https://fintechnews.sg/133965/ai/mas-agentic-ai/) — the four components
- [Hawk — how rule testing tools improve AML transaction monitoring](https://hawk.ai/news-press/how-rule-testing-tools-improve-aml-transaction-monitoring) · [Flagright — tuning transaction monitoring rules](https://www.flagright.com/post/how-to-tune-transaction-monitoring-rules) — rule simulation, backtesting, ATL/BTL threshold testing
- [FFIEC BSA/AML Examination Manual](https://bsaaml.ffiec.gov/manual/AssessingComplianceWithBSARegulatoryRequirements/00) — supervisory expectations on monitoring-rule effectiveness
