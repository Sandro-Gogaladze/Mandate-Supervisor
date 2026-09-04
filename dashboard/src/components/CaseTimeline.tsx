// The ledger, rendered — who did what, when, and what was sent to whom.
// This surface is the point of the architecture: auditability you can SEE,
// not a claim in a slide. Rows come straight from GET /ledger/{case_id};
// The milestone strip is derived (which run counts as "the" review depends
// on whether the history was cleared); the log below is verbatim.
import { useEffect, useState } from 'react'
import {
  BadgeCheck,
  Bot,
  FileClock,
  Fingerprint,
  Gauge,
  GitMerge,
  RotateCcw,
  Inbox,
  ListChecks,
  MessageCircleQuestion,
  ScrollText,
  Send,
  ShieldAlert,
  ShieldCheck,
  UserRound,
  Waypoints,
  type LucideIcon,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { getLedgerEvents, verifyLedger } from '@/lib/api'
import type { LedgerEvent } from '@/lib/types'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

const EVENT_META: Record<string, { icon: LucideIcon; label: string; tone?: string }> = {
  dossier_submitted: { icon: Inbox, label: 'Dossier submitted' },
  fact_recorded: { icon: ListChecks, label: 'Fact recorded' },
  assessment_recorded: { icon: ShieldCheck, label: 'Assessment recorded' },
  authorisation_computed: { icon: Gauge, label: 'Authorisation recommendation' },
  authorisation_decided: { icon: BadgeCheck, label: 'Authorisation signed' },
  control_posture_recorded: { icon: ShieldCheck, label: 'Control posture' },
  run_evaluated: { icon: ListChecks, label: 'Execution evaluated' },
  specialist_failed: { icon: ShieldAlert, label: 'Judgment unavailable' },
  case_watched: { icon: BadgeCheck, label: 'Standing watch' },
  portfolio_sweep_started: { icon: Waypoints, label: 'Portfolio sweep started' },
  portfolio_sweep_completed: { icon: BadgeCheck, label: 'Portfolio sweep completed' },
  portfolio_finding_recorded: { icon: GitMerge, label: 'Portfolio finding' },
  case_submitted: { icon: Inbox, label: 'Case submitted' },
  case_opened: { icon: UserRound, label: 'Case opened' },
  run_started: { icon: Waypoints, label: 'Run started' },
  dispatch_planned: { icon: Waypoints, label: 'Dispatch planned' },
  dispatch_recorded: { icon: Send, label: 'Agent briefed' },
  finding_recorded: { icon: ShieldAlert, label: 'Finding recorded', tone: 'text-amber-700 dark:text-amber-400' },
  observation_recorded: { icon: ListChecks, label: 'Observation recorded' },
  critic_checked: { icon: ShieldCheck, label: 'Critic check' },
  correlation_recorded: { icon: GitMerge, label: 'Correlation recorded' },
  escalation_round_started: { icon: GitMerge, label: 'Escalation round' },
  score_computed: { icon: Gauge, label: 'Score computed' },
  run_completed: { icon: BadgeCheck, label: 'Run completed' },
  question_asked: { icon: MessageCircleQuestion, label: 'Question asked' },
  investigation_completed: { icon: ScrollText, label: 'Investigation answered' },
  report_drafted: { icon: ScrollText, label: 'Report drafted' },
  grounding_checked: { icon: ShieldCheck, label: 'Grounding checked' },
  report_blocked: { icon: ShieldAlert, label: 'Report blocked', tone: 'text-red-700 dark:text-red-400' },
  decision_recorded: { icon: BadgeCheck, label: 'Decision recorded', tone: 'text-emerald-700 dark:text-emerald-400' },
  case_closed: { icon: BadgeCheck, label: 'Case closed' },
  failure_occurrence_recorded: { icon: ShieldAlert, label: 'Catalogue failure recorded', tone: 'text-red-700 dark:text-red-400' },
  orchestrator_replied: { icon: MessageCircleQuestion, label: 'Orchestrator replied' },
  review_history_cleared: { icon: RotateCcw, label: 'Review history cleared', tone: 'text-muted-foreground' },
}

/** The three dates a supervisor actually asks the record for. Everything
 * below is the full event log; this is the case at a glance.
 *
 * `clearedSeq` matters: after a reset the case has not been reviewed, so the
 * review and decision dates must clear with it even though the events are
 * still on the ledger below. */
function Milestones({ events }: { events: LedgerEvent[] }) {
  const clearedSeq = Math.max(0, ...events.filter((e) => e.event_type === 'review_history_cleared').map((e) => e.seq))
  const live = events.filter((e) => e.seq > clearedSeq)
  const submitted = events.find((e) => e.event_type === 'case_submitted' || e.event_type === 'dossier_submitted')
  const reviewed = [...live].reverse().find((e) => e.event_type === 'run_completed'
    && ['triage', 'investigation'].includes(String((e.payload as Record<string, unknown>).kind)))
  const signed = [...live].reverse().find((e) => e.event_type === 'authorisation_decided')
  const when = (e?: LedgerEvent) => e && new Date(e.recorded_at).toLocaleString('en-GB',
    { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })

  const items: { label: string; value: string | undefined; detail?: string }[] = [
    { label: 'Submitted', value: when(submitted) },
    {
      label: 'Reviewed',
      value: when(reviewed),
      detail: reviewed ? String((reviewed.payload as Record<string, unknown>).run_id ?? '') : undefined,
    },
    {
      label: 'Decision signed',
      value: when(signed),
      detail: signed
        ? [(signed.payload as Record<string, unknown>).disposition, (signed.payload as Record<string, unknown>).reviewer]
            .filter(Boolean).join(' · ')
        : undefined,
    },
  ]
  return (
    <dl className="grid grid-cols-1 gap-3 border-b px-4 py-3 sm:grid-cols-3">
      {items.map((item) => (
        <div key={item.label}>
          <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">{item.label}</dt>
          <dd className={cn('mt-0.5 text-[13px]', item.value ? 'font-medium' : 'text-muted-foreground')}>
            {item.value ?? 'Not yet'}
          </dd>
          {item.detail && <dd className="font-mono text-[10px] text-muted-foreground">{item.detail}</dd>}
        </div>
      ))}
    </dl>
  )
}

function actorChip(actor: string) {
  const [kind, ...rest] = actor.split(':')
  const name = rest.join(':')
  const Icon = kind === 'human' ? UserRound : kind === 'agent' ? Bot : Fingerprint
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 font-mono text-[10px]',
        kind === 'human'
          ? 'border-primary/30 bg-primary/5 text-primary'
          : kind === 'agent'
            ? 'border-violet-500/25 bg-violet-500/5 text-violet-700 dark:text-violet-400'
            : 'border-border text-muted-foreground',
      )}
    >
      <Icon className="size-2.5" />
      {name}
    </span>
  )
}

