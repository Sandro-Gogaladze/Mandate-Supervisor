import { useEffect, useState } from 'react'
import { BadgeCheck, ShieldAlert } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { signAuthorisation } from '@/lib/api'
import { DISPOSITION_LABEL, type Disposition, type DossierDetail } from '@/lib/supervision-types'
import { RunCitation } from '@/components/AgentTurn'

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


export function AuthorisationPanel({ caseId, dossier, officer, busy, onSaved, onOpenRun }: { caseId: string; dossier: DossierDetail | null; officer: string; busy: boolean; onSaved: () => void; onOpenRun: (run: string) => void }) {
  const report = dossier?.recommendation
  const [reviewer, setReviewer] = useState(officer === 'Case officer' ? '' : officer)
  const [disposition, setDisposition] = useState<Disposition>('incomplete-submission')
  const [rationale, setRationale] = useState('')
  const [conditions, setConditions] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { if (report) { setDisposition(report.disposition); setConditions(report.conditions.join('\n')); setError('') } }, [report?.recommendation_digest])
  if (!report) return <div className="p-8 text-sm text-muted-foreground">Run a review to obtain an evidence-backed recommendation. The named supervisor signs the authorisation here.</div>
  async function sign() {
    if (!report) return
    setSaving(true); setError('')
    try { await signAuthorisation(caseId, { reviewer: reviewer.trim(), disposition, rationale: rationale.trim(), conditions: conditions.split('\n').map(c => c.trim()).filter(Boolean), recommendation_digest: report.recommendation_digest }); toast.success('Authorisation decision recorded'); onSaved() }
    catch (e) { setError(String(e)); onSaved() }
    finally { setSaving(false) }
  }
  return <div className="h-full overflow-y-auto p-5"><div className="mx-auto max-w-3xl space-y-5">
    <div className="rounded-xl border bg-card p-4"><h4 className="flex items-center gap-2 text-sm font-semibold"><BadgeCheck className="size-4" />Named supervisory decision</h4>
      <p className="mb-4 mt-1 text-xs text-muted-foreground">Yours to make. The fields are pre-filled with the supervisor’s recommendation; the evidence behind it is below.</p>
      <FieldGroup><Field><FieldLabel htmlFor="decision-name">Supervisor</FieldLabel><Input id="decision-name" value={reviewer} onChange={e => setReviewer(e.target.value)} placeholder="Your full name" /></Field>
        <Field><FieldLabel htmlFor="decision-disposition">Disposition</FieldLabel><select id="decision-disposition" value={disposition} onChange={e => setDisposition(e.target.value as Disposition)} className="h-9 rounded-md border bg-background px-3 text-sm">{Object.entries(DISPOSITION_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
        <Field><FieldLabel htmlFor="decision-rationale">Rationale</FieldLabel><textarea id="decision-rationale" rows={3} className="rounded-md border bg-background p-3 text-sm" value={rationale} onChange={e => setRationale(e.target.value)} placeholder="Explain your decision against the evidence and policy." /></Field>
        {disposition === 'monitor' && <Field><FieldLabel htmlFor="decision-conditions">Conditions · one per line</FieldLabel><textarea id="decision-conditions" rows={3} className="rounded-md border bg-background p-3 text-sm" value={conditions} onChange={e => setConditions(e.target.value)} /></Field>}
      </FieldGroup>
      {error && <p role="alert" className="mt-3 text-sm text-destructive">{error}</p>}
      <Button className="mt-4" onClick={sign} disabled={busy || saving || reviewer.trim().length < 2 || rationale.trim().length < 10 || disposition === 'monitor' && !conditions.trim()}>{saving ? 'Recording…' : `Sign: ${DISPOSITION_LABEL[disposition]}`}</Button>
    </div>
    <div>
      <h4 className="mb-2 text-sm font-semibold">What Mandate Supervisor recommends, and why</h4>
    <div className="rounded-xl border bg-card p-4">
      <div className="flex items-center gap-2"><ShieldAlert className="size-4 text-muted-foreground" /><h3 className="font-heading text-lg font-semibold">{DISPOSITION_LABEL[report.disposition]}</h3><Badge variant="outline" className="ml-auto">Recommended</Badge></div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className="font-mono text-[11px]">Policy {report.policy_version}</Badge>
        <Badge variant="outline" className="border-amber-500/40 text-[11px] text-amber-700 dark:text-amber-400">{report.policy_status.replaceAll('_', ' ')}</Badge>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 text-center">
        <div className="rounded-lg bg-muted/40 p-3"><strong className="font-mono text-lg">{report.clean_runs}</strong><p className="text-[10px] text-muted-foreground">clean runs</p></div>
        <div className="rounded-lg bg-muted/40 p-3"><strong className="font-mono text-lg">{report.rules_exercised}/{report.active_rules}</strong><p className="text-[10px] text-muted-foreground">rules exercised</p></div>
      </div>
    </div>
    </div>
    <BreachedRules report={report} onOpenRun={onOpenRun} />
    {dossier?.decisions.map((d, i) => <div key={i} className="rounded-lg border p-3 text-xs"><b>{DISPOSITION_LABEL[d.disposition]}</b> · {d.reviewer} · {d.decided_at}<p className="mt-1">{d.rationale}</p>{d.conditions.map(c => <p key={c}>Condition: {c}</p>)}</div>)}
  </div></div>
}
