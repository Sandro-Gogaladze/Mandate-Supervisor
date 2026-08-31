import { useEffect, useState } from 'react'
import { Building2, ChevronRight, ClipboardList, Gauge } from 'lucide-react'
import { listCases } from '@/lib/api'
import type { CaseStatus, CaseSummary } from '@/lib/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { UploadCaseDialog } from '@/components/UploadCaseDialog'
import { TIER_TONE } from '@/components/ResultsPanel'
import { cn } from '@/lib/utils'

// Status chips: where the case is in its life — derived from the ledger,
// never stored (ledger/projection.py).
const STATUS_META: Record<CaseStatus, { label: string; tone: string }> = {
  submitted: { label: 'awaiting review', tone: 'bg-muted text-muted-foreground border-transparent' },
  triaged: { label: 'triaged', tone: 'border-border text-muted-foreground' },
  under_review: { label: 'under review', tone: 'border-primary/30 bg-primary/5 text-primary' },
  investigating: { label: 'investigating', tone: 'border-primary/30 bg-primary/5 text-primary' },
  pending_decision: { label: 'awaiting decision', tone: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400' },
  issued: { label: 'issued', tone: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400' },
  closed_rejected: { label: 'rejected', tone: 'border-border text-muted-foreground' },
  closed_no_action: { label: 'closed · no action', tone: 'border-border text-muted-foreground' },
}

export function CaseQueue({ onSelect }: { onSelect: (c: CaseSummary) => void }) {
  const [cases, setCases] = useState<CaseSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = () => listCases().then(setCases).catch((err) => setError(String(err)))

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (error) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col items-start gap-3 p-8">
        <p className="text-sm text-destructive">
          Couldn't reach the Supervisor API — the queue can't load. Check that the backend is running, then try again.
        </p>
        <p className="font-mono text-xs text-muted-foreground">{error}</p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setError(null)
            setCases(null)
            refresh()
          }}
        >
          Retry
        </Button>
      </div>
    )
  }

  if (!cases) {
    return (
      <div className="mx-auto grid max-w-5xl grid-cols-1 gap-4 p-8 md:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28 w-full" />
        ))}
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-5xl px-8 py-10">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <ClipboardList className="size-5 text-muted-foreground" />
            <h1 className="font-heading text-xl font-semibold tracking-tight">Case queue</h1>
            <Badge variant="secondary" className="ml-1 font-normal">
              {cases.length} on the record
            </Badge>
          </div>
          <p className="mt-1.5 max-w-xl text-sm text-muted-foreground">
            Highest risk first once reviewed — a supervisor runs the first pass from each case's room. Open a
            case to work it, or submit a mandate chain and transaction history that arrived outside this queue.
          </p>
        </div>
        <UploadCaseDialog
          onUploaded={(summary) => {
            refresh()
            onSelect(summary)
          }}
        />
      </div>
      <div className="mt-6 grid grid-cols-1 gap-3.5 md:grid-cols-2">
        {cases.map((c) => {
          const status = STATUS_META[c.status] ?? STATUS_META.submitted
          return (
            // A real <button>: keyboard-operable, focus ring matching every
            // other control.
            <button
              key={c.case_id}
              type="button"
              onClick={() => onSelect(c)}
              className="group flex flex-col gap-2 rounded-xl border bg-card py-4 text-left text-card-foreground shadow-sm outline-none transition-colors hover:border-primary/40 hover:bg-accent/30 focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
            >
              <div className="flex w-full items-start justify-between gap-2 px-5">
                <div className="flex min-w-0 items-center gap-2">
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-muted">
                    <Building2 className="size-4 text-muted-foreground" />
                  </div>
                  <div className="min-w-0">
                    <div className="truncate font-medium leading-tight">{c.firm}</div>
                    <div className="font-mono text-[11px] text-muted-foreground">{c.case_id}</div>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  {c.risk_total !== null && c.risk_tier !== null && (
                    <Badge variant="outline" className={cn('gap-1 font-mono text-[11px]', TIER_TONE[c.risk_tier])}>
                      <Gauge className="size-3" />
                      {c.risk_total.toFixed(2)}
                    </Badge>
                  )}
                  <ChevronRight className="size-4 text-muted-foreground/50 transition-transform group-hover:translate-x-0.5 group-hover:text-muted-foreground" />
                </div>
              </div>
              <div className="flex items-center gap-2 px-5">
                <Badge variant="outline" className={cn('text-[10px] font-normal uppercase', status.tone)}>
                  {status.label}
                </Badge>
                {c.findings_count > 0 && (
                  <span className="text-[11px] text-muted-foreground">
                    {c.findings_count} finding{c.findings_count === 1 ? '' : 's'}
                  </span>
                )}
              </div>
              <div className="px-5">
                <p className="line-clamp-2 text-sm text-muted-foreground">{c.summary}</p>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
