import { useEffect, useState } from 'react'
import { ShieldAlert } from 'lucide-react'
import { getFailureCatalogue, type FailureEntry } from '@/lib/api'
import { Skeleton } from '@/components/ui/skeleton'
import { BlueprintGrid } from '@/components/BlueprintGrid'
import { DocShell } from '@/components/DocShell'
import { nodeMeta } from '@/lib/node-meta'
import { cn } from '@/lib/utils'

/**
 * The seven phases of an agent's life, plus the cross-cutting one. Ordering
 * and prose from docs/explainer/05-the-failure-catalogue.md; the failures
 * themselves are read live from the registry.
 */
const PHASES: { id: string; title: string; gist: string; agents: string[] }[] = [
  {
    id: 'P0',
    title: 'The agent comes into existence',
    gist: 'Before an agent can pay for anything, somebody has to vouch for it. This phase asks whether that vouching is worth anything.',
    agents: ['kya'],
  },
  {
    id: 'P1',
    title: 'A human authorises it',
    gist: 'The part of the system that is actually about the consumer — whether a person was there, saw what they were agreeing to, and is better off for it.',
    agents: ['consent'],
  },
  {
    id: 'P2',
    title: 'The agent assembles a cart',
    gist: 'Where the published research says the attacks actually live, and where signed artifacts are structurally blind — all of it happens before anything is signed.',
    agents: ['provenance', 'injection'],
  },
  {
    id: 'P3',
    title: 'The mandate is signed',
    gist: 'The classic scope questions: did the agent stay inside what the human actually authorised?',
    agents: ['mandate'],
  },
  {
    id: 'P4',
    title: 'The payment executes',
    gist: 'We verified the payer exhaustively and never once checked the payee. AML has always been about the other side of the transaction.',
    agents: ['counterparty'],
  },
  {
    id: 'P5',
    title: 'Many payments accumulate',
    gist: 'No single transaction is wrong. The set is.',
    agents: ['log', 'drift'],
  },
  {
    id: 'P6',
    title: 'Many agents act at once',
    gist: 'The one structural advantage a supervisor has over any single firm: seeing every supervised institution at the same time.',
    agents: ['systemic'],
  },
  {
    id: 'X1',
    title: 'The firm’s own controls run',
    gist: 'Cross-cutting. The difference between a detection tool and a supervision tool — did the controls the firm declared actually do their job?',
    agents: ['control_assurance'],
  },
]

/**
 * The shared vocabulary of harm. Every rule in every rulebook declares which
 * of these entries its breach establishes, which is what lets a finding name
 * a harm instead of a rule id — and what lets Control Assurance learn from
 * its peers' facts alone that a risk materialised.
 */
export function CataloguePage() {
  const [data, setData] = useState<{ version: string; as_of: string; failures: FailureEntry[] } | null>(null)
  useEffect(() => { getFailureCatalogue().then(setData).catch(() => setData(null)) }, [])

  const failures = data?.failures ?? []
  const uncovered = failures.filter((f) => f.mapped_rules.length === 0 && !f.non_rule_detector).length

  return (
    <DocShell>
      <header className="relative overflow-hidden rounded-xl border bg-card px-5 py-5 shadow-sm md:px-6">
        <BlueprintGrid strength={5} size={24} />
        <div className="relative">
          <div className="flex items-center gap-2">
            <ShieldAlert className="size-4.5 text-muted-foreground" />
            <h1 className="font-heading text-lg font-semibold tracking-tight">The failure catalogue</h1>
          </div>
          <p className="mt-1.5 max-w-2xl text-[13px] leading-relaxed text-muted-foreground">
            The {failures.length || ''} ways an AI payment agent can go wrong, each with a permanent id. Every rule
            points at one of them, so a failed check names the harm, not just the rule.
          </p>
          {data && (
            <p className="mt-2 font-mono text-[11px] text-muted-foreground">
              catalogue {data.version} · as of {data.as_of}
              {uncovered > 0 && ` · ${uncovered} not yet covered by a rule`}
            </p>
          )}
        </div>
      </header>

      <section className="mt-7">
        <h2 className="font-heading text-[15px] font-semibold tracking-tight">How it is organised</h2>
        <p className="mt-1.5 max-w-3xl text-[13px] leading-relaxed text-muted-foreground">
          Grouped by <span className="font-medium text-foreground">when in an agent’s life the failure happens</span> —
          from being issued a credential, to a person authorising it, to building a cart, signing, paying, and the
          patterns that only show up across many payments or many firms. One specialist owns each phase.
        </p>
        <p className="mt-2 max-w-3xl text-[13px] leading-relaxed text-muted-foreground">
          Nearly a third sits in the first phase — whether the agent should have operated at all. And everything in the
          cart-building phase happens <span className="font-medium text-foreground">before anything is signed</span>,
          which is why signature checks cannot find it.
        </p>
      </section>

      {!data ? (
        <div className="mt-8 flex flex-col gap-3">
          {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-40" />)}
        </div>
      ) : (
        PHASES.map((phase) => {
          const rows = failures.filter((f) => f.phase === phase.id)
          if (rows.length === 0) return null
          return (
            <section key={phase.id} className="mt-8">
              <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
                <span className="font-mono text-[12px] font-semibold text-brand-blue">{phase.id}</span>
                <h2 className="font-heading text-[15px] font-semibold tracking-tight">{phase.title}</h2>
                <span className="text-[12px] text-muted-foreground">
                  {rows.length} failure{rows.length === 1 ? '' : 's'} ·{' '}
                  {phase.agents.map((a) => nodeMeta(a).label).join(' · ')}
                </span>
              </div>
              <p className="mt-1 max-w-3xl text-[13px] leading-relaxed text-muted-foreground">{phase.gist}</p>
              <div className="mt-3 overflow-hidden rounded-lg border bg-card">
                {rows.map((f, i) => (
                  <div key={f.failure_id} className={cn('flex gap-3 px-4 py-2.5', i > 0 && 'border-t')}>
                    <span className="w-8 shrink-0 font-mono text-[11px] font-semibold text-brand-blue">
                      {f.failure_id}
                    </span>
                    <span className="min-w-0 flex-1 text-[13px] leading-snug">{f.name}</span>
                    {f.mapped_rules.length === 0 && (
                      <span className="shrink-0 text-[11px] text-muted-foreground">
                        {f.non_rule_detector ? `${f.non_rule_detector} sweep` : 'no rule yet'}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )
        })
      )}

      <section className="mt-8">
        <p className="rounded-lg border-l-2 border-brand-blue/40 bg-muted/30 px-4 py-2.5 text-[13px] leading-relaxed text-muted-foreground">
          <span className="font-medium text-foreground">No rule yet</span> is deliberate: a harm the system can name
          but cannot yet detect from the evidence a submission carries. Published rather than hidden.
        </p>
      </section>
    </DocShell>
  )
}
