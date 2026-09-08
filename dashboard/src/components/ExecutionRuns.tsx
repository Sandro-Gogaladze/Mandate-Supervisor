import { useEffect, useState } from 'react'
import { ArrowUpDown, Download, Search } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { getExecutions, getExecution, dossierExportURL } from '@/lib/api'
import { EvidenceFields, AssessmentCard } from '@/components/AgentTurn'
import type { DossierDetail, ExecutionDetail, ExecutionSummary } from '@/lib/supervision-types'

const money = (amount: number | null, currency: string | null) => amount == null ? '—' : `${currency ?? ''} ${amount.toFixed(2)}`

function Stat({ label, value, tone }: { label: string; value: string; tone?: 'warn' }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className={`mt-0.5 text-[13px] font-medium ${tone === 'warn' ? 'text-amber-700 dark:text-amber-400' : ''}`}>{value}</dd>
    </div>
  )
}

/** The submission's own shape, before any finding. Filed-versus-executed is
 * the one number here that is a supervisory signal rather than a label: a
 * firm that ran a hundred and filed ten has chosen which ten. */
function SubmissionSummary({ dossier }: { dossier: DossierDetail }) {
  const ctx = dossier.dossier.submission_context
  const withheld = ctx.runs_executed_total - ctx.runs_submitted
  return (
    <div className="rounded-lg border bg-card p-3.5">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-5">
        <Stat label="Agent" value={dossier.dossier.agent_id} />
        <Stat label="Institution" value={dossier.dossier.institution_id} />
        <Stat
          label="Runs filed"
          value={withheld > 0 ? `${ctx.runs_submitted} of ${ctx.runs_executed_total}` : String(ctx.runs_submitted)}
          tone={withheld > 0 ? 'warn' : undefined}
        />
        <Stat label="Deployment model" value={ctx.deployment_target.model_version} />
        <Stat label="Prompt release" value={ctx.deployment_target.prompt_release_ref} />
      </dl>
      {withheld > 0 && (
        <p className="mt-3 border-t pt-2.5 text-[12px] text-amber-700 dark:text-amber-400">
          {withheld} executed {withheld === 1 ? 'run was' : 'runs were'} not filed. Which runs a firm chooses to submit is itself evidence.
        </p>
      )}
    </div>
  )
}

