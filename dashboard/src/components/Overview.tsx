import { useEffect, useState } from 'react'
import { ArrowRight, Building2, ChevronRight, GitMerge, ShieldAlert, Waypoints } from 'lucide-react'
import { listCases } from '@/lib/api'
import type { CaseSummary } from '@/lib/types'
import { nodeMeta, SPECIALISTS, AGENT_ICON } from '@/lib/node-meta'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { UploadCaseDialog } from '@/components/UploadCaseDialog'
import { cn } from '@/lib/utils'

export function Overview({
  onOpenQueue,
  onOpenCase,
}: {
  onOpenQueue: () => void
  onOpenCase: (c: CaseSummary) => void
}) {
  const [cases, setCases] = useState<CaseSummary[] | null>(null)

  useEffect(() => {
    listCases().then(setCases).catch(() => setCases([]))
  }, [])

  return (
    <div className="mx-auto max-w-6xl px-8 py-10">
      {/* Hero — the console's front door. The heading carries its own
          weight (no kicker); the institution lives in the copy. */}
      <section className="relative overflow-hidden rounded-2xl border bg-card px-8 py-10 shadow-sm md:px-12 md:py-14">
        {/* Fine blueprint grid in the logo blue — the drafting-table
            texture this console commits to, fading toward the bottom. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              'linear-gradient(oklch(0.55 0.21 262 / 0.06) 1px, transparent 1px), linear-gradient(90deg, oklch(0.55 0.21 262 / 0.06) 1px, transparent 1px)',
            backgroundSize: '28px 28px',
            maskImage: 'linear-gradient(to bottom, black 30%, transparent 95%)',
          }}
        />
        <img
          src="/logo.png"
          alt=""
          aria-hidden
          className="pointer-events-none absolute right-10 top-1/2 hidden w-56 -translate-y-1/2 opacity-90 lg:block xl:w-64"
        />
        <div className="relative max-w-2xl">
          <h1 className="font-heading text-4xl font-bold leading-[1.08] tracking-tight md:text-5xl">
            Continuous oversight of
            <br />
            AI payment agents.
          </h1>
          <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-muted-foreground">
            The National Bank of Georgia's supervision console. Every submitted mandate chain is checked against what
            the agent was actually authorised to do — by eight domain specialists and Control Assurance, live, with every step of their
            reasoning on the record.
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <Button size="lg" onClick={onOpenQueue} className="font-medium">
              Open case queue
              <ArrowRight data-icon="inline-end" />
            </Button>
            <UploadCaseDialog onUploaded={onOpenCase} />
          </div>
        </div>
      </section>

      {/* The bench — a roster, not a card grid. Operate-mode density: the
          reader scans names and jobs, they don't tour four brochures. */}
      <section className="mt-10">
        <div className="flex items-end justify-between gap-4">
          <div>
            <h2 className="font-heading text-xl font-semibold tracking-tight">The review bench</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              An orchestrator dispatches the case; each specialist reports typed findings, never prose into the void.
            </p>
          </div>
          <div className="hidden items-center gap-1.5 text-xs text-muted-foreground md:flex">
            <Waypoints className="size-3.5" /> dispatch
            <ChevronRight className="size-3" />
            <ShieldAlert className="size-3.5" /> specialists
            <ChevronRight className="size-3" />
            <GitMerge className="size-3.5" /> escalation
          </div>
        </div>
        <div className="mt-4 overflow-hidden rounded-xl border bg-card">
          {SPECIALISTS.map((id, i) => {
            const meta = nodeMeta(id)
            const Icon = meta.icon
            const tone = AGENT_ICON[meta.color]
            return (
              <div key={id} className={cn('flex items-center gap-4 px-5 py-3.5', i > 0 && 'border-t')}>
                <div className={cn('flex size-9 shrink-0 items-center justify-center rounded-lg', tone.bg)}>
                  <Icon className={cn('size-4.5', tone.text)} strokeWidth={2.25} />
                </div>
                <div className="min-w-0 flex-1 sm:flex sm:items-baseline sm:gap-3">
                  <span className="w-20 shrink-0 font-heading text-[15px] font-semibold">{meta.label}</span>
                  <span className="block text-[13px] leading-relaxed text-muted-foreground">{meta.blurb}</span>
                </div>
                <span className="size-1.5 shrink-0 rounded-full bg-emerald-500" title="ready" />
              </div>
            )
          })}
        </div>
      </section>

      {/* Next up — a taste of the queue, not the whole queue. */}
      <section className="mt-10">
        <div className="flex items-center justify-between">
          <h2 className="font-heading text-xl font-semibold tracking-tight">Next up</h2>
          <Button variant="ghost" size="sm" onClick={onOpenQueue}>
            View full queue
            <ArrowRight data-icon="inline-end" />
          </Button>
        </div>
        <div className="mt-3 overflow-hidden rounded-xl border bg-card">
          {cases === null ? (
            <div className="flex flex-col gap-2 p-4">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-14" />
              ))}
            </div>
          ) : (
            cases.slice(0, 3).map((c, i) => (
              <button
                key={c.case_id}
                onClick={() => onOpenCase(c)}
                className={cn(
                  'group flex w-full items-center gap-4 px-5 py-3.5 text-left transition-colors hover:bg-accent/40',
                  i > 0 && 'border-t',
                )}
              >
                <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-muted">
                  <Building2 className="size-4 text-muted-foreground" />
                </div>
                <div className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{c.firm}</span>
                  <div className="mt-0.5 truncate text-[13px] text-muted-foreground">{c.summary}</div>
                </div>
                <Badge variant="outline" className="hidden shrink-0 font-mono text-[10px] sm:inline-flex">
                  {c.case_id}
                </Badge>
                <ChevronRight className="size-4 shrink-0 text-muted-foreground/50 transition-transform group-hover:translate-x-0.5" />
              </button>
            ))
          )}
        </div>
      </section>
    </div>
  )
}
