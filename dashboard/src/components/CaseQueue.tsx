import { DISPOSITION_LABEL } from '@/lib/supervision-types'
import { useEffect, useState } from 'react'
import { Building2, ChevronRight, ClipboardList, Gauge } from 'lucide-react'
import { listCases, refreshCases } from '@/lib/api'
import type { CaseStatus, CaseSummary } from '@/lib/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { UploadCaseDialog } from '@/components/UploadCaseDialog'
import { BlueprintGrid } from '@/components/BlueprintGrid'
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

/** The four numbers a supervisor actually wants off this page: how much
 * is here, how much hasn't been looked at, how much is waiting on them,
 * and how much is finished. Derived, never stored. */
const STATS: { label: string; count: (c: CaseSummary[]) => number; urgent?: boolean }[] = [
  { label: 'on the record', count: (c) => c.length },
  { label: 'awaiting review', count: (c) => c.filter((x) => x.status === 'submitted').length },
  { label: 'awaiting decision', count: (c) => c.filter((x) => x.status === 'pending_decision').length, urgent: true },
  { label: 'decided', count: (c) => c.filter((x) => x.status === 'issued').length },
]

export function CaseQueue({ onSelect }: { onSelect: (c: CaseSummary) => void }) {
  const [cases, setCases] = useState<CaseSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Mount shares the in-flight window; an explicit refresh after an upload
  // must not be served a list taken before it.
  const load = (fresh = false) => (fresh ? refreshCases() : listCases()).then(setCases).catch((err) => setError(String(err)))
  const refresh = () => load(true)

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (error) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col items-start gap-3 p-8">
        <p className="text-sm text-destructive">
          Couldn't reach the Supervisor API — cases can't load. Check that the backend is running, then try again.
        </p>
        <p className="font-mono text-xs text-muted-foreground">{error}</p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setError(null)
            setCases(null)
            load(true)
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
      {/* A header band, not a bare title row: this page is where an
          outside reader lands after the Overview, so it restates what a
          case is and shows the shape of the load before the cards. Same
          drafting-paper texture as the explainer cards on the Overview —
          this header explains, the cards below are the live data. */}
      <section className="relative overflow-hidden rounded-xl border bg-card px-5 py-4 shadow-sm md:px-6">
        <BlueprintGrid strength={5} size={24} />
        <div className="relative flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
          <div>
            <div className="flex items-center gap-2">
              <ClipboardList className="size-4.5 text-muted-foreground" />
              <h1 className="font-heading text-xl font-semibold tracking-tight">Cases</h1>
            </div>
            {/* One sentence. The second one told the reader to file a
                submission while the button to do it sat beside the text. */}
            <p className="mt-1.5 max-w-2xl text-[13px] leading-relaxed text-muted-foreground">
              The case record of every submitted agent — one entry each, available once a submission has been filed and
              its checks have passed.
            </p>
          </div>
          <UploadCaseDialog
            onUploaded={(summary) => {
              refresh()
              onSelect(summary)
            }}
          />
        </div>

        {/* The load at a glance. Counts derive from the same list the
            cards render, so the strip can never disagree with them. Number
            and label share a baseline: stacked, four cells of two short
            lines each left most of the strip empty. */}
        <dl className="relative mt-4 flex flex-wrap items-stretch divide-x divide-border rounded-lg border bg-card/60">
          {STATS.map((stat) => {
            const n = stat.count(cases)
            return (
              <div key={stat.label} className="flex flex-1 basis-[45%] items-baseline gap-2 px-3.5 py-2 sm:basis-0">
                <dd
                  className={cn(
                    'font-heading text-base font-semibold tabular-nums leading-none tracking-tight',
                    // Work waiting on the supervisor is the one number worth
                    // colouring; the rest are context.
                    stat.urgent && n > 0 && 'text-amber-600 dark:text-amber-400',
                    n === 0 && 'text-muted-foreground/50',
                  )}
                >
                  {n}
                </dd>
                <dt className="text-[11.5px] leading-none text-muted-foreground">{stat.label}</dt>
              </div>
            )
          })}
        </dl>
      </section>

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
              className="group flex h-full flex-col gap-2 rounded-xl border bg-card py-4 text-left text-card-foreground shadow-sm outline-none transition-colors hover:border-primary/40 hover:bg-accent/30 focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
            >
              {/* Row 1 belongs to the firm — the one thing a reviewer scans
                  for. Only the risk score, which is short and fixed-width,
                  shares it; every other chip drops to the meta row so a long
                  firm name never has to truncate. */}
              <div className="flex w-full items-start justify-between gap-3 px-5">
                <div className="flex min-w-0 items-center gap-2.5">
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-muted">
                    <Building2 className="size-4 text-muted-foreground" />
                  </div>
                  <div className="min-w-0">
                    <div className="truncate font-heading text-[15px] font-semibold leading-tight">{c.firm}</div>
                    <div className="truncate font-mono text-[11px] text-muted-foreground">{c.case_id}</div>
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
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 px-5">
                <Badge variant="outline" className={cn('text-[10px] font-normal uppercase', status.tone)}>
                  {status.label}
                </Badge>
                {(c.authorisation_decision || c.recommendation) && (
                  <Badge variant="outline" className="text-[10px] font-normal">
                    {DISPOSITION_LABEL[(c.authorisation_decision || c.recommendation)!]}
                    {!c.authorisation_decision && ' · proposed'}
                  </Badge>
                )}
                {c.findings_count > 0 && (
                  <span className="text-[11px] text-muted-foreground">
                    {c.findings_count} finding{c.findings_count === 1 ? '' : 's'}
                  </span>
                )}
              </div>
              {/* mt-auto pins the summary to the bottom so cards in a row end
                  on the same line however many chips the meta row carries. */}
              <div className="mt-auto px-5 pt-0.5">
                <p className="line-clamp-2 text-sm leading-relaxed text-muted-foreground">{c.summary}</p>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
