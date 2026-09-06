import { useEffect, useState } from 'react'
import { getFailureCatalogue, getRulebook, type FailureEntry } from '@/lib/api'
import type { RulebookView } from '@/lib/sandbox-types'
import { AGENT_DOCS } from '@/lib/agent-docs'
import { nodeMeta, AGENT_ICON } from '@/lib/node-meta'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { BlueprintGrid } from '@/components/BlueprintGrid'
import { DocShell } from '@/components/DocShell'
import { cn } from '@/lib/utils'

/** A section rule: a small caps label with a hairline running out from it.
 * Cheaper vertically than an icon-and-heading pair, and it reads as a
 * document's structure rather than as another card. */
function Rule({ label, meta }: { label: string; meta?: string }) {
  return (
    <div className="mt-7 flex items-center gap-3">
      <h2 className="shrink-0 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{label}</h2>
      {meta && <span className="shrink-0 font-mono text-[10.5px] text-muted-foreground/70">{meta}</span>}
      <div className="h-px flex-1 bg-border" />
    </div>
  )
}

/** One row of the spec sheet: term on the left, definition on the right. */
function Spec({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 border-t px-4 py-2.5 first:border-t-0 sm:flex-row sm:gap-4">
      <dt className="w-40 shrink-0 pt-[1px] text-[12px] font-medium text-foreground/80">{term}</dt>
      <dd className="min-w-0 flex-1 text-[12.5px] leading-[1.55] text-muted-foreground">{children}</dd>
    </div>
  )
}

/**
 * The reference page for one specialist, laid out as a spec sheet rather than
 * a stack of titled cards: the four things that define an agent — what it is
 * given, what it decides in code, what its one model call decides, what it
 * hands back — are parallel facts, so they belong in one table where they can
 * be compared, not in four blocks each with its own heading and preamble.
 *
 * Prose comes from `agent-docs`; everything countable is read live from the
 * registry, so a page can never claim a rulebook the system is not running.
 */
