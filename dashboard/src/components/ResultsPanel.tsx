import { useState } from 'react'
import { AlertTriangle, ChevronRight, CircleSlash, Eye, Gauge, GitMerge, ListChecks, Route, SearchCheck } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { FailureList } from '@/components/FailureList'
import { nodeMeta, AGENT_TONE } from '@/lib/node-meta'
import { cn } from '@/lib/utils'
import type {
  Correlation,
  DispatchPlan,
  DispositionTier,
  Finding,
  FindingAgent,
  FailureOccurrence,
  InvestigationAnswer,
  Observation,
  ObservationAgent,
  RiskScore,
} from '@/lib/types'

export const TIER_TONE: Record<DispositionTier, string> = {
  clear: 'bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-400',
  review: 'bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-400',
  escalate: 'bg-red-500/10 text-red-700 border-red-500/30 dark:text-red-400',
}

/** What the results panel renders — the ledger projection, or the live
 * triage overlay while a run streams (CaseReview builds it). */
export interface ResultsView {
  findings: Finding[]
  failure_occurrences: FailureOccurrence[]
  observations: Observation[]
  correlations: Correlation[]
  dispatch_plan?: DispatchPlan
  escalation_round?: number
  risk_score?: RiskScore
}

function ScoreCard({ score }: { score: RiskScore }) {
  const maxFactor = Math.max(...score.factors.map((f) => f.score), 0.0001)
  return (
    <div className="rounded-lg border bg-muted/30 p-3.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <Gauge className="size-3.5" />
          Risk score
        </div>
        <span className="font-mono text-[10px] text-muted-foreground">weights · config {score.config_version}</span>
      </div>
      <div className="mt-2 flex items-center gap-3">
        <span className="font-mono text-3xl font-bold tracking-tight">{score.total.toFixed(2)}</span>
        <Badge variant="outline" className={cn('gap-1 text-xs font-semibold uppercase', TIER_TONE[score.tier])}>
          {score.tier_label}
        </Badge>
        <span className="text-xs text-muted-foreground">{score.tier_guidance}</span>
      </div>
      <div className="mt-3 flex flex-col gap-1.5">
        {score.factors.map((f) => {
          const meta = nodeMeta(f.agent)
          return (
            <div key={f.agent} className="flex items-center gap-2 text-xs">
              {/* Specialist names run to "Consent & Harm"; a narrower column
                  wrapped them onto a second line and knocked the bars out of
                  their grid. */}
              <span className="w-28 shrink-0 truncate font-medium text-muted-foreground" title={meta.label}>
                {meta.label}
              </span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-border/60">
                <div
                  className={cn('h-full rounded-full transition-all', f.score > 0 ? 'bg-primary' : 'bg-transparent')}
                  style={{ width: `${(f.score / maxFactor) * 100}%` }}
                />
              </div>
              <span className="w-16 shrink-0 whitespace-nowrap text-right font-mono">
                {f.score.toFixed(2)}
                <span className="text-muted-foreground"> ·{f.finding_count}</span>
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function SectionTitle({ icon: Icon, children }: { icon: typeof AlertTriangle; children: React.ReactNode }) {
  return (
    <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
      <Icon className="size-3.5" />
      {children}
    </h3>
  )
}

function AgentChip({ agent }: { agent: ObservationAgent }) {
  const meta = nodeMeta(agent)
  const Icon = meta.icon
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase', AGENT_TONE[meta.color])}>
      <Icon className="size-3" />
      {meta.label}
    </span>
  )
}

const RELATIONSHIP_LABEL: Record<Correlation['relationship'], string> = {
  same_event: 'same event',
  causal: 'causal',
  corroborating: 'corroborating',
  contradictory: 'contradictory',
}

/** Everything that is not the headline. Six sections all open at once was
 * the complaint: a reviewer scanning a case wants the failures, and reaches
 * for the plan, the correlations or the unscored notes only when a failure
 * makes them want to. */
function Drawer({ icon, title, children }: { icon: typeof AlertTriangle; title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div>
      <Separator className="mb-3" />
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center gap-1.5 text-left">
        <ChevronRight className={cn('size-3.5 text-muted-foreground transition-transform', open && 'rotate-90')} />
        <SectionTitle icon={icon}>{title}</SectionTitle>
      </button>
      {open && <div className="mt-2">{children}</div>}
    </div>
  )
}


export function ResultsPanel({ view, answers }: { view: ResultsView; answers: InvestigationAnswer[] }) {
  const { findings, failure_occurrences, observations, correlations, dispatch_plan: plan, risk_score } = view
  // Grouped by the specialist that established them, because "which agent
  // found this" is the first question a reviewer asks of a failure list.
  const byDomain = Object.entries(
    failure_occurrences.reduce<Record<string, FailureOccurrence[]>>((acc, o) => {
      (acc[o.domain] ??= []).push(o)
      return acc
    }, {}),
  )
  const hasAnything = plan || failure_occurrences.length > 0 || findings.length > 0 || observations.length > 0 || risk_score || answers.length > 0

  if (!hasAnything) {
    return (
      <div className="flex min-h-[40vh] flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground">
        <ListChecks className="size-6 text-muted-foreground/40" />
        <p>Findings and observations will appear here as agents report in.</p>
      </div>
    )
  }

  // No scroll container of its own: the Findings tab is one page — the drafted
  // report and then the record it cites — and a second scroller inside it
  // trapped the wheel and pinned the report half off-screen.
  return (
    <div className="flex flex-col gap-5">
      {risk_score && <ScoreCard score={risk_score} />}

      {plan && (
        <Drawer icon={Route} title="Dispatch plan">
          <div className="flex flex-wrap gap-1.5">
            {(plan.skills ?? []).map((skill) => {
              const agent = skill.split('.')[0] as FindingAgent
              const meta = nodeMeta(agent)
              const Icon = meta.icon
              return (
                <Badge key={skill} variant="default" className="gap-1">
                  <Icon className="size-3" />
                  {meta.label}
                </Badge>
              )
            })}
            {(plan.not_dispatched ?? []).map((skill) => {
              const meta = nodeMeta(skill.split('.')[0])
              return (
                <Badge key={skill} variant="outline" className={cn('gap-1 text-muted-foreground/60 line-through')}>
                  {meta.label}
                </Badge>
              )
            })}
            {(view.escalation_round ?? 0) > 0 && (
              <Badge variant="secondary" className="gap-1">
                escalation round {view.escalation_round}
              </Badge>
            )}
          </div>
          <p className="mt-2.5 text-sm leading-relaxed text-muted-foreground">{plan.reasoning}</p>
        </Drawer>
      )}

      {failure_occurrences.length > 0 && (
        <div>
          <Separator className="mb-4" />
          <SectionTitle icon={AlertTriangle}>Detected failures ({failure_occurrences.length})</SectionTitle>
          <p className="mt-1 text-[11px] text-muted-foreground">
            Exact catalogue failures, projected from rule assessments and linked to their supporting facts and runs.
          </p>
          <div className="mt-2 flex flex-col gap-3">
            {byDomain.map(([domain, group]) => (
              <div key={domain}>
                <AgentChip agent={domain as ObservationAgent} />
                <div className="mt-1.5"><FailureList occurrences={group} /></div>
              </div>
            ))}
          </div>
        </div>
      )}

      {findings.length > 0 && (
        <Drawer icon={AlertTriangle} title={`All findings (${findings.length}) — including those mapping to no catalogue failure`}>
          <div className="flex flex-col gap-2">
            {findings.map((f) => (
              <div key={f.finding_id} className="rounded-lg border p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <AgentChip agent={f.agent} />
                  <span className="font-mono text-[10px] text-muted-foreground">{f.type}</span>
                </div>
                <p className="mt-2 leading-relaxed">{f.summary}</p>
                <div className="mt-1.5 flex items-center gap-1.5">
                  {f.rule_id && (
                    <span className="inline-block rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                      {f.rule_id}
                    </span>
                  )}
                  <span className="font-mono text-[10px] text-muted-foreground/60">{f.finding_id}</span>
                </div>
              </div>
            ))}
          </div>
        </Drawer>
      )}

      {correlations.length > 0 && (
        <Drawer icon={GitMerge} title={`Correlations (${correlations.length})`}>
          <p className="text-[11px] text-muted-foreground">
            Relationships between findings — validated against real finding ids, never scored.
          </p>
          <div className="mt-2 flex flex-col gap-2">
            {correlations.map((c, i) => (
              <div key={i} className="rounded-lg border border-indigo-500/25 bg-indigo-500/[0.04] p-3 text-sm">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge variant="outline" className="gap-1 border-indigo-500/30 text-[10px] uppercase text-indigo-700 dark:text-indigo-400">
                    {RELATIONSHIP_LABEL[c.relationship]}
                  </Badge>
                  {c.finding_ids.map((fid) => (
                    <span key={fid} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                      {fid}
                    </span>
                  ))}
                </div>
                <p className="mt-2 leading-relaxed">{c.explanation}</p>
              </div>
            ))}
          </div>
        </Drawer>
      )}

      {answers.length > 0 && (
        <Drawer icon={SearchCheck} title={`Investigation answers (${answers.length})`}>
          <div className="flex flex-col gap-2">
            {answers.map((a) => (
              <div key={a.question_id} className="rounded-lg border border-teal-500/25 bg-teal-500/[0.04] p-3 text-sm">
                <p className="text-[13px] font-medium">“{a.question}”</p>
                <p className="mt-1.5 leading-relaxed">{a.answer}</p>
                {a.tool_calls.length > 0 && (
                  <p className="mt-1.5 font-mono text-[10px] text-muted-foreground">
                    trail: {a.tool_calls.map((t) => t.tool).join(' → ')}
                  </p>
                )}
              </div>
            ))}
          </div>
        </Drawer>
      )}

      {observations.length > 0 && (
        <Drawer icon={Eye} title={`Unverified observations (${observations.length})`}>
          <p className="flex items-center gap-1 text-[11px] text-muted-foreground">
            <CircleSlash className="size-3" />
            Unverified model hunches — surfaced for a human reviewer, never scored.
          </p>
          <div className="mt-2 flex flex-col gap-2">
            {observations.map((o, i) => (
              <div key={i} className="rounded-lg border border-dashed p-3 text-sm">
                <AgentChip agent={o.agent} />
                <p className="mt-2 leading-relaxed">{o.note}</p>
                <p className="mt-1.5 text-[11px] italic text-muted-foreground">{o.cited_evidence}</p>
              </div>
            ))}
          </div>
        </Drawer>
      )}
    </div>
  )
}
