import { useEffect, useState } from 'react'
import { ArrowRight, Building2, ChevronRight } from 'lucide-react'
import { listCases } from '@/lib/api'
import type { CaseSummary } from '@/lib/types'
import { nodeMeta, SPECIALISTS, AGENT_ICON } from '@/lib/node-meta'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { UploadCaseDialog } from '@/components/UploadCaseDialog'
import { BlueprintGrid } from '@/components/BlueprintGrid'
import { SpecialistOrbit } from '@/components/SpecialistOrbit'
import { cn } from '@/lib/utils'

/** The rail behind the numbered nodes — same fade as the hero nameplate
 * rule, so the page reads as one system rather than two. */
const RAIL = (dir: 'to right' | 'to bottom') =>
  `linear-gradient(${dir}, color-mix(in oklab, var(--brand-blue) 40%, transparent), color-mix(in oklab, var(--brand-blue) 12%, transparent))`

/** The four stages of a review, in order. Deliberately shallow — each
 * specialist gets its own page; this is the map, not the territory. */
const STEPS: { title: string; body: string }[] = [
  {
    title: 'Submission',
    body: 'The bank or PSP that sponsors the agent files its evidence: the agent’s credential, the mandates it held, and the complete record of its runs.',
  },
  {
    title: 'Verification',
    body: 'Code, not a model. Every signature and hash chain is checked first, so nothing unverified ever reaches a specialist.',
  },
  {
    title: 'Review',
    body: 'Ten specialists each answer one question, against published rules. Facts are established first; judgement only sits on top of them.',
  },
  {
    title: 'Decision',
    body: 'The findings go to a regulator with the evidence behind each one. They decide the outcome — authorise, authorise with conditions, refuse, or inconclusive — and sign it.',
  },
]

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
      {/* Hero — the console's front door. Name, then what it is, then what
          it's for: the product name means nothing to a first-time reader, so
          it sits as a kicker and the headline carries the explanation. */}
      <section className="relative overflow-hidden rounded-2xl border bg-card px-8 py-10 shadow-sm md:px-12 md:py-14">
        <BlueprintGrid />
        {/* Two real columns, not text with art floated over it: the mark
            occupies its own track so the copy has a guaranteed measure and
            nothing has to be hand-tuned away from a collision. */}
        <div className="relative grid items-center gap-10 lg:grid-cols-[minmax(0,1fr)_auto]">
          <div className="max-w-[34rem]">
            {/* Nameplate, not an eyebrow. Set in the heading face at
                sentence case and ruled off underneath, the way a masthead
                is — a tracked micro-caps label reads as a section kicker,
                which is exactly the wrong signal for a product name. The
                two-tone wordmark is what makes it unmistakably a name and
                not a heading: "Supervisor" carries the brand blue, and the
                pairing is theme-safe (foreground + a token that already
                redefines itself in dark). */}
            <p className="font-heading text-xl font-semibold leading-none tracking-[-0.015em] text-foreground">
              Mandate <span className="text-brand-blue">Supervisor</span>
            </p>
            {/* The rule fades rather than stopping, so it reads as a
                masthead edge instead of a cut-off border. */}
            <div
              aria-hidden
              className="mt-4 h-px w-full"
              style={{
                backgroundImage:
                  'linear-gradient(to right, color-mix(in oklab, var(--brand-blue) 45%, transparent), color-mix(in oklab, var(--brand-blue) 10%, transparent) 55%, transparent)',
              }}
            />
            {/* "AI payment agents" moves as one unit, so the line never
                breaks after "AI" and orphans it at the end of line one. */}
            <h1 className="mt-6 font-heading text-4xl font-bold leading-[1.06] tracking-tight md:text-[3.25rem]">
              Supervision of <span className="whitespace-nowrap">AI payment agents.</span>
            </h1>
            <p className="mt-5 text-[15px] leading-[1.65] text-pretty text-muted-foreground">
              A regulator&rsquo;s console for checking that an institution&rsquo;s agent{' '}
              {/* The load-bearing phrase: full-strength text over a low
                  highlighter stroke in the brand blue. background-image
                  (not box-shadow) so the stroke re-draws on every line
                  fragment when the sentence wraps. */}
              <span
                className="font-medium text-foreground [box-decoration-break:clone] [-webkit-box-decoration-break:clone]"
                style={{
                  backgroundImage:
                    'linear-gradient(to top, color-mix(in oklab, var(--brand-blue) 22%, transparent) 0.36em, transparent 0.36em)',
                }}
              >
                behaved the way it was meant to
              </span>{' '}
              &mdash; analysing the agent&rsquo;s own records so a regulator can authorise, monitor, or refuse it.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button size="lg" onClick={onOpenQueue} className="font-medium">
                Open cases
                <ArrowRight data-icon="inline-end" />
              </Button>
              <UploadCaseDialog onUploaded={onOpenCase} />
            </div>
          </div>

          {/* The mark's own paper is near-white, so it needs a tinted halo to
              sit on a white card instead of dissolving into it. */}
          <div className="relative hidden lg:block">
            <div
              aria-hidden
              className="pointer-events-none absolute left-1/2 top-1/2 size-[24rem] -translate-x-1/2 -translate-y-1/2"
              style={{
                background:
                  'radial-gradient(closest-side, color-mix(in oklab, var(--brand-blue) 13%, transparent), transparent)',
              }}
            />
            <img src="/logo.png" alt="" aria-hidden className="relative w-56 xl:w-64" />
          </div>
        </div>
      </section>

      {/* How a review works — a rail, not four cards. Four equal boxes
          would carry no sequence; a numbered rail says "this flows", and
          it lands the reader on the bench below already knowing where the
          ten specialists sit in the process. Deliberately icon-free:
          the roster underneath is ten icon rows already. */}
      <section className="mt-12">
        <h2 className="font-heading text-xl font-semibold tracking-tight">How a review works</h2>
        <p className="mt-1 text-sm text-muted-foreground">Four stages, one submission, one decision.</p>

        <div className="relative mt-5 overflow-hidden rounded-xl border bg-card px-5 py-5 md:px-6">
          <BlueprintGrid strength={4} size={24} />
          <div className="relative">
          <ol className="relative grid gap-6 md:grid-cols-4 md:gap-7">
            {/* The rail. Horizontal on wide screens, a left spine when the
                steps stack — drawn behind the nodes, fading out toward the
                end the way the nameplate rule does. */}
            <div
              aria-hidden
              className="pointer-events-none absolute bottom-2 left-[5px] top-2 w-px md:hidden"
              style={{ backgroundImage: RAIL('to bottom') }}
            />
            <div
              aria-hidden
              /* Stops at the final node rather than running on to the card
                 edge — the sequence ends at a decision, so the rail should
                 too. 25% is the last of four equal columns. */
              className="pointer-events-none absolute left-0 right-[25%] top-[5px] hidden h-px md:block"
              style={{ backgroundImage: RAIL('to right') }}
            />
            {STEPS.map((step, i) => (
              <li key={step.title} className="relative pl-7 md:pl-0">
                {/* Hollow while the process is still running; the last node
                    fills, so the rail visibly terminates at a decision. */}
                <span
                  aria-hidden
                  className={cn(
                    'absolute left-0 top-[3px] size-[11px] rounded-full border-2 border-brand-blue bg-card md:top-0',
                    i === STEPS.length - 1 && 'bg-brand-blue',
                  )}
                />
                <div className="md:pt-6">
                  <span className="font-mono text-[11px] font-medium tracking-wider text-brand-blue">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <h3 className="mt-1 font-heading text-[15px] font-semibold tracking-tight">{step.title}</h3>
                  <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">{step.body}</p>
                </div>
              </li>
            ))}
          </ol>

          <p className="mt-5 border-t pt-3 text-[11.5px] leading-snug text-muted-foreground/70">
            Every step is written to an append-only, hash-chained record — so any conclusion can be traced back to the
            evidence that produced it.
          </p>
          </div>
        </div>
      </section>

      {/* The roster, not a card grid. Operate-mode density: the reader
          scans names and jobs, they don't tour ten brochures. The
          sequencing legend that used to sit here is gone — the rail above
          already carries it, and repeating it made the page argue with
          itself about where the process is explained. */}
      <section className="mt-12">
        <h2 className="font-heading text-xl font-semibold tracking-tight">What gets checked</h2>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Ten specialists, one question each — answered against published rules, and reported as findings a human
          can re-check.
        </p>
        {/* The ring on anything wide enough to read it; the roster list
            below that, where ten labelled spokes would collapse into
            a pile. Same ten, two shapes. */}
        <div className="relative mt-6 hidden overflow-hidden rounded-xl border bg-card px-6 py-8 md:block">
          <BlueprintGrid strength={5} size={24} fade="radial" />
          <div className="relative">
            <SpecialistOrbit />
          </div>
        </div>

        <div className="mt-4 overflow-hidden rounded-xl border bg-card md:hidden">
          {SPECIALISTS.map((id, i) => {
            const meta = nodeMeta(id)
            const Icon = meta.icon
            const tone = AGENT_ICON[meta.color]
            return (
              <div key={id} className={cn('flex items-center gap-4 px-5 py-3.5', i > 0 && 'border-t')}>
                <div className={cn('flex size-9 shrink-0 items-center justify-center rounded-lg', tone.bg)}>
                  <Icon className={cn('size-4.5', tone.text)} strokeWidth={2.25} />
                </div>
                <div className="min-w-0 flex-1">
                  <span className="font-heading text-[15px] font-semibold">{meta.label}</span>
                  <span className="mt-0.5 block text-[13px] leading-relaxed text-muted-foreground">{meta.blurb}</span>
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {/* Recent cases — a taste of the list, not the whole list. */}
      <section className="mt-10">
        <div className="flex items-center justify-between">
          <h2 className="font-heading text-xl font-semibold tracking-tight">Recent cases</h2>
          <Button variant="ghost" size="sm" onClick={onOpenQueue}>
            View all cases
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