export function AgentPage({ agentId }: { agentId: string }) {
  const doc = AGENT_DOCS[agentId]
  const meta = nodeMeta(agentId)
  const tone = AGENT_ICON[meta.color]
  const Icon = meta.icon

  const [book, setBook] = useState<RulebookView | null>(null)
  const [failures, setFailures] = useState<FailureEntry[] | null>(null)

  useEffect(() => {
    setBook(null)
    if (doc?.rulebook) getRulebook(doc.rulebook).then(setBook).catch(() => setBook(null))
  }, [doc?.rulebook])

  useEffect(() => {
    getFailureCatalogue().then((c) => setFailures(c.failures)).catch(() => setFailures([]))
  }, [])

  if (!doc) return <div className="p-8 text-sm text-muted-foreground">No reference page for “{agentId}”.</div>

  const owned = (failures ?? []).filter((f) => doc.failureDomain && f.domain === doc.failureDomain)
  const rules = book?.ruleset.rules ?? []

  return (
    <DocShell>
      <header className="relative overflow-hidden rounded-lg border bg-card px-4 py-3.5 shadow-xs md:px-5">
        <BlueprintGrid strength={5} size={24} />
        <div className="relative flex items-center gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-md border bg-background">
            <Icon className={cn('size-4.5', tone.text)} strokeWidth={2} />
          </span>
          <div className="min-w-0">
            {/* Name and question on one line where there's room: the question
                is the definition of the specialist, not a subtitle to it. */}
            <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
              <h1 className="font-heading text-[17px] font-semibold tracking-tight">{meta.label}</h1>
              <p className="text-[13px] text-muted-foreground">{doc.question}</p>
            </div>
            <Badge variant="outline" className="mt-1 font-mono text-[10px] font-normal">
              {doc.phase.id === '—' ? 'on demand' : `${doc.phase.id} · ${doc.phase.title}`}
            </Badge>
          </div>
        </div>
      </header>

      <Rule label="How it works" />
      <dl className="mt-2.5 overflow-hidden rounded-lg border bg-card">
        <Spec term="Receives">
          <ul className="space-y-1">
            {doc.receives.map((r) => (
              <li key={r} className="flex gap-2">
                <span aria-hidden className="mt-[0.55em] size-1 shrink-0 rounded-full bg-brand-blue/60" />
                {r}
              </li>
            ))}
          </ul>
        </Spec>
        <Spec term="Deterministic floor">{doc.floor}</Spec>
        <Spec term="Model call">
          {doc.model ?? (
            <span>
              <span className="font-medium text-foreground">None.</span> Entirely deterministic — the same submission
              produces the same result, with no key and no model.
            </span>
          )}
        </Spec>
        <Spec term="Produces">{doc.produces}</Spec>
      </dl>

      {doc.failureDomain && (
        <>
          <Rule label="Failures it owns" meta={failures ? `${owned.length}` : undefined} />
          {!failures ? (
            <Skeleton className="mt-2.5 h-32" />
          ) : (
            <div className="mt-2.5 overflow-hidden rounded-lg border bg-card">
              {owned.map((f, i) => (
                <div key={f.failure_id} className={cn('flex gap-3 px-4 py-1.5', i > 0 && 'border-t')}>
                  <span className="w-7 shrink-0 font-mono text-[11px] font-medium text-brand-blue">{f.failure_id}</span>
                  <span className="min-w-0 flex-1 text-[12.5px] leading-snug">{f.name}</span>
                  {f.mapped_rules.length === 0 && (
                    <span className="shrink-0 text-[10.5px] text-muted-foreground">
                      {f.non_rule_detector ? `${f.non_rule_detector} sweep` : 'no rule yet'}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {doc.rulebook && (
        <>
          <Rule
            label="The rules it runs"
            meta={book ? `${book.ruleset.ruleset_id} · v${book.ruleset.version}` : undefined}
          />
          {!book ? (
            <Skeleton className="mt-2.5 h-48" />
          ) : (
            <div className="mt-2.5 overflow-hidden rounded-lg border bg-card">
              {rules.map((r, i) => (
                <div key={r.rule_id} className={cn('px-4 py-2.5', i > 0 && 'border-t', r.status !== 'active' && 'opacity-55')}>
                  <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                    <code className="font-mono text-[11px] font-semibold">{r.rule_id}</code>
                    {r.status !== 'active' && (
                      <span className="rounded bg-muted px-1 py-px text-[9.5px] uppercase text-muted-foreground">{r.status}</span>
                    )}
                    {r.evaluation === 'judged' && (
                      <span className="rounded bg-muted px-1 py-px text-[9.5px] uppercase text-muted-foreground">judged</span>
                    )}
                    <span className="ml-auto font-mono text-[10.5px] text-muted-foreground/70">
                      {r.severity_weight.toFixed(2)}
                      {r.failures.length > 0 && ` · ${r.failures.join(' ')}`}
                    </span>
                  </div>
                  <p className="mt-0.5 text-[12.5px] leading-[1.5] text-muted-foreground">{r.description}</p>
                  {Object.keys(r.params).length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-x-3 font-mono text-[10.5px] text-muted-foreground/80">
                      {Object.entries(r.params).map(([k, v]) => (
                        <span key={k}>
                          <span className="opacity-60">{k}</span>{' '}
                          {Array.isArray(v) ? (v as unknown[]).join(', ') : String(v)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {doc.notes.length > 0 && (
        <>
          <Rule label="Worth knowing" />
          <div className="mt-2.5 space-y-2">
            {doc.notes.map((n) => (
              <p key={n} className="border-l-2 border-brand-blue/40 pl-3 text-[12.5px] leading-[1.55] text-muted-foreground">
                {n}
              </p>
            ))}
          </div>
        </>
      )}
    </DocShell>
  )
}
