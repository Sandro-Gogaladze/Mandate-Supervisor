import { useEffect, useState } from 'react'
import { Building2, ChevronRight, ClipboardList } from 'lucide-react'
import { listCases } from '@/lib/api'
import type { CaseSummary } from '@/lib/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { UploadCaseDialog } from '@/components/UploadCaseDialog'

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
              {cases.length} awaiting review
            </Badge>
          </div>
          <p className="mt-1.5 max-w-xl text-sm text-muted-foreground">
            Select a case below to run a live multi-agent review, or submit a mandate chain and transaction history
            that arrived outside this queue.
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
          // A real <button>, not a click-div wearing Card's classes: the
          // queue is the primary work surface and must be operable by
          // keyboard — Tab reaches it, Enter/Space opens it, and the
          // focus ring matches every other control.
          return (
            <button
              key={c.case_id}
              type="button"
              onClick={() => onSelect(c)}
              className="group flex flex-col gap-2 rounded-xl border bg-card py-4 text-left text-card-foreground shadow-sm outline-none transition-colors hover:border-primary/40 hover:bg-accent/30 focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
            >
              <div className="flex w-full items-start justify-between gap-2 px-5">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-muted">
                    <Building2 className="size-4 text-muted-foreground" />
                  </div>
                  <div className="min-w-0">
                    <div className="truncate font-medium leading-tight">{c.firm}</div>
                    <div className="font-mono text-[11px] text-muted-foreground">{c.case_id}</div>
                  </div>
                </div>
                <ChevronRight className="size-4 shrink-0 text-muted-foreground/50 transition-transform group-hover:translate-x-0.5 group-hover:text-muted-foreground" />
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
