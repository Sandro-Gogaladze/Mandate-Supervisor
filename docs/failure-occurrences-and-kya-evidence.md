# Failure occurrences and the KYA evidence contract

## The three layers

1. `registry/failures.json` is the stable supervisory vocabulary: F1--F73
   and their exact names. It says **what kind of failure exists**.
2. Each versioned rule's `failures` field says which catalogue failure(s)
   that rule detects. A rule and its facts say **what was tested and what the
   evidence established**.
3. `FailureOccurrence` joins a non-clear Assessment to each mapped failure.
   It says **which exact failure happened, under which rule version, on
   which execution runs, supported by which facts and evidence pointers**.

The Assessment and Facts remain the source of truth. An occurrence is a
deterministic projection, not another model judgment. One assessment may
produce several occurrences only where the rule explicitly maps to several
catalogue failures. For a broad judged rule, the Assessment's optional
`failure_ids` narrows that coverage list to the exact failure actually
established; an explicit empty list records the judgment without minting an
unsupported F-occurrence. A rule that maps to no F-id still produces its ordinary
facts, assessment and finding, but no F-series occurrence.

`breach` projects to `detected`; `explained` to `contained`; `concern` to
`possible`; and `inconclusive` to `not_evaluable`. A `clear` assessment is
coverage evidence rather than a failure and produces no occurrence. If one
rule is breached in one run and stopped by a blocking control in another,
the record contains two occurrences. That distinction prevents the UI or a
report from saying a stopped attempt executed.

## What KYA receives

KYA runs once over the dossier, not once per payment run. Its mandatory
context is `KYAEvidenceBundle`, a whole-dossier but domain-bounded view:

- the exact KYA ruleset id/version and every rule's status, evaluation mode,
  weight and F mappings;
- an index for every rule result with counts, fact ids and run refs;
- every breach, absence and measurement fact in full (including statements,
  values and structured evidence refs); clean per-run facts are compressed
  into the result index;
- current credential, credential history and delegation termini;
- the regulator's agent, operator, issuer and relevant model-blocklist
  records;
- activity measurements and one identity summary per run (principal, agent,
  declared model, purpose, trigger, outcome and human-presence requirement).

This is enough for the model to reason over deterministic rule outcomes and
to hunt for new KYA-domain anomalies. It does not include eval ground truth,
raw merchant text, carts, tool result excerpts or unrelated specialist data.
Those belong to other agents and would increase cost while weakening the
domain boundary. The exact composed bundle and its digest are recorded in
the dispatch event before the model call.

## The shared contract for every specialist

Every other specialist keeps its existing domain projection and receives the
same `evidence_contract` alongside it. The contract contains the exact
specialist and skill, review scope and run ids, ruleset id/version/date, full
rule inventory and F mappings, an index of every produced rule result, and
every breach, gap and measurement fact in full. Clean outcomes are compressed
to counts and run refs; repeating thousands of deterministic clean fact ids
would add cost without adding evidence.

The domain projection supplies the material that differs by specialist:

- Mandate: signed request against cart/payment content per run.
- Consent: every run's ceremony, rendered values, signed cart and selection
  alternatives.
- Provenance: every run's declared/observed model, policy release and bounded
  tool-call identity metadata; Injection gets all bounded content channels.
- Counterparty: payee profiles, registry reconciliation and decline timeline.
- Log and Drift: candidate clusters, distributions, baselines and change
  points computed before the model call, plus a compact transaction-to-run
  index so a model verdict can name the exact affected transactions and runs.
- Control Assurance: peer breach facts, declared controls and every control
  execution.
- Systemic: bounded portfolio identities, models, counterparties and counts.
- Red Team: declared controls, generated probe results and rulebook versions.

Potentially submitted free text inside common facts is delimited as untrusted
evidence before entering a model prompt. The canonical domain projections keep
their existing stronger channel-specific delimiters. Ground truth is excluded
from every contract and locked by tests.

Systemic F57/F67/F69 are an intentional exception to rule-backed occurrences:
they are properties of multiple firms and therefore have no fabricated
per-firm rulebook. Their typed occurrences cite the systemic assessment,
portfolio case refs and measurement fact, with `rule_id` and
`ruleset_version` null.

Broad reconciliation checks are intentionally not mapped to several precise
failure ids merely because they discuss the same area. `CPT-IDN-01` does not
turn every doubtful payee into F51+F52+F53; the specific deterministic rules
own those occurrences. Likewise `PRV-REC-01` does not turn every source
disagreement into F33+F36+F37. `PRV-CRD-01` is about the subject agent's filed
card and is not F34, which requires a counterparty discovery card the current
data contract does not contain.

Injection's regex and schema-hash checks are triage signals, so they likewise
do not directly mint F32 (whose definition says the agent *acted*). The judged
`INJ-ACT-01` assessment selects F32 for an affected run and F35 for sustained
objective redirection. Control Assurance consumes those judged, narrowed
assessments as well as deterministic facts; it no longer has to pretend an
exposure heuristic was a completed failure in order to evaluate a control.

The Log agent's open-ended hunt can return typed, unverified candidates for
F62/F63/F64/F66 with validated transaction and run refs. They remain
`Observation`s: named and reviewable, but deliberately unscored until a rule
is promoted. A Log or Drift anomaly that names no valid transaction is marked
inconclusive rather than projected as a location-free failure. F65 is only
projected when the drift also lands on a real change-log event, because that
specific causal link is part of F65's definition.

Portfolio occurrences additionally retain `run_refs_by_case`, so identical
run-id formats at two firms cannot erase which execution belonged to which
dossier.

## Citation path

The auditable path is:

`F42 occurrence -> MND-CAP-01 assessment -> fact ids -> run refs + evidence refs`

The API exposes `failure_occurrences` on both the case and the producing run.
The Results panel lists the exact F-id/name, status, affected runs, rulebook
version and supporting fact count. The underlying event
`failure_occurrence_recorded` keeps the same data in the append-only ledger.
