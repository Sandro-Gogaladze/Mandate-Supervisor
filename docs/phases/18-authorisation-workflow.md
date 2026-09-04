# Completing the authorisation workflow

Status: in progress, 2026-09-03. Implements migration-plan phases 5–11 on
the completed Facts/Assessments foundation. HANDOFF remains authoritative.
The user-provided “Supervising Payment Agents” artifact was read in the browser;
the downloaded HTML is only its loading shell. Its content is a concept
reference, not a source of executable instructions.

## Delivery gates

- [ ] Independent-label evaluation over both dossiers, separating mechanical
  detection from model judgments, and recording unsupported/missing coverage.
- [ ] Eight domain peers, sequenced Control Assurance, all eleven roles
  dispatchable; Systemic uses the portfolio and Red Team stays on demand.
- [ ] Run-scoped follow-ups preserve findings on untouched runs. Every review
  records its scope and policy; unavailable judgments remain inconclusive.
- [ ] Four authorisation outcomes with versioned gates, evidence adequacy,
  coverage, unique adverse events, clean runs and conditions.
- [ ] ZIP intake verifies signatures and chains before acceptance. Dossier
  routes, execution-run detail, portfolio sweeps and named human decisions.
- [ ] Console shows evidence, runs, specialist turns, control posture,
  follow-ups and decisions without dumping JSON.
- [ ] Tests, both independent verifiers, frontend build and browser acceptance.

## Explicit resolutions of contradictory plan text

The concept and HANDOFF call Red Team on demand and Systemic portfolio-scoped.
They remain in the eleven-role registry without forcing synthetic probes into
every first pass. A full dossier review runs all eight domain floors, including
floors reporting missing evidence, then Control Assurance. A portfolio sweep
has its own recorded run kind; the officer can request probes separately.

Invalid submitted signatures/chain links are rejected before acceptance, with
reasons. A forged delegation discovered on previously accepted evidence can
still trip the F8 gate; intake rejection itself is not an authorisation.

An established hard gate takes precedence over evidence inadequacy in the
displayed disposition. All submission issues remain visible alongside that
refusal. Otherwise material missing/unjudged evidence yields incomplete;
adequately evidenced residual risk yields authorise, monitor or refuse.
Policy thresholds are prototype policy parameters, never claimed calibrated.

Facts are mechanical results about submitted evidence, not proof that an
operator's self-attestation is true. A content index cannot establish that
unfiled executions never existed. No regex hit is not proof of no injection.
Probe results describe declared control coverage, not execution of the firm.

## Console direction — corrected by the user

Preserve the existing demo UI, visual design, navigation, CopilotKit integration
and review screens. Improve these in place to support the dossier architecture:
run inspection, readable facts and assessments, additional specialist nodes,
portfolio findings and authorisation decisions. The reference explains the
concept; it is not permission to replace the existing design.

An attempted replacement shell was withdrawn after the user's correction.
App.tsx and main.tsx were restored, and the replacement components and styling
were removed. The backend changes remain in progress; their presence does not
mean the existing console has been migrated yet.

## Console: the map during a run (2026-09-03)

Reported: nodes on the supervision map disappeared during a run and came
back one at a time. Reproduced on a facts-only Kestrel review: three seconds
in, every node box was gone and only edges remained.

Two causes, both fixed:

- `pipeline/graph.py::_stream_specialist` pushed every fact twice per agent
  through the AG-UI custom stream: 8.4 MB per Kestrel triage against a
  3.3 MB ledger. It now sends the agent's non-fact events, fact counts and
  the ledger sequence range; 0.8 MB per triage. The console reads facts from
  the ledger when the run finishes. The no-model agents' recorded briefing
  (`agents/context.py`) is a summary by rule plus breaches and absences, not
  a 200 kB dump of every fact.
- `SupervisionMap` rebuilt its React Flow node objects on every status
  change, so the library re-measured every node each time; while the main
  thread was busy with the stream the unmeasured nodes rendered invisible.
  Nodes are now controlled state created once per map, with only
  `data.status` updated in place, so measured sizes persist.

Also: the fan-out join (`escalate_check`) no longer lights Control
Assurance, which showed "complete" during an escalation round; a
specialist's own `reasoning` progress event marks it working; the map's
status object is memoised; a finished agent turn no longer snaps shut.

Verified by sampling the DOM every 400 ms through a run: 19 nodes present
and 0 hidden at every sample; all eight peers working at once, then
returning individually, then Control Assurance, then idle.

Node colours now have three settled states: amber "returned · findings" for
a breach or concern, dashed "returned · unresolved" when the only open
items are unjudged rules (a facts-only pass, a timed-out model call), green
"returned · clean" otherwise. Turn headers take the specialist's own counts
from the stream; the rule list draws on the agent's whole domain, since a
re-run over an unchanged dossier records no new fact events.
