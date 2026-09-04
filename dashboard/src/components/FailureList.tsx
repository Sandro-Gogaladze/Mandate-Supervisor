// A specialist's headline output: which catalogue failure, and where.
//
// The full chain — narrative, verdict, cited facts, rule and ruleset version
// — stays one disclosure away in the turn that owns it. A reviewer scanning a
// case wants "F42 on RUN-…0043", not six lines of provenance per row; the
// provenance is what they open when a row earns their attention.
import { useState, type ReactNode } from 'react'
import { ChevronRight } from 'lucide-react'
import { RunCitation } from '@/components/AgentTurn'
import { cn } from '@/lib/utils'
import type { FailureOccurrence } from '@/lib/types'

/** Ordered worst-first: a detected failure outranks a possible one, and a
 * contained or unevaluable one sorts last. */
const STATUS_ORDER: FailureOccurrence['status'][] = ['detected', 'possible', 'contained', 'not_evaluable']

export const STATUS_LABEL: Record<FailureOccurrence['status'], string> = {
  detected: 'happened',
  possible: 'possible',
  contained: 'stopped',
  not_evaluable: 'not decided',
}

const STATUS_TONE: Record<FailureOccurrence['status'], string> = {
  detected: 'border-red-500/30 bg-red-500/[0.05] text-red-700 dark:text-red-400',
  possible: 'border-amber-500/30 bg-amber-500/[0.05] text-amber-700 dark:text-amber-400',
  contained: 'border-sky-500/30 bg-sky-500/[0.04] text-sky-700 dark:text-sky-400',
  not_evaluable: 'border-dashed text-muted-foreground',
}

export function sortOccurrences(occurrences: FailureOccurrence[]): FailureOccurrence[] {
  return occurrences
    .slice()
    .sort((a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status)
      || a.failure_id.localeCompare(b.failure_id, undefined, { numeric: true }))
}

/** Where the failure landed. Runs are the common case and are clickable;
 * transactions carry history-only patterns whose run may not be submitted;
 * case refs are portfolio scope. Nothing at all means dossier-level, which
 * is a real answer and not a missing one. */
function Where({ o, onOpenRun }: { o: FailureOccurrence; onOpenRun?: (run: string) => void }) {
  const byCase = Object.entries(o.run_refs_by_case ?? {})
  if (byCase.length > 0) {
    return (
      <div className="flex flex-col gap-0.5">
        {byCase.map(([caseId, runs]) => (
          <div key={caseId} className="flex flex-wrap items-baseline gap-x-1.5">
            <span className="font-mono text-[10px] text-muted-foreground">{caseId}</span>
            {runs.map((run) => <Ref key={`${caseId}:${run}`} value={run} onOpenRun={onOpenRun} />)}
          </div>
        ))}
      </div>
    )
  }
  const refs = o.run_refs.length ? o.run_refs
    : o.transaction_refs.length ? o.transaction_refs
      : o.case_refs
  if (!refs.length) return <span className="text-[11px] text-muted-foreground">across the dossier</span>
  return (
    <div className="flex flex-wrap gap-1">
      {refs.map((value) => (
        <Ref key={value} value={value} onOpenRun={o.run_refs.length ? onOpenRun : undefined} />
      ))}
    </div>
  )
}

function Ref({ value, onOpenRun }: { value: string; onOpenRun?: (run: string) => void }) {
  if (onOpenRun) return <RunCitation run={value} onOpenRun={onOpenRun} />
  return <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">{value}</span>
}

/** One failure. `children` is the reasoning that produced it — when supplied
 * the row becomes its own disclosure, so the claim and its justification are
 * one thing a reader opens rather than two parallel lists they have to match
 * up by eye. */
export function FailureRow({ o, onOpenRun, children }: {
  o: FailureOccurrence
  onOpenRun?: (run: string) => void
  children?: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const head = (
    <>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        {children !== undefined && (
          <ChevronRight className={cn('size-3.5 shrink-0 self-center transition-transform', open && 'rotate-90')} />
        )}
        <span className="font-mono text-[11px] font-semibold">{o.failure_id}</span>
        <span className="text-[13.5px] font-medium leading-5 text-foreground">{o.failure_name}</span>
        <span className="ml-auto text-[11px] uppercase tracking-wide opacity-80">{STATUS_LABEL[o.status]}</span>
      </div>
      <div className={cn('mt-1', children !== undefined && 'pl-5')}><Where o={o} onOpenRun={onOpenRun} /></div>
    </>
  )
  if (children === undefined) {
    return <div className={cn('rounded-lg border px-3 py-2', STATUS_TONE[o.status])}>{head}</div>
  }
  return (
    <div className={cn('rounded-lg border', STATUS_TONE[o.status])}>
      <button type="button" onClick={() => setOpen(!open)} className="w-full px-3 py-2 text-left">
        {head}
      </button>
      {open && <div className="border-t px-3 py-2.5">{children}</div>}
    </div>
  )
}

export function FailureList({ occurrences, onOpenRun, detail }: {
  occurrences: FailureOccurrence[]
  onOpenRun?: (run: string) => void
  /** The reasoning behind one occurrence. Return undefined to leave that row
   * flat rather than rendering an empty drawer. */
  detail?: (o: FailureOccurrence) => ReactNode | undefined
}) {
  return (
    <div className="flex flex-col gap-1.5">
      {sortOccurrences(occurrences).map((o) => (
        <FailureRow key={o.occurrence_id} o={o} onOpenRun={onOpenRun}>
          {detail?.(o)}
        </FailureRow>
      ))}
    </div>
  )
}

/** "8 happened on 6 runs · 1 stopped" — the step header, by status, so the
 * count a reader sees here reconciles with the rows underneath rather than
 * silently counting only the detected ones. */
export function failureSummary(occurrences: FailureOccurrence[]): string | null {
  if (!occurrences.length) return null
  return STATUS_ORDER
    .map((status) => {
      const group = occurrences.filter((o) => o.status === status)
      if (!group.length) return null
      const runs = new Set(group.flatMap((o) => o.run_refs)).size
      const label = `${group.length} ${STATUS_LABEL[status]}`
      return status === 'detected' && runs ? `${label} on ${runs} run${runs === 1 ? '' : 's'}` : label
    })
    .filter(Boolean)
    .join(' · ')
}