export function ExecutionRuns({ caseId, dossier, refreshKey, onOpenRun }: { caseId: string; dossier: DossierDetail | null; refreshKey: number; onOpenRun: (run: string) => void }) {
  const [runs, setRuns] = useState<ExecutionSummary[]>([])
  const [error, setError] = useState('')
  // Without this the empty INITIAL state is indistinguishable from a loaded
  // empty one, and the tab reads "All 0 · No runs match this filter" while the
  // request is still in flight. On a busy machine that window is seconds long
  // — the endpoint recomputes the recommendation over the whole ledger — and
  // it was reported as the run list being broken.
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState(false)
  useEffect(() => {
    let active = true
    setLoading(true)
    getExecutions(caseId)
      .then(r => { if (active) { setRuns(r); setError('') } })
      .catch(e => active && setError(String(e)))
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [caseId, refreshKey])
  const counts = (verdict: string) => runs.filter(r => (r.review?.verdict ?? 'awaiting') === verdict).length
  const rank = { breach: 0, unresolved: 1, clean: 2 }
  const visible = runs.filter(r => (filter === 'all' || (r.review?.verdict ?? 'awaiting') === filter) && `${r.run_id} ${r.merchant} ${r.request}`.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => sort ? (a.review ? rank[a.review.verdict] : 3) - (b.review ? rank[b.review.verdict] : 3) || a.started_at.localeCompare(b.started_at) : a.started_at.localeCompare(b.started_at))
  return <div className="h-full overflow-auto p-5">
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-heading text-lg font-semibold">Submission</h3><p className="text-xs text-muted-foreground">What the institution filed: one signed Intent → Cart → Payment chain per purchase.</p></div>
        <Button asChild variant="outline" size="sm"><a href={dossierExportURL(caseId)}><Download /> Export dossier</a></Button>
      </div>
      {dossier && <SubmissionSummary dossier={dossier} />}
      <div className="flex flex-wrap gap-2">{['all', 'clean', 'breach', 'unresolved', 'awaiting'].map(v => <Button key={v} variant={v === filter ? 'secondary' : 'outline'} size="sm" onClick={() => setFilter(v)}>{v === 'all' ? (loading ? 'All —' : `All ${runs.length}`) : `${v} ${loading ? '—' : counts(v)}`}</Button>)}</div>
      <div className="flex items-center gap-2"><Search className="size-4 text-muted-foreground" /><Input aria-label="Search execution runs" placeholder="Run, merchant or shopper request" value={search} onChange={e => setSearch(e.target.value)} /><Button variant="outline" onClick={() => setSort(v => !v)}><ArrowUpDown />{sort ? 'By verdict' : 'By date'}</Button></div>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <div className="rounded-lg border bg-card"><Table><TableHeader><TableRow><TableHead>Run / shopper request</TableHead><TableHead>Merchant</TableHead><TableHead>Amount</TableHead><TableHead>Execution</TableHead><TableHead>Assessment</TableHead></TableRow></TableHeader>
        <TableBody>{visible.map(r => <TableRow key={r.run_id} className="cursor-pointer" onClick={() => onOpenRun(r.run_id)}>
          <TableCell className="max-w-sm"><button className="text-left font-mono text-[11px] text-primary hover:underline" onClick={() => onOpenRun(r.run_id)}>{r.run_id}</button><p className="mt-1 truncate text-xs text-muted-foreground">{r.request}</p></TableCell>
          <TableCell className="text-xs">{r.merchant ?? 'No cart'}</TableCell><TableCell className="whitespace-nowrap font-mono text-xs">{money(r.amount, r.currency)}</TableCell><TableCell className="text-xs">{r.outcome}</TableCell>
          <TableCell><Badge variant="outline" className={r.review?.verdict === 'clean' ? 'text-emerald-700' : r.review?.verdict === 'breach' ? 'text-amber-700' : ''}>{r.review?.verdict ?? 'Awaiting review'}</Badge></TableCell>
        </TableRow>)}</TableBody></Table></div>
      {loading && <p className="text-sm text-muted-foreground">Loading the filed runs…</p>}
      {!loading && !visible.length && !error && <p className="text-sm text-muted-foreground">No runs match this filter.</p>}
    </div>
  </div>
}

export function ExecutionInspector({ caseId, runId, onClose, dossier, onOpenRun, onInvestigate }: { caseId: string; runId: string | null; onClose: () => void; dossier: DossierDetail | null; onOpenRun: (run: string) => void; onInvestigate: (run: string) => void }) {
  const [detail, setDetail] = useState<ExecutionDetail | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { setDetail(null); setError(''); if (!runId) return; let active = true; getExecution(caseId, runId).then(d => active && setDetail(d)).catch(e => active && setError(String(e))); return () => { active = false } }, [caseId, runId])
  const run = detail?.run
  return <Dialog open={!!runId} onOpenChange={open => !open && onClose()}><DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
    <DialogHeader><DialogTitle className="font-mono text-sm">{runId}</DialogTitle><DialogDescription>Submitted execution evidence, from the shopper’s request to settlement.</DialogDescription></DialogHeader>
    {error && <p role="alert" className="text-destructive">{error}</p>}
    {!run && !error && <p className="text-sm text-muted-foreground">Loading execution evidence…</p>}
    {run && <div className="space-y-5 text-sm">
      <section><h4 className="mb-2 font-semibold">1 · Shopper request and signed intent</h4><p className="rounded-md bg-muted/50 p-3">{run.intent_mandate.natural_language_intent}</p><p className="my-2 font-mono text-[10px] text-muted-foreground">{run.intent_mandate.intent_mandate_id}</p><EvidenceFields values={run.intent_mandate.authorization_scope} /></section>
      <section><h4 className="mb-2 font-semibold">2 · What the agent used</h4><EvidenceFields values={{ observed_model: run.construction_context.model.observed_version, declared_model: run.construction_context.model.declared_version, prompt_release: run.construction_context.policy_version.release_ref }} />
        {run.construction_context.tool_calls.map(t => <details key={t.sequence} className="mt-2 rounded-md border p-2"><summary className="cursor-pointer text-xs">{t.sequence} · {t.tool_name} · {t.server_id}</summary><div className="mt-2"><EvidenceFields values={t.arguments} /><p className="mt-2 text-[10px] uppercase text-muted-foreground">Retrieved content · untrusted source text</p><blockquote className="mt-1 whitespace-pre-wrap border-l-2 pl-3 text-xs">{t.result_excerpt?.text ?? 'No excerpt supplied'}{t.result_excerpt?.truncated && <span className="block text-muted-foreground">Excerpt was truncated in the submission.</span>}</blockquote></div></details>)}
      </section>
      <section><h4 className="mb-2 font-semibold">3 · Consent and cart</h4><EvidenceFields values={{ ceremony_occurred: run.consent_ceremony?.occurred, scope: run.consent_ceremony?.ceremony_scope }} />
        {run.consent_ceremony?.rendered_values && <div className="mt-2 rounded-md border p-2"><p className="mb-2 text-xs text-muted-foreground">Values shown to the shopper</p><EvidenceFields values={run.consent_ceremony.rendered_values} /></div>}
        {run.cart ? <div className="mt-3"><p>{run.cart.merchant.name} · {money(run.cart.cart_total, run.cart.currency)}</p><p className="font-mono text-[10px] text-muted-foreground">{run.cart.cart_mandate_id}</p>{run.cart.line_items.map((item, i) => <p key={i} className="mt-1 text-xs">{item.qty} × {item.description} · {money(item.unit_price, run.cart!.currency)}</p>)}</div> : <p>No cart submitted.</p>}
      </section>
      <section><h4 className="mb-2 font-semibold">4 · Payment, controls and settlement</h4>
        {run.payment ? <><p>{money(run.payment.amount, run.payment.currency)} · {run.payment.settlement_status}</p><p className="mb-2 font-mono text-[10px] text-muted-foreground">{run.payment.payment_mandate_id}</p><EvidenceFields values={run.payment.payee} /></> : <p>No payment mandate.</p>}
        {run.controls_evaluated.map((c, i) => <div key={i} className="mt-2 rounded-md border p-2 text-xs"><b>{c.control_id}</b> · {c.outcome}{c.override && <div className="mt-1"><EvidenceFields values={c.override} /></div>}</div>)}
        {detail?.transactions.map(t => <p key={t.transaction_id} className="mt-2 text-xs">{t.transaction_id} · {money(t.amount, t.currency)} · {t.status} · {t.timestamp}</p>)}
      </section>
      <section><h4 className="mb-2 font-semibold">5 · Current assessments</h4><div className="space-y-2">{dossier?.assessments.filter(a => a.run_refs.includes(run.run_id)).map(a => <AssessmentCard key={a.assessment_id} assessment={a} facts={new Map(dossier.facts.map(f => [f.fact_id, f]))} onOpenRun={onOpenRun} />)}</div></section>
      <Button onClick={() => onInvestigate(run.run_id)}>Ask the orchestrator about this run</Button>
    </div>}
  </DialogContent></Dialog>
}
