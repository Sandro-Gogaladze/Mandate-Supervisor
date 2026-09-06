import { useEffect, useState } from 'react'
import { BadgeCheck, Gauge, ShieldAlert, TriangleAlert, UserRoundCheck } from 'lucide-react'
import { toast } from 'sonner'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { signAuthorisation } from '@/lib/api'
import { DISPOSITION_LABEL, type Disposition, type DossierDetail } from '@/lib/supervision-types'
import { RunCitation } from '@/components/AgentTurn'
import { TIER_TONE } from '@/components/ResultsPanel'
import type { GateContext, GateSubmission, RiskScore } from '@/lib/types'
import { cn } from '@/lib/utils'

/** Severity as ink. A reviewer signing their name to a disposition needs to
 * see at a glance whether they are looking at one serious breach or a dozen
 * marginal ones, and a list of identically-weighted rows cannot show that. */
function severityTone(severity: number): string {
  if (severity >= 0.85) return 'border-red-500/50 bg-red-500/[0.10]'
  if (severity >= 0.7) return 'border-red-500/35 bg-red-500/[0.06]'
  if (severity >= 0.5) return 'border-amber-500/40 bg-amber-500/[0.06]'
  return 'border-amber-500/25 bg-amber-500/[0.03]'
}

function BreachedRules({ report, onOpenRun }: {
  report: NonNullable<DossierDetail['recommendation']>
  onOpenRun: (run: string) => void
}) {
  // A hard gate is a breach that no amount of good behaviour offsets, so it
  // belongs in this list marked, not in a separate box above it.
  const gated = new Map(report.hard_gates.map((g) => [g.assessment_id, g.reason]))
  const rows = [...report.factors].sort((a, b) => {
    const gate = Number(gated.has(b.assessment_id)) - Number(gated.has(a.assessment_id))
    return gate || b.severity_assessed - a.severity_assessed
  })
  if (!rows.length) return null
  return (
    <div>
      <h4 className="text-sm font-semibold">Breached rules · {rows.length}</h4>
      <p className="mb-2 mt-0.5 text-xs text-muted-foreground">
        {(() => {
          const runs = new Set(rows.flatMap((f) => f.run_refs)).size
          const caseWide = rows.filter((f) => !f.run_refs.length).length
          // Deliberately spelled out: this counts rules, the Submission tab
          // counts runs, and the two will not match.
          return `Rule breaches, not runs — ${runs} run${runs === 1 ? '' : 's'} affected` +
            (caseWide ? `, and ${caseWide} that concern the agent rather than any single run.` : '.')
        })()}
      </p>
      <div className="space-y-1.5">
        {rows.map((f) => {
          const reason = gated.get(f.assessment_id)
          return (
            <div key={f.assessment_id} className={`rounded-lg border px-3 py-2 ${severityTone(f.severity_assessed)}`}>
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                <span className="font-mono text-[12px] font-semibold">{f.rule_id ?? f.agent}</span>
                {reason && <Badge variant="destructive" className="text-[9px] uppercase">Hard gate</Badge>}
                <span className="text-[11px] uppercase tracking-wide text-muted-foreground">{f.agent.replaceAll('_', ' ')}</span>
                <span className="ml-auto font-mono text-[11px] text-muted-foreground">severity {f.severity_assessed.toFixed(2)}{f.confidence !== 'certain' && ` · ${f.confidence}`}</span>
              </div>
              {reason && <p className="mt-1 text-[13px] leading-5">{reason}</p>}
              {f.run_refs.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-2">{f.run_refs.slice(0, 8).map((run) => <RunCitation key={run} run={run} onOpenRun={onOpenRun} />)}{f.run_refs.length > 8 && <span className="text-[10px] text-muted-foreground">and {f.run_refs.length - 8} more</span>}</div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}


/** The decision page — the ONE place a case is signed off.
 *
 * Two things are recorded when a case ends, and they are different claims:
 * the authorisation (`authorisation_decided` — what happens to this agent)
 * and the report gate (`decision_recorded` — whether the drafted document
 * issues). They stay separate on the ledger, because collapsing them would
 * lose audit, but they were separate FORMS too: two reviewer-name fields that
 * could disagree, two justification boxes, two "sign" buttons with nothing
 * saying which was the decision, and no enforced order — POST /decision only
 * blocks on an unfinished triage run, so a case could be authorised while its
 * report sat frozen at the gate and be gated later under another name.
 *
 * So: one identity, one rationale, one primary act. Signing a disposition
 * already means accepting the report as its basis (the payload embeds it),
 * so signing issues the report too. The authorisation POST goes FIRST — it is
 * the write that can be refused (stale digest, open hard gate), and a refusal
 * must leave the pipeline still paused rather than a report issued with no
 * authorisation behind it. The two gate actions with no disposition of their
 * own — send it back, reject the draft — stay as secondary controls, because
 * neither is a decision about the agent. */
/** One count in the run tally. A zero is styled like any other number — a
 * greyed-out zero would read as "nothing to see", and on this panel a zero is
 * frequently the most important number on the page. */
/** What "incomplete submission" is actually short for.
 *
 * Two very different things reach this disposition and the label collapses
 * them: the filing genuinely arriving short (S1-S4), and OUR review failing to
 * reach a determinate result on evidence that did arrive (coverage, judgment,
 * evidence). Halcyon is the second kind — 12 target runs filed, 94% rule
 * coverage — and reading "Incomplete submission" alone would send a supervisor
 * back to the institution over a shortfall on our side. So name the origin. */
const ADEQUACY_ORIGIN: Record<string, string> = {
  S1: 'filing', S2: 'filing', S3: 'filing', S4: 'filing',
  coverage: 'review', judgment: 'review', evidence: 'review',
}

function Adequacy({ report }: { report: NonNullable<DossierDetail['recommendation']> }) {
  if (!report.adequacy.length) return null
  const filing = report.adequacy.filter(a => ADEQUACY_ORIGIN[a.code] !== 'review')
  const review = report.adequacy.filter(a => ADEQUACY_ORIGIN[a.code] === 'review')
  // Adequacy is what *produces* an incomplete submission, but it survives a
  // refuse: a hard gate outranks it, so the gaps are still open underneath.
  // Saying "not yet decidable" over a refuse would contradict the disposition
  // sitting directly above it.
  const blocking = report.disposition === 'incomplete-submission'
  return <div>
    <h4 className="mb-2 text-sm font-semibold">
      {blocking ? 'Why this is not yet decidable' : 'Gaps that are still open'}
    </h4>
    <div className="space-y-3 rounded-xl border bg-card p-4">
      <p className="text-xs text-muted-foreground">
        {blocking
          ? 'Nothing here says the agent misbehaved. It says the case cannot be authorised or monitored until each point below is closed — the policy will not let a decision rest on evidence it could not read.'
          : 'These did not drive the recommendation — a breach outranks them — but they are unclosed, and they would block an authorise or a monitor on their own.'}
      </p>
      {[['The institution filed short', filing, 'Return it. The missing material has to come from the submitter.'],
        ['The review could not conclude', review, 'Ours to close, not theirs. Re-run the case or resolve the flagged judgements before returning it.'],
      ].map(([title, items, note]) => (items as typeof filing).length ? (
        <div key={title as string}>
          <p className="text-xs font-semibold">{title as string}</p>
          <p className="mb-1.5 text-[11px] text-muted-foreground">{note as string}</p>
          <ul className="space-y-1">
            {(items as typeof filing).map(a => (
              <li key={a.code} className="flex gap-2 text-xs">
                <span className="mt-px font-mono text-[10px] text-muted-foreground">{a.code}</span>
                <span>{a.reason}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null)}
    </div>
  </div>
}

function RunTally({ n, label, tone }: { n: number | string; label: string; tone?: string }) {
  return (
    <div className="rounded-lg bg-muted/40 p-3">
      <strong className={cn('font-mono text-lg', tone)}>{n}</strong>
      <p className="text-[10px] text-muted-foreground">{label}</p>
    </div>
  )
}

export function AuthorisationPanel({ caseId, dossier, officer, busy, onSaved, onOpenRun, gate, gateRisk, findingsCount, onGateDecide }: {
  caseId: string
  dossier: DossierDetail | null
  officer: string
  busy: boolean
  onSaved: () => void
  onOpenRun: (run: string) => void
  /** The paused human gate, when the drafting run is holding one. */
  gate?: { context: GateContext } | null
  gateRisk?: RiskScore | null
  findingsCount?: number
  onGateDecide?: (d: GateSubmission) => void
}) {
  const report = dossier?.recommendation
  const [reviewer, setReviewer] = useState(officer === 'Case officer' ? '' : officer)
  const [disposition, setDisposition] = useState<Disposition>('incomplete-submission')
  const [rationale, setRationale] = useState('')
  const [conditions, setConditions] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { if (report) { setDisposition(report.disposition); setConditions(report.conditions.join('\n')); setError('') } }, [report?.recommendation_digest])

  const named = reviewer.trim().length >= 2
  const ctx = gate?.context
  const decideGate = (d: GateSubmission) => onGateDecide?.(d)
  const paused = ctx ? (
    <div className="rounded-xl border border-primary/40 bg-primary/5 p-4 ring-1 ring-primary/10">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <UserRoundCheck className="size-4 text-primary" />
        <span className="text-sm font-semibold">The report is waiting on this decision</span>
        <span className="text-xs text-muted-foreground">the pipeline is paused — nothing issues without a named sign-off</span>
      </div>
      {ctx.error && <Alert variant="destructive" className="mt-3"><TriangleAlert /><AlertDescription>{ctx.error}</AlertDescription></Alert>}
      {gateRisk && (
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border bg-background/60 px-3.5 py-2.5">
          <span className="flex items-center gap-1.5 text-sm"><Gauge className="size-4 text-muted-foreground" /><span className="font-mono font-semibold">{gateRisk.total.toFixed(2)}</span></span>
          <Badge variant="outline" className={cn('gap-1 text-xs font-semibold uppercase', TIER_TONE[gateRisk.tier])}>{gateRisk.tier_label}</Badge>
          <span className="text-sm text-muted-foreground">{findingsCount ?? 0} finding{(findingsCount ?? 0) === 1 ? '' : 's'} cited in the drafted report</span>
          <span className="ml-auto font-mono text-[11px] text-muted-foreground">{ctx.case_id}</span>
        </div>
      )}
    </div>
  ) : null

  if (!report) return <div className="h-full overflow-y-auto p-5"><div className="mx-auto max-w-3xl space-y-5">
    {paused}
    <p className="p-3 text-sm text-muted-foreground">Run a review to obtain an evidence-backed recommendation. The named supervisor signs the authorisation here.</p>
  </div></div>

  /** Authorisation first, gate second — see the note above this component. */
  async function sign() {
    if (!report) return
    setSaving(true); setError('')
    try {
      await signAuthorisation(caseId, { reviewer: reviewer.trim(), disposition, rationale: rationale.trim(), conditions: conditions.split('\n').map(c => c.trim()).filter(Boolean), recommendation_digest: report.recommendation_digest })
    } catch (e) {
      // The gate is deliberately NOT resumed: a refused authorisation leaves
      // the report frozen, which is the safe half-state to be left in.
      setError(String(e)); onSaved(); setSaving(false); return
    }
    onSaved()
    if (ctx) {
      toast.success(`Signed: ${DISPOSITION_LABEL[disposition]} — issuing the report`)
      decideGate({ action: 'approve', reviewer: reviewer.trim(), comment: rationale.trim() || null, directive: null })
    } else {
      toast.success('Authorisation decision recorded')
    }
    setSaving(false)
  }

  return <div className="h-full overflow-y-auto p-5"><div className="mx-auto max-w-3xl space-y-5">
    {paused}
    <div className="rounded-xl border bg-card p-4"><h4 className="flex items-center gap-2 text-sm font-semibold"><BadgeCheck className="size-4" />Named supervisory decision</h4>
      <p className="mb-4 mt-1 text-xs text-muted-foreground">
        Yours to make. The fields are pre-filled with the supervisor’s recommendation; the evidence behind it is below.
        {ctx && ' Signing records the disposition and issues the drafted report it rests on.'}
      </p>
      <FieldGroup>
        {/* ONE name for both writes. Two fields could put two different people
            on one case — the same reason the case room's identity is read-only. */}
        <Field><FieldLabel htmlFor="decision-name">Supervisor</FieldLabel><Input id="decision-name" value={reviewer} onChange={e => setReviewer(e.target.value)} placeholder="Your full name" /></Field>
        <Field><FieldLabel htmlFor="decision-disposition">Disposition</FieldLabel><select id="decision-disposition" value={disposition} onChange={e => setDisposition(e.target.value as Disposition)} className="h-9 rounded-md border bg-background px-3 text-sm">{Object.entries(DISPOSITION_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
        <Field><FieldLabel htmlFor="decision-rationale">Rationale</FieldLabel><textarea id="decision-rationale" rows={3} className="rounded-md border bg-background p-3 text-sm" value={rationale} onChange={e => setRationale(e.target.value)} placeholder="Explain your decision against the evidence and policy." /></Field>
        {disposition === 'monitor' && <Field><FieldLabel htmlFor="decision-conditions">Conditions · one per line</FieldLabel><textarea id="decision-conditions" rows={3} className="rounded-md border bg-background p-3 text-sm" value={conditions} onChange={e => setConditions(e.target.value)} /></Field>}
      </FieldGroup>
      {error && <p role="alert" className="mt-3 text-sm text-destructive">{error}</p>}
      <Button className="mt-4" onClick={sign} disabled={busy || saving || !named || rationale.trim().length < 10 || disposition === 'monitor' && !conditions.trim()}>
        {saving ? 'Recording…' : ctx ? `Sign & issue: ${DISPOSITION_LABEL[disposition]}` : `Sign: ${DISPOSITION_LABEL[disposition]}`}
      </Button>
    </div>

    <div>
      <h4 className="mb-2 text-sm font-semibold">What Mandate Supervisor recommends, and why</h4>
    <div className="rounded-xl border bg-card p-4">
      <div className="flex items-center gap-2"><ShieldAlert className="size-4 text-muted-foreground" /><h3 className="font-heading text-lg font-semibold">{DISPOSITION_LABEL[report.disposition]}</h3><Badge variant="outline" className="ml-auto">Recommended</Badge></div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className="font-mono text-[11px]">Policy {report.policy_version}</Badge>
        <Badge variant="outline" className="border-amber-500/40 text-[11px] text-amber-700 dark:text-amber-400">{report.policy_status.replaceAll('_', ' ')}</Badge>
      </div>
      {/* Every run, by verdict — not the clean count on its own. `clean` is
          the residual category: a run is clean only if it has no breach AND
          nothing left it unresolved, and two of the four unresolved
          conditions are case-wide (any inconclusive assessment carrying no
          run_refs, and rule coverage under the policy minimum). Either one
          marks EVERY run unresolved, so "0 clean runs" shown alone reads as a
          judgement on the runs when it is often a statement that they were
          never judged. Kestrel: 14 breach, 36 unresolved, 0 clean — the 36
          are unjudged, not unclean. */}
      <div className="mt-4 grid grid-cols-2 gap-2 text-center sm:grid-cols-4">
        <RunTally n={report.runs.filter(r => r.verdict === 'breach').length} label="runs with a breach" tone="text-red-700 dark:text-red-400" />
        <RunTally n={report.runs.filter(r => r.verdict === 'unresolved').length} label="unresolved" tone="text-amber-700 dark:text-amber-400" />
        <RunTally n={report.runs.filter(r => r.verdict === 'clean').length} label="clean" tone="text-emerald-700 dark:text-emerald-400" />
        <RunTally n={`${report.rules_exercised}/${report.active_rules}`} label="rules exercised" />
      </div>
    </div>
    </div>
    <Adequacy report={report} />
    <BreachedRules report={report} onOpenRun={onOpenRun} />
    {dossier?.decisions.map((d, i) => <div key={i} className="rounded-lg border p-3 text-xs"><b>{DISPOSITION_LABEL[d.disposition]}</b> · {d.reviewer} · {d.decided_at}<p className="mt-1">{d.rationale}</p>{d.conditions.map(c => <p key={c}>Condition: {c}</p>)}</div>)}
  </div></div>
}
