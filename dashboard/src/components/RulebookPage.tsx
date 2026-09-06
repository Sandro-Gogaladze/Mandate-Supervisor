import { useEffect, useState } from 'react'
import { ArrowRight, BookOpen } from 'lucide-react'
import { getSandboxDomains } from '@/lib/api'
import type { SandboxDomain } from '@/lib/sandbox-types'
import { Skeleton } from '@/components/ui/skeleton'
import { BlueprintGrid } from '@/components/BlueprintGrid'
import { DocShell } from '@/components/DocShell'
import { nodeMeta } from '@/lib/node-meta'
import { cn } from '@/lib/utils'

/** Sandbox domain → the specialist that owns it, so a reader can get from a
 * rulebook to the agent that runs it. */
const OWNER: Record<string, string> = {
  kya: 'kya',
  mandate: 'mandate',
  consent: 'consent',
  provenance: 'provenance',
  injection: 'injection',
  counterparty: 'counterparty',
  log: 'log',
  drift: 'drift',
  control_assurance: 'control_assurance',
}

/** What each field on a rule is for — the anatomy, once, so the rule lists on
 * the agent pages can be read without a legend. */
const ANATOMY: { field: string; what: string }[] = [
  { field: 'rule_id', what: 'Stable identity, readable by subject — KYA-ACC-03, MND-CAP-01, CTL-DIS-04.' },
  { field: 'status', what: 'active, draft, or retired. A draft rule is evaluated and reported but does not contribute to a decision.' },
  { field: 'evaluation', what: 'computable — decided in code — or judged, decided by a specialist reasoning over deterministic measurements.' },
  { field: 'severity_weight', what: 'The deterministic floor of how serious a breach is. It feeds the score; it is not the score.' },
  { field: 'params', what: 'The tunable dials: thresholds, allowlists, depths. No threshold is hardcoded anywhere in an agent.' },
  { field: 'failures', what: 'Which catalogue entries a breach of this rule establishes — the link between a rule firing and a named harm.' },
  { field: 'version · effective_from', what: 'So a decision can name the rule version it was made under, years later.' },
]

/**
 * The rulebook, explained: what a rule is made of, what the domains are, and
 * how one becomes policy. Counts come from the registry, so the page states
 * what is actually in force rather than what was true when it was written.
 */
