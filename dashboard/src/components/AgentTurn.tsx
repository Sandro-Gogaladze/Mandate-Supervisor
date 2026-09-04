import { useEffect, useState } from 'react'
import { CheckCheck, ChevronRight, Loader2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { nodeMeta } from '@/lib/node-meta'
import type { LedgerEvent } from '@/lib/types'
import type { Assessment, Fact, SpecialistProgress } from '@/lib/supervision-types'

export const turnAnchor = (agent: string, runId: string) => `turn-${runId}-${agent}`

export function EvidenceFields({ values }: { values: Record<string, unknown> }) {
  return <dl className="grid grid-cols-[minmax(6rem,1fr)_2fr] gap-x-3 gap-y-1 text-xs">
    {Object.entries(values).map(([key, value]) => <div key={key} className="contents">
      <dt className="break-words text-muted-foreground">{key.replaceAll('_', ' ')}</dt>
      <dd className="break-words">{value == null ? 'Not supplied' : typeof value !== 'object' ? String(value)
        : <details><summary className="cursor-pointer">{Array.isArray(value) ? `${value.length} entries` : Object.keys(value).map(k => k.replaceAll('_', ' ')).join(' · ')}</summary>
          <div className="mt-2 border-l pl-2">{Array.isArray(value)
            ? value.map((entry, i) => <div key={i} className="mb-2">{entry && typeof entry === 'object' ? <EvidenceFields values={entry as Record<string, unknown>} /> : String(entry)}</div>)
            : <EvidenceFields values={value as Record<string, unknown>} />}</div>
        </details>}</dd>
    </div>)}
  </dl>
}

export function RunCitation({ run, onOpenRun }: { run: string; onOpenRun: (run: string) => void }) {
  return <button type="button" className="break-all text-left font-mono text-[10px] text-primary underline-offset-2 hover:underline" onClick={() => onOpenRun(run)}>{run}</button>
}

export function FactCard({ fact, onOpenRun }: { fact: Fact; onOpenRun: (run: string) => void }) {
  return <div className="rounded-md border bg-card p-2 text-xs">
    <div className="flex flex-wrap items-center gap-2">
      <span className="font-mono text-[10px] text-muted-foreground">{fact.rule_id ?? 'Measurement'}</span>
      <Badge variant="outline" className="text-[9px]">{fact.kind}</Badge>
      {fact.run_ref && <RunCitation run={fact.run_ref} onOpenRun={onOpenRun} />}
    </div>
    <p className="mt-1 leading-relaxed">{fact.statement}</p>
    {fact.kind === 'absent' && <p className="mt-1 text-amber-700 dark:text-amber-400">{fact.absent_reason?.replaceAll('_', ' ')}{fact.missing && ` · needed: ${fact.missing}`}</p>}
    {fact.refs.length > 0 && <details className="mt-1 text-muted-foreground"><summary className="cursor-pointer">Evidence references ({fact.refs.length})</summary>
      <div className="mt-1 space-y-1">{fact.refs.map((ref, i) => <div key={i}>
        <span className="font-mono text-[10px]">{ref.ref}</span>
        {ref.value != null && typeof ref.value !== 'object' && <> · {String(ref.value)}</>}
      </div>)}</div>
    </details>}
  </div>
}

export function AssessmentCard({ assessment: a, facts, onOpenRun }: { assessment: Assessment; facts: Map<string, Fact>; onOpenRun: (run: string) => void }) {
  return <div className={`rounded-lg border p-2.5 text-xs ${a.verdict === 'breach' ? 'border-amber-500/30 bg-amber-500/[0.05]' : a.verdict === 'inconclusive' ? 'border-dashed' : 'bg-card'}`}>
    <div className="flex flex-wrap items-center gap-2">
      <Badge variant="outline" className="text-[10px]">{a.verdict}</Badge>
      <span className="font-mono text-[10px]">{a.rule_id}</span>
      <span className="ml-auto text-[10px] text-muted-foreground">{a.confidence} · severity {a.severity_assessed.toFixed(2)}</span>
    </div>
    <p className="mt-1.5 leading-relaxed">{a.narrative}</p>
    <div className="mt-1 flex flex-wrap gap-x-2">{a.run_refs.map(run => <RunCitation key={run} run={run} onOpenRun={onOpenRun} />)}</div>
    <details className="mt-1.5"><summary className="cursor-pointer text-[11px] text-muted-foreground">Cites {a.fact_ids.length} facts · round {a.round}</summary>
      <div className="mt-2 space-y-1">{a.fact_ids.map(id => facts.has(id)
        ? <FactCard key={id} fact={facts.get(id)!} onOpenRun={onOpenRun} />
        : <p key={id} className="text-amber-700">Evidence reference not loaded: {id}</p>)}</div>
    </details>
  </div>
}

export function AgentTurn({ agent, runId, events, facts, liveCounts, status, onOpenRun }: {
  agent: string; runId: string; events: LedgerEvent[]; facts: Map<string, Fact>
  liveCounts?: SpecialistProgress['fact_counts']; status?: string; onOpenRun: (run: string) => void
}) {
  const [filter, setFilter] = useState('all')
  const [limit, setLimit] = useState(30)
  const meta = nodeMeta(agent)
  const assessments = events.filter(e => e.event_type === 'assessment_recorded').map(e => e.payload as unknown as Assessment)
  const ids = new Set(assessments.flatMap(a => a.fact_ids))
  const recorded = new Set(events.filter(e => e.event_type === 'fact_recorded').map(e => String(e.payload.fact_id)))
  // The agent's facts: everything in its domain on the ledger (a later run
  // re-evaluating an unchanged dossier records no new fact events, so the
  // run's own events alone would show a sliver), plus anything it cited.
  const ownFacts = new Map([...facts].filter(([id, f]) => f.domain === agent || ids.has(id) || recorded.has(id)))
  // The specialist's own counts for this run are exact and arrive with the
  // stream; the ledger view stands in when the turn is read back later.
  const total = liveCounts?.total ?? ownFacts.size
  const counts = (kind: Fact['kind']) => liveCounts ? (liveCounts[kind as keyof SpecialistProgress['fact_counts']] ?? 0) : [...ownFacts.values()].filter(f => f.kind === kind).length
  const running = status === 'reasoning'
  // Open while the specialist works; afterwards the reader's own toggling
  // wins (a controlled `open` that flipped back closed the turn under them).
  const [open, setOpen] = useState(running)
  useEffect(() => { if (running) setOpen(true) }, [running])
  const dispatch = events.find(e => e.event_type === 'dispatch_recorded')
  const context = dispatch?.payload.context_blocks as Record<string, unknown> | undefined
  const visible = [...ownFacts.values()].filter(f => filter === 'all' || f.kind === filter)
  return <details id={turnAnchor(agent, runId)} className="group/turn rounded-lg border bg-card/50" open={open} onToggle={e => setOpen((e.currentTarget as HTMLDetailsElement).open)}>
    <summary className="flex cursor-pointer list-none items-center gap-2 p-2.5 [&::-webkit-details-marker]:hidden">
      <ChevronRight className="size-3 shrink-0 transition-transform group-open/turn:rotate-90" />
      <meta.icon className="size-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1"><span className="text-xs font-semibold">{meta.label}</span>
        <p className="text-[10px] text-muted-foreground">{total} facts · {counts('satisfied')} satisfied · {counts('breach')} breach · {counts('absent')} absent · {assessments.length} assessments</p>
      </div>
      {running ? <Loader2 className="size-3 animate-spin text-amber-600" /> : status === 'complete' || assessments.length ? <CheckCheck className="size-3 text-emerald-600" /> : null}
    </summary>
    <div className="space-y-2 border-t p-2.5">
      <p className="text-xs text-muted-foreground">{meta.blurb}</p>
      {dispatch?.payload.instruction ? <p className="text-xs italic">{String(dispatch.payload.instruction)}</p> : null}
      {context && <p className="text-[10px] text-muted-foreground">Evidence blocks: {Object.keys(context).map(k => k.replaceAll('_', ' ')).join(' · ')}</p>}
      {events.filter(e => e.event_type === 'specialist_failed').map(e => <p key={e.seq} className="text-xs text-amber-700">{String(e.payload.message)}</p>)}
      {assessments.map(a => <AssessmentCard key={a.assessment_id} assessment={a} facts={new Map([...facts, ...ownFacts])} onOpenRun={onOpenRun} />)}
      {events.filter(e => e.event_type === 'control_posture_recorded').map(e => <div key={e.seq} className="rounded-md border p-2"><EvidenceFields values={e.payload} /></div>)}
      <details><summary className="cursor-pointer text-xs text-muted-foreground">Rule results ({total})</summary>
        {ownFacts.size === 0 && total > 0 && <p className="my-2 text-xs text-muted-foreground">The rule results are on the ledger and load when the run finishes.</p>}
        {ownFacts.size > 0 && liveCounts && ownFacts.size !== liveCounts.total && <p className="my-2 text-xs text-muted-foreground">{ownFacts.size} of {liveCounts.total} loaded.</p>}
        <div className="my-2 flex flex-wrap gap-1">{['all', 'breach', 'satisfied', 'absent', 'measurement'].map(kind => <Button key={kind} variant={kind === filter ? 'secondary' : 'ghost'} size="sm" onClick={() => { setFilter(kind); setLimit(30) }}>{kind}</Button>)}</div>
        <div className="space-y-1">{visible.slice(0, limit).map(f => <FactCard key={f.fact_id} fact={f} onOpenRun={onOpenRun} />)}</div>
        {visible.length > limit && <Button variant="ghost" size="sm" onClick={() => setLimit(n => n + 30)}>Show 30 more · {visible.length - limit} remaining</Button>}
      </details>
    </div>
  </details>
}

// Tool argument streams are partial documents. Render only human-readable
// narrative fields as they arrive; evidence becomes typed cards when recorded.
export function ToolCallRow({ name, args }: { name: string; args: unknown }) {
  const text: string[] = []
  function collect(value: unknown, key = '') {
    if (typeof value === 'string' && /^(reasoning|narrative|summary|answer|explanation|note|message_to_officer|overall_assessment|body|rationale)$/.test(key)) text.push(value)
    else if (Array.isArray(value)) value.forEach(v => collect(v))
    else if (value && typeof value === 'object') Object.entries(value).forEach(([k, v]) => collect(v, k))
  }
  collect(args)
  return <div className="space-y-1 text-xs"><span className="text-[10px] text-muted-foreground">{name.replaceAll('_', ' ')}</span>
    {text.length ? text.map((line, i) => <p key={i} className="leading-relaxed">{line}</p>) : <span className="ml-2 text-muted-foreground">Preparing structured evidence…</span>}
  </div>
}