function payloadGlance(event: LedgerEvent): string | null {
  const p = event.payload as Record<string, unknown>
  switch (event.event_type) {
    case 'fact_recorded': return `${p.kind} · ${p.rule_id} · ${p.statement}`
    case 'assessment_recorded': return `${p.verdict} · ${p.rule_id} · ${p.narrative}`
    case 'run_evaluated': return `${p.run_id} · ${p.verdict}`
    case 'authorisation_computed': return String(p.disposition)
    case 'authorisation_decided': return `${p.disposition} · ${p.reviewer} · ${p.rationale}`
    case 'control_posture_recorded': return `${p.control_id ?? p.rule_id ?? ''} · ${p.posture ?? ''}`
    case 'specialist_failed': return String(p.message)
    case 'portfolio_finding_recorded': return String(p.summary)
    case 'run_started':
      return `${p.kind} run ${p.run_id}`
    case 'dispatch_recorded':
      return `${p.target} · ${p.skill}${p.instruction ? ` — “${String(p.instruction).slice(0, 90)}”` : ''}`
    case 'finding_recorded':
      return `${p.agent}: ${p.type} (${p.rule_id ?? 'no rule'})`
    case 'observation_recorded':
      return `${p.agent}: ${String(p.note).slice(0, 100)}`
    case 'critic_checked':
      return `${p.target}: ${p.passed ? 'quoted values verified' : `unquoted values ${(p.unquoted_values as unknown[] ?? []).join(', ')}`}`
    case 'correlation_recorded':
      return `${p.relationship}: ${(p.finding_ids as string[]).join(' + ')}`
    case 'score_computed':
      return `${p.total} · ${String(p.tier).toUpperCase()}`
    case 'question_asked':
      return `“${String(p.question).slice(0, 110)}”`
    case 'investigation_completed':
      return String(p.answer).slice(0, 120)
    case 'grounding_checked':
      return p.passed ? `passed (attempt ${p.attempt})` : `${(p.problems as string[]).length} problem(s)`
    case 'decision_recorded':
      return `${p.action} by ${p.reviewer}`
    case 'escalation_round_started':
      return `round ${p.round} → ${(p.targets as string[]).join(', ')}`
    case 'case_closed':
      return String(p.reason ?? '')
    default:
      return null
  }
}