export function RulebookPage({ onOpenAgent, onOpenSandbox }: {
  onOpenAgent: (id: string) => void
  onOpenSandbox: () => void
}) {
  const [domains, setDomains] = useState<SandboxDomain[] | null>(null)
  useEffect(() => { getSandboxDomains().then(setDomains).catch(() => setDomains([])) }, [])

  const total = (domains ?? []).reduce((n, d) => n + d.rules, 0)

  return (
    <DocShell>
      <header className="relative overflow-hidden rounded-xl border bg-card px-5 py-5 shadow-sm md:px-6">
        <BlueprintGrid strength={5} size={24} />
        <div className="relative">
          <div className="flex items-center gap-2">
            <BookOpen className="size-4.5 text-muted-foreground" />
            <h1 className="font-heading text-lg font-semibold tracking-tight">The Agent Supervision Rulebook</h1>
          </div>
          <p className="mt-1.5 max-w-2xl text-[13px] leading-relaxed text-muted-foreground">
            Every rule applied to a submission — {total || '103'} of them across {domains?.length || 9} domains, one
            per specialist. No such rulebook exists internationally; this is a proposal for what one looks like.
          </p>
        </div>
      </header>

      <section className="mt-8">
        <h2 className="font-heading text-[15px] font-semibold tracking-tight">Rules are data, not code</h2>
        <p className="mt-1.5 max-w-3xl text-[13px] leading-relaxed text-muted-foreground">
          Rules live in versioned JSON; no threshold is hardcoded in any agent. Each specialist is handed its
          rulebook, so the sandbox can run the real agents against a draft without changing any code.
        </p>
        <dl className="mt-3 overflow-hidden rounded-lg border bg-card">
          {ANATOMY.map((a, i) => (
            <div key={a.field} className={cn('gap-3 px-4 py-2.5 sm:flex', i > 0 && 'border-t')}>
              <dt className="w-52 shrink-0 font-mono text-[11.5px] font-medium">{a.field}</dt>
              <dd className="mt-0.5 text-[13px] leading-snug text-muted-foreground sm:mt-0">{a.what}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="mt-8">
        <h2 className="font-heading text-[15px] font-semibold tracking-tight">The domains</h2>
        <p className="mt-1.5 max-w-3xl text-[13px] leading-relaxed text-muted-foreground">
          One rulebook per specialist, tunable independently. A rule belongs to whichever agent already holds the
          evidence it needs — assigned by evidence, not by topic.
        </p>
        {!domains ? (
          <Skeleton className="mt-3 h-64" />
        ) : (
          <div className="mt-3 overflow-hidden rounded-lg border bg-card">
            {domains.map((d, i) => {
              const owner = OWNER[d.domain]
              return (
                <button
                  key={d.domain}
                  type="button"
                  onClick={() => owner && onOpenAgent(owner)}
                  className={cn(
                    'group flex w-full items-center gap-3 px-4 py-3 text-left outline-none transition-colors hover:bg-accent/40 focus-visible:bg-accent/40',
                    i > 0 && 'border-t',
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <div className="font-heading text-[14px] font-semibold tracking-tight">{d.label}</div>
                    <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                      v{d.version} · {d.rules} rules · {d.judged} judged · {d.tunable} tunable
                    </div>
                  </div>
                  {owner && (
                    <span className="hidden shrink-0 items-center gap-1 text-[12px] text-muted-foreground sm:flex">
                      {nodeMeta(owner).label}
                      <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        )}
      </section>

      <section className="mt-8">
        <h2 className="font-heading text-[15px] font-semibold tracking-tight">How a rule becomes policy</h2>
        <p className="mt-1.5 max-w-3xl text-[13px] leading-relaxed text-muted-foreground">
          Never by editing a file and shipping it.
        </p>
        <ol className="mt-3 overflow-hidden rounded-lg border bg-card">
          {[
            ['Fork', 'The book in force is copied. Nothing you are looking at can change under you.'],
            ['Edit', 'Change a status, a weight, a threshold. Rules are data, so this is an edit, not a deployment.'],
            ['Sweep', 'Run the draft over every labelled submission through the real pipeline. No model calls, seconds.'],
            ['Compare', 'Against the book in force: which cases flip, what appears, which rules stop firing at all.'],
            ['Promote', 'A named person, a reason, and the sweep id — so the evidence behind the change is on the record.'],
          ].map(([step, what], i) => (
            <li key={step} className={cn('flex gap-3 px-4 py-2.5', i > 0 && 'border-t')}>
              <span className="w-6 shrink-0 font-mono text-[11px] text-brand-blue">{String(i + 1).padStart(2, '0')}</span>
              <span className="min-w-0">
                <span className="font-heading text-[13.5px] font-semibold">{step}</span>
                <span className="mt-0.5 block text-[13px] leading-snug text-muted-foreground">{what}</span>
              </span>
            </li>
          ))}
        </ol>
        <button
          type="button"
          onClick={onOpenSandbox}
          className="mt-3 inline-flex items-center gap-1.5 text-[13px] font-medium text-brand-blue outline-none hover:underline"
        >
          Open the policy sandbox
          <ArrowRight className="size-3.5" />
        </button>
      </section>

      <section className="mt-8">
        <h2 className="font-heading text-[15px] font-semibold tracking-tight">What a draft rule means</h2>
        <p className="mt-1.5 max-w-3xl text-[13px] leading-relaxed text-muted-foreground">
          Not an unfinished rule — one whose evidence a submission cannot yet carry, or whose threshold the sandbox
          must still tune. It is evaluated and reported, but does not count toward a decision.
        </p>
        <p className="mt-3 rounded-lg border-l-2 border-brand-blue/40 bg-muted/30 px-4 py-2.5 text-[13px] leading-relaxed text-muted-foreground">
          Four rules turned out to be wrong once run against realistic data: one breached every consumer purchase ever
          made, one failed every non-bank operator, one sat above the agent’s largest transaction and so never fired,
          and one breached every run on record. None was visible before the sweep — which is the argument for the
          sandbox.
        </p>
      </section>
    </DocShell>
  )
}
