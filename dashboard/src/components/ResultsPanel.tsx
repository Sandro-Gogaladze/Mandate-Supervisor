import { AlertTriangle, CircleSlash, Eye, Gauge, ListChecks, Route } from 'lucide-react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { nodeMeta, AGENT_TONE } from '@/lib/node-meta'
import { cn } from '@/lib/utils'
import type { SupervisionAgentState } from '@/lib/agent-state'
import type { DispositionTier, FindingAgent, RiskScore } from '@/lib/types'

export const TIER_TONE: Record<DispositionTier, string> = {
  clear: 'bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-400',
  review: 'bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-400',
  escalate: 'bg-red-500/10 text-red-700 border-red-500/30 dark:text-red-400',
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
        {/* DESIGN.md: numbers are data, data is mono. */}
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
              <span className="w-16 shrink-0 font-medium text-muted-foreground">{meta.label}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-border/60">
                <div
                  className={cn('h-full rounded-full transition-all', f.score > 0 ? 'bg-primary' : 'bg-transparent')}
                  style={{ width: `${(f.score / maxFactor) * 100}%` }}
                />
              </div>
              <span className="w-14 shrink-0 text-right font-mono">
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

function AgentChip({ agent }: { agent: FindingAgent }) {
  const meta = nodeMeta(agent)
  const Icon = meta.icon
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase', AGENT_TONE[meta.color])}>
      <Icon className="size-3" />
      {meta.label}
    </span>
  )
}

export function ResultsPanel({ state }: { state: SupervisionAgentState }) {
  const plan = state.dispatch_plan
  const findings = state.findings ?? []
  const observations = state.observations ?? []
  const hasAnything = plan || findings.length > 0 || observations.length > 0 || state.risk_score

  if (!hasAnything) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground">
        <ListChecks className="size-6 text-muted-foreground/40" />
        <p>Findings and observations will appear here as agents report in.</p>
      </div>
    )
  }

  return (
    <ScrollArea className="h-full">
      <div className="flex flex-col gap-5 p-4">
        {state.risk_score && <ScoreCard score={state.risk_score} />}

        {plan && (
          <div>
            <SectionTitle icon={Route}>Dispatch plan</SectionTitle>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {(['run_mandate', 'run_kya', 'run_log', 'run_drift'] as const).map((key) => {
                const agent = key.replace('run_', '') as FindingAgent
                const meta = nodeMeta(agent)
                const Icon = meta.icon
                return (
                  <Badge
                    key={key}
                    variant={plan[key] ? 'default' : 'outline'}
                    className={cn('gap-1', !plan[key] && 'text-muted-foreground/60 line-through')}
                  >
                    <Icon className="size-3" />
                    {meta.label}
                  </Badge>
                )
              })}
              {(state.escalation_round ?? 0) > 0 && (
                <Badge variant="secondary" className="gap-1">
                  escalation round {state.escalation_round}
                </Badge>
              )}
            </div>
            <p className="mt-2.5 text-sm leading-relaxed text-muted-foreground">{plan.reasoning}</p>
          </div>
        )}

        {findings.length > 0 && (
          <div>
            <Separator className="mb-4" />
            <SectionTitle icon={AlertTriangle}>Findings ({findings.length})</SectionTitle>
            <div className="mt-2 flex flex-col gap-2">
              {findings.map((f) => (
                <div key={f.finding_id} className="rounded-lg border p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <AgentChip agent={f.agent} />
                    <span className="font-mono text-[10px] text-muted-foreground">{f.type}</span>
                  </div>
                  <p className="mt-2 leading-relaxed">{f.summary}</p>
                  {f.rule_id && (
                    <span className="mt-1.5 inline-block rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                      {f.rule_id}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {observations.length > 0 && (
          <div>
            <Separator className="mb-4" />
            <SectionTitle icon={Eye}>Observations ({observations.length})</SectionTitle>
            <p className="mt-1 flex items-center gap-1 text-[11px] text-muted-foreground">
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
          </div>
        )}
      </div>
    </ScrollArea>
  )
}