export function CaseTimeline({ caseId, refreshKey }: { caseId: string; refreshKey: number }) {
  const [runFilter, setRunFilter] = useState('')
  const [limit, setLimit] = useState(100)
  const [events, setEvents] = useState<LedgerEvent[] | null>(null)
  const [chain, setChain] = useState<{ intact: boolean; event_count: number } | null>(null)

  useEffect(() => {
    getLedgerEvents(caseId, true).then(setEvents).catch(() => setEvents([]))
  }, [caseId, refreshKey])

  const checkChain = () => verifyLedger().then(setChain).catch(() => setChain(null))

  if (events === null) {
    return (
      <div className="flex flex-col gap-2 p-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-9" />
        ))}
      </div>
    )
  }

  if (events.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center text-sm text-muted-foreground">
        <FileClock className="size-6 text-muted-foreground/40" />
        <p>No events on the record yet.</p>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2 border-b px-4 py-2.5">
        <span className="text-xs text-muted-foreground">
          {events.length} events · hash-chained, append-only
        </span>
        <div className="flex items-center gap-2">
          {chain && (
            <Badge
              variant="outline"
              className={cn(
                'gap-1 text-[10px] uppercase',
                chain.intact
                  ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400'
                  : 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400',
              )}
            >
              <Fingerprint className="size-3" />
              {chain.intact ? `chain intact · ${chain.event_count} events` : 'CHAIN BROKEN'}
            </Badge>
          )}
          <Button size="sm" variant="outline" onClick={checkChain}>
            <Fingerprint data-icon="inline-start" />
            Verify chain
          </Button>
        </div>
      </div>
      <Milestones events={events} />
      <div className="border-b px-4 py-2"><Input aria-label="Filter timeline by execution run" placeholder="Filter by execution run ID" value={runFilter} onChange={e => { setRunFilter(e.target.value); setLimit(100) }} /></div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col px-4 py-2">
          {events.filter(e => !runFilter || (e.run_ref ?? String(e.payload.run_ref ?? '')).includes(runFilter) || (e.payload.run_refs as string[] | undefined)?.some(r => r.includes(runFilter))).slice(0, limit).map((event) => {
            const meta = EVENT_META[event.event_type] ?? { icon: ScrollText, label: event.event_type }
            const Icon = meta.icon
            const glance = payloadGlance(event)
            return (
              <div key={event.seq} className="flex items-start gap-2.5 border-b border-border/50 py-2 text-xs last:border-0">
                <span className="w-8 shrink-0 pt-0.5 text-right font-mono text-[10px] text-muted-foreground/60">
                  {event.seq}
                </span>
                <Icon className={cn('mt-0.5 size-3.5 shrink-0 text-muted-foreground', meta.tone)} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                    <span className={cn('font-medium', meta.tone)}>{meta.label}</span>
                    {actorChip(event.actor)}
                    {event.run_id && (
                      <span className="font-mono text-[10px] text-muted-foreground/70">{event.run_id}</span>
                    )}
                    <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                      {new Date(event.recorded_at).toLocaleString('en-GB', {
                        day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit',
                      })}
                    </span>
                  </div>
                  {glance && <p className="mt-0.5 truncate text-muted-foreground">{glance}</p>}
                </div>
              </div>
            )
          })}
          {events.length > limit && <Button variant="ghost" onClick={() => setLimit(n => n + 100)}>Show more events</Button>}
        </div>
      </ScrollArea>
    </div>
  )
}
