// The case room (architecture-v2, revised on direction after live use):
// ONE conversation that IS the case. The transcript renders the ledger —
// every routing decision, every briefing with its exact context, every
// finding, the report, the signature — interleaved with the officer's own
// messages, Claude-Code-style: prose turns with expandable work blocks
// under them. While a run streams, a live block shows step/tool activity;
// when it lands, the ledger's authoritative rows replace it.
//
// Nothing here is derived client-side beyond grouping: if it's on screen,
// it's on the record (or streaming toward it).
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  BadgeCheck,
  BrainCircuit,
  CheckCheck,
  ChevronRight,
  CircleSlash,
  Cog,
  CornerDownLeft,
  Eye,
  FileText,
  Fingerprint,
  Gauge,
  GitMerge,
  Inbox,
  Loader2,
  MessageCircleQuestion,
  Play,
  RotateCw,
  SearchCheck,
  Send,
  ShieldAlert,
  ShieldCheck,
  UserRound,
  Waypoints,
  XCircle,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { nodeMeta, AGENT_TONE } from '@/lib/node-meta'
import { TIER_TONE } from '@/components/ResultsPanel'
import { ReviewGate, type GateSubmission } from '@/components/ReviewGate'
import type { FeedEvent } from '@/hooks/usePipelineFeed'
import type {
  DispositionTier,
  GateContext,
  LedgerEvent,
  ObservationAgent,
  RiskScore,
} from '@/lib/types'
import { cn } from '@/lib/utils'

/* eslint-disable @typescript-eslint/no-explicit-any */

// ---------------------------------------------------------------------------
// Transcript model — built straight from the ledger
// ---------------------------------------------------------------------------

interface RunGroup {
  runId: string
  kind: 'triage' | 'investigation' | 'drafting'
  events: LedgerEvent[]
}

type Item =
  | { type: 'system'; icon: typeof Inbox; text: string; at: string }
  | { type: 'officer'; text: string; at?: string }
  | { type: 'orchestrator'; text: string; intent?: string; at?: string }
  | { type: 'run'; group: RunGroup }

function buildTranscript(events: LedgerEvent[]): Item[] {
  const items: Item[] = []
  const groups = new Map<string, RunGroup>()

  for (const event of events) {
    const p = event.payload as any
    if (event.run_id) {
      let group = groups.get(event.run_id)
      if (!group) {
        group = { runId: event.run_id, kind: p.kind ?? 'triage', events: [] }
        groups.set(event.run_id, group)
        items.push({ type: 'run', group })
      }
      if (event.event_type === 'run_started') group.kind = p.kind
      group.events.push(event)
      continue
    }
    switch (event.event_type) {
      case 'case_submitted':
        items.push({ type: 'system', icon: Inbox, text: 'Case submitted — full bundle on the record', at: event.recorded_at })
        break
      case 'case_opened':
        items.push({ type: 'system', icon: UserRound, text: `Case opened by ${event.actor.replace('human:', '')}`, at: event.recorded_at })
        break
      case 'case_closed':
        items.push({ type: 'system', icon: BadgeCheck, text: `Case closed — ${p.reason ?? 'no action'} · by ${event.actor.replace('human:', '')}`, at: event.recorded_at })
        break
      default:
        break
    }
  }
  return items
}

// ---------------------------------------------------------------------------
// Small shared bits
// ---------------------------------------------------------------------------

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function AgentChip({ agent }: { agent: ObservationAgent | string }) {
  const meta = nodeMeta(agent)
  const Icon = meta.icon
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-medium uppercase', AGENT_TONE[meta.color])}>
      <Icon className="size-2.5" />
      {meta.label}
    </span>
  )
}

function Expandable({ summary, children }: { summary: React.ReactNode; children: React.ReactNode }) {
  return (
    <details className="group/x min-w-0">
      <summary className="flex cursor-pointer list-none items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground [&::-webkit-details-marker]:hidden">
        <ChevronRight className="size-3 transition-transform group-open/x:rotate-90" />
        {summary}
      </summary>
      <div className="mt-1.5 min-w-0">{children}</div>
    </details>
  )
}

function Json({ value }: { value: unknown }) {
  return (
    <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md bg-black/[0.03] p-2 font-mono text-[10.5px] leading-snug text-muted-foreground dark:bg-white/[0.04]">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

function ScoreChip({ total, tier, tierLabel }: { total: number; tier: DispositionTier; tierLabel: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <Gauge className="size-3.5 text-muted-foreground" />
      <span className="font-mono text-sm font-bold">{total.toFixed(2)}</span>
      <Badge variant="outline" className={cn('text-[10px] font-semibold uppercase', TIER_TONE[tier])}>
        {tierLabel}
      </Badge>
    </span>
  )
}

// ---------------------------------------------------------------------------
// Ledger event → row inside a run block
// ---------------------------------------------------------------------------

function EventRow({ event }: { event: LedgerEvent }) {
  const p = event.payload as any
  switch (event.event_type) {
    case 'run_started': {
      const overridden = Object.entries(p.prompts ?? {}).filter(([, v]: [string, any]) => v.override)
      if (!overridden.length) return null
      return (
        <div className="flex items-start gap-2 text-xs text-muted-foreground">
          <Fingerprint className="mt-0.5 size-3.5 shrink-0" />
          <Expandable summary={<>ran with edited instructions — {overridden.map(([k]) => k).join(', ')} (recorded in full)</>}>
            {overridden.map(([k, v]: [string, any]) => (
              <div key={k} className="mb-1.5">
                <span className="font-mono text-[10px]">{k}</span>
                <Json value={v.override} />
              </div>
            ))}
          </Expandable>
        </div>
      )
    }
    case 'dispatch_planned':
      return (
        <div className="flex items-start gap-2 text-[13px]">
          <Waypoints className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
          <div className="min-w-0">
            <span className="font-medium">Routing</span>
            <span className="ml-2 inline-flex flex-wrap gap-1 align-middle">
              {(p.selected_skills ?? []).map((s: string) => (
                <span key={s} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">{s}</span>
              ))}
            </span>
            <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{p.plan?.reasoning}</p>
          </div>
        </div>
      )
    case 'dispatch_recorded':
      return (
        <div className="flex items-start gap-2 text-[13px]">
          <Send className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
          <div className="min-w-0 flex-1">
            <span className="font-medium">Briefed</span> <AgentChip agent={p.target} />{' '}
            <span className="font-mono text-[10px] text-muted-foreground">{p.skill}</span>
            {p.instruction && (
              <p className="mt-0.5 text-xs italic leading-relaxed text-muted-foreground">“{p.instruction}”</p>
            )}
            <Expandable summary={<>exact context sent · {String(p.context_digest).slice(0, 18)}…</>}>
              <Json value={p.context_blocks} />
            </Expandable>
          </div>
        </div>
      )
    case 'finding_recorded':
      return (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/[0.05] p-2.5 text-[13px]">
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5">
              <ShieldAlert className="size-3.5 text-amber-600" />
              <AgentChip agent={p.agent} />
              <span className="font-mono text-[10px] text-muted-foreground">{p.type}</span>
            </span>
            <span className="font-mono text-[10px] text-muted-foreground">{p.rule_id}</span>
          </div>
          <p className="mt-1.5 leading-relaxed">{p.summary}</p>
          <span className="mt-1 inline-block font-mono text-[10px] text-muted-foreground/70">{p.finding_id}</span>
        </div>
      )
    case 'observation_recorded':
      return (
        <div className="rounded-lg border border-dashed p-2.5 text-[13px]">
          <span className="flex items-center gap-1.5">
            <Eye className="size-3.5 text-muted-foreground" />
            <AgentChip agent={p.agent} />
            <span className="flex items-center gap-1 text-[10px] text-muted-foreground"><CircleSlash className="size-2.5" /> unverified · never scored</span>
          </span>
          <p className="mt-1.5 leading-relaxed">{p.note}</p>
          <p className="mt-1 text-[11px] italic text-muted-foreground">{p.cited_evidence}</p>
        </div>
      )
    case 'critic_checked':
      return (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <ShieldCheck className={cn('size-3.5', p.passed ? 'text-emerald-600' : 'text-red-600')} />
          <span>
            Critic · <AgentChip agent={p.target} />{' '}
            {p.passed
              ? `quoted values verified (${p.checked} checked)`
              : `unquoted values flagged: ${(p.unquoted_values ?? []).join(', ')}`}
          </span>
        </div>
      )
    case 'correlation_recorded':
      return (
        <div className="rounded-lg border border-indigo-500/25 bg-indigo-500/[0.04] p-2.5 text-[13px]">
          <span className="flex flex-wrap items-center gap-1.5">
            <GitMerge className="size-3.5 text-indigo-600" />
            <Badge variant="outline" className="border-indigo-500/30 text-[10px] uppercase text-indigo-700 dark:text-indigo-400">
              {String(p.relationship).replace('_', ' ')}
            </Badge>
            {(p.finding_ids ?? []).map((fid: string) => (
              <span key={fid} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">{fid}</span>
            ))}
          </span>
          <p className="mt-1.5 leading-relaxed">{p.explanation}</p>
        </div>
      )
    case 'escalation_round_started':
      return (
        <div className="flex items-center gap-2 py-0.5 text-xs font-medium text-muted-foreground">
          <RotateCw className="size-3.5" />
          Escalation round {p.round} → {(p.targets ?? []).join(', ')}
        </div>
      )
    case 'score_computed':
      return (
        <div className="flex items-center gap-2 text-[13px]">
          <ScoreChip total={p.total} tier={p.tier} tierLabel={p.tier_label} />
          <span className="text-xs text-muted-foreground">{p.tier_guidance}</span>
        </div>
      )
    case 'investigation_completed':
      return (
        <div className="rounded-lg border border-teal-500/25 bg-teal-500/[0.04] p-2.5 text-[13px]">
          <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <SearchCheck className="size-3.5 text-teal-600" />
            Investigator answered
          </span>
          <p className="mt-1.5 leading-relaxed">{p.answer}</p>
          {(p.tool_calls ?? []).length > 0 && (
            <div className="mt-2 flex flex-col gap-0.5">
              {(p.tool_calls ?? []).map((t: any, i: number) => (
                <div key={i} className="truncate font-mono text-[10.5px] text-muted-foreground">
                  <span className="text-teal-700 dark:text-teal-400">{t.tool}</span>
                  ({JSON.stringify(t.arguments)}) → {String(t.result_digest).slice(0, 18)}…
                </div>
              ))}
            </div>
          )}
        </div>
      )
    case 'report_drafted':
      return (
        <div className="rounded-lg border bg-card p-3.5 text-[13px] shadow-sm">
          <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <FileText className="size-3.5" />
            Supervisory report — draft
          </span>
          <p className="mt-2 font-heading text-sm font-medium leading-relaxed">{p.overall_assessment}</p>
          {(p.sections ?? []).map((s: any, i: number) => (
            <div key={i} className="mt-3 border-t pt-2.5">
              <h4 className="text-[13px] font-semibold">{s.title}</h4>
              <p className="mt-1 text-[13px] leading-relaxed text-foreground/90">{s.body}</p>
              <div className="mt-1.5 flex flex-wrap items-center gap-1">
                <span className="text-[9px] font-medium uppercase tracking-wide text-muted-foreground">cites</span>
                {(s.cited_finding_ids ?? []).map((fid: string) => (
                  <span key={fid} className="rounded border px-1 py-0.5 font-mono text-[9px] text-muted-foreground">{fid}</span>
                ))}
              </div>
            </div>
          ))}
          {p.open_observations_note && (
            <div className="mt-3 rounded-md border border-dashed bg-muted/30 p-2.5">
              <span className="flex items-center gap-1 text-[10px] font-medium uppercase text-muted-foreground">
                <Eye className="size-3" /> unverified observations — not findings
              </span>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{p.open_observations_note}</p>
            </div>
          )}
        </div>
      )
    case 'grounding_checked':
      return (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <ShieldCheck className={cn('size-3.5', p.passed ? 'text-emerald-600' : 'text-amber-600')} />
          {p.passed
            ? `Grounding passed — every claim cites a real finding (attempt ${p.attempt})`
            : `Grounding failed (attempt ${p.attempt}) — regenerating with the validator's complaints`}
        </div>
      )
    case 'report_blocked':
      return (
        <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-2.5 text-[13px]">
          <span className="flex items-center gap-1.5 font-medium text-red-700 dark:text-red-400">
            <ShieldAlert className="size-3.5" /> Draft blocked — failed grounding after the retry cap
          </span>
          <ul className="mt-1.5 ml-4 list-disc font-mono text-[11px] text-muted-foreground">
            {(p.problems ?? []).map((x: string, i: number) => <li key={i}>{x}</li>)}
          </ul>
        </div>
      )
    case 'decision_recorded': {
      const icon = p.action === 'approve' ? CheckCheck : p.action === 'reject' ? XCircle : RotateCw
      const Icon = icon
      return (
        <div
          className={cn(
            'flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border px-3 py-2 text-[13px]',
            p.action === 'approve' && 'border-emerald-500/30 bg-emerald-500/5',
          )}
        >
          <Icon className={cn('size-4', p.action === 'approve' ? 'text-emerald-600' : 'text-muted-foreground')} />
          <span className="font-semibold">
            {p.action === 'approve' ? 'Report issued' : p.action === 'reject' ? 'Report rejected' : 'Sent back for re-analysis'}
          </span>
          <span className="text-muted-foreground">signed by {p.reviewer} · {fmtTime(p.decided_at)}</span>
          {p.directive && (
            <span className="w-full text-xs text-muted-foreground">
              → {(p.directive.target_agents ?? []).join(', ')}: “{p.directive.instructions}”
            </span>
          )}
          {p.comment && <span className="w-full text-xs italic text-muted-foreground">“{p.comment}”</span>}
        </div>
      )
    }
    default:
      return null
  }
}

// ---------------------------------------------------------------------------
// Run block — one bounded run as a Claude-Code-style work group
// ---------------------------------------------------------------------------

const RUN_META: Record<RunGroup['kind'], { label: string; icon: typeof Waypoints }> = {
  triage: { label: 'Full review pass', icon: Waypoints },
  investigation: { label: 'Investigation', icon: SearchCheck },
  drafting: { label: 'Report drafting', icon: FileText },
}

function RunBlock({ group }: { group: RunGroup }) {
  const meta = RUN_META[group.kind]
  const Icon = meta.icon
  const started = group.events.find((e) => e.event_type === 'run_started')
  const completed = group.events.find((e) => e.event_type === 'run_completed')
  // question/reply render as bubbles around the block (Transcript handles
  // them); everything else is a work row inside it.
  const rows = group.events.filter(
    (e) => !['question_asked', 'orchestrator_replied', 'run_completed'].includes(e.event_type),
  )
  const rendered = rows.map((e) => ({ e, node: EventRow({ event: e }) })).filter((r) => r.node !== null)
  if (rendered.length === 0) return null

  return (
    <div className="flex gap-2.5">
      <div className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted">
        <Icon className="size-3.5 text-muted-foreground" />
      </div>
      <div className="min-w-0 flex-1 rounded-xl border bg-card/60 px-3.5 py-3">
        <div className="flex items-center justify-between gap-2 text-xs">
          <span className="font-semibold">{meta.label}</span>
          <span className="font-mono text-[10px] text-muted-foreground">
            {group.runId}
            {started && <> · {fmtTime(started.recorded_at)}</>}
            {completed && <> → {fmtTime(completed.recorded_at)}</>}
          </span>
        </div>
        <div className="mt-2.5 flex flex-col gap-2.5">
          {rendered.map(({ e, node }) => (
            <div key={e.seq}>{node}</div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Live block — the run currently streaming, from AG-UI events
// ---------------------------------------------------------------------------

function LiveBlock({ label, events }: { label: string; events: FeedEvent[] }) {
  return (
    <div className="flex gap-2.5">
      <div className="relative flex size-6 shrink-0 items-center justify-center rounded-full bg-amber-500/15">
        <Loader2 className="size-3.5 animate-spin text-amber-600" />
      </div>
      <div className="min-w-0 flex-1 rounded-xl border border-amber-500/30 bg-amber-500/[0.03] px-3.5 py-3">
        <div className="flex items-center gap-2 text-xs font-semibold">
          {label}
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-500 opacity-75" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-amber-500" />
          </span>
        </div>
        <div className="mt-2 flex flex-col gap-1">
          {events.map((event) =>
            event.kind === 'node' ? (
              <div key={event.key} className="flex items-center gap-1.5 text-xs text-muted-foreground">
                {event.status === 'complete' ? (
                  <CheckCheck className="size-3 text-emerald-600" />
                ) : (
                  <Cog className="size-3 animate-spin text-amber-600" />
                )}
                <span className="font-medium text-foreground">{nodeMeta(event.nodeName).label}</span>
                {event.status === 'complete' ? 'finished' : 'working…'}
              </div>
            ) : (
              <div key={event.key} className="rounded-md border border-amber-500/20 bg-card/60 px-2 py-1.5 text-[11px]">
                <span className="flex items-center gap-1.5 font-mono font-medium">
                  <BrainCircuit className={cn('size-3', event.status !== 'complete' && 'animate-pulse text-amber-600')} />
                  {event.name}
                  <span className="ml-auto text-[9px] uppercase text-muted-foreground">
                    {event.status === 'complete' ? 'done' : event.status === 'executing' ? 'writing' : 'thinking'}
                  </span>
                </span>
                {event.args != null && JSON.stringify(event.args) !== '{}' && (
                  <pre className="mt-1 max-h-28 overflow-auto whitespace-pre-wrap break-words font-mono text-[10px] leading-snug text-muted-foreground">
                    {typeof event.args === 'string' ? event.args : JSON.stringify(event.args, null, 1)}
                  </pre>
                )}
              </div>
            ),
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// The conversation
// ---------------------------------------------------------------------------

export interface ConversationProps {
  events: LedgerEvent[] | null
  liveEvents: FeedEvent[]
  liveLabel: string | null // non-null while a run streams
  pendingQuestion: string | null
  pendingReply: string | null // orchestrator reply streamed but not yet in the ledger
  gate: { context: GateContext } | null
  gateRisk: RiskScore | null
  findingsCount: number
  officer: string
  onOfficerChange: (name: string) => void
  onDecide: (d: GateSubmission) => void
  onSend: (text: string) => void
  onRun: () => void
  onDraft: () => void
  onCloseCase: () => void
  busy: boolean
  hasTriage: boolean
  closable: boolean
}

export function Conversation({
  events,
  liveEvents,
  liveLabel,
  pendingQuestion,
  pendingReply,
  gate,
  gateRisk,
  findingsCount,
  officer,
  onOfficerChange,
  onDecide,
  onSend,
  onRun,
  onDraft,
  onCloseCase,
  busy,
  hasTriage,
  closable,
}: ConversationProps) {
  const [draft, setDraft] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  const items = useMemo(() => buildTranscript(events ?? []), [events])

  // Follow the conversation as it grows — scoped to this scroller only.
  useEffect(() => {
    const viewport = bottomRef.current?.closest('[data-slot="scroll-area-viewport"]')
    if (viewport) viewport.scrollTop = viewport.scrollHeight
  }, [items, liveEvents, pendingQuestion, pendingReply, gate])

  const send = () => {
    const text = draft.trim()
    if (!text || busy) return
    setDraft('')
    onSend(text)
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ScrollArea className="min-h-0 flex-1">
        <div className="mx-auto flex max-w-3xl flex-col gap-3.5 px-4 py-4">
          {items.length === 0 && (
            <p className="py-10 text-center text-sm text-muted-foreground">Loading the record…</p>
          )}
          {items.map((item, i) => {
            if (item.type === 'system') {
              const Icon = item.icon
              return (
                <div key={i} className="flex items-center justify-center gap-1.5 py-0.5 text-[11px] text-muted-foreground">
                  <Icon className="size-3" />
                  {item.text}
                  <span className="font-mono text-[10px] text-muted-foreground/60">{fmtTime(item.at)}</span>
                </div>
              )
            }
            if (item.type === 'run') {
              const question = item.group.events.find((e) => e.event_type === 'question_asked')
              const reply = item.group.events.find((e) => e.event_type === 'orchestrator_replied')
              return (
                <div key={item.group.runId} className="flex flex-col gap-3.5">
                  {question && (
                    <OfficerBubble
                      text={(question.payload as any).question}
                      by={question.actor.replace('human:', '')}
                      at={question.recorded_at}
                    />
                  )}
                  {reply && <OrchestratorBubble text={(reply.payload as any).message} intent={(reply.payload as any).intent} />}
                  <RunBlock group={item.group} />
                </div>
              )
            }
            return null
          })}

          {pendingQuestion && <OfficerBubble text={pendingQuestion} by={officer} />}
          {pendingReply && <OrchestratorBubble text={pendingReply} />}
          {liveLabel && <LiveBlock label={liveLabel} events={liveEvents} />}

          {gate && (
            <div className="pl-8">
              <ReviewGate
                key={gate.context.error ?? 'gate'}
                context={gate.context}
                onDecide={onDecide}
                risk={gateRisk}
                findingsCount={findingsCount}
                defaultReviewer={officer !== 'Case officer' ? officer : undefined}
              />
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      {/* Composer — the supervisor drives everything from here. */}
      <div className="border-t bg-card/80 px-4 pb-3 pt-2.5">
        <div className="mx-auto flex max-w-3xl flex-col gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <Button size="sm" variant={hasTriage ? 'outline' : 'default'} onClick={onRun} disabled={busy}>
              <Play data-icon="inline-start" />
              {hasTriage ? 'Run again' : 'Run review'}
            </Button>
            <Button size="sm" variant="outline" onClick={onDraft} disabled={busy || !hasTriage}>
              <FileText data-icon="inline-start" />
              Draft report
            </Button>
            {closable && (
              <Button size="sm" variant="outline" onClick={onCloseCase} disabled={busy}>
                <BadgeCheck data-icon="inline-start" />
                Close — no action
              </Button>
            )}
            <div className="ml-auto flex items-center gap-1.5">
              <UserRound className="size-3.5 text-muted-foreground" />
              <Input
                value={officer}
                onChange={(e) => onOfficerChange(e.target.value)}
                className="h-7 w-36 text-xs"
                aria-label="Acting as — recorded on everything you do"
              />
            </div>
          </div>
          <div className="flex items-end gap-2">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  send()
                }
              }}
              placeholder="Ask the orchestrator — “run the review”, “who is this counterparty?”, “have Log re-check the same-day cluster”, “draft the report”…"
              rows={2}
              className="min-h-10 flex-1 resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
            />
            <Button onClick={send} disabled={busy || !draft.trim()}>
              {busy ? <Loader2 className="animate-spin" /> : <CornerDownLeft />}
              Send
            </Button>
          </div>
          <p className="flex items-center gap-1 text-[10px] text-muted-foreground">
            <MessageCircleQuestion className="size-3" />
            The orchestrator routes — it never judges. Every message, briefing, and decision lands on the hash-chained record as
            <span className="font-mono">human:{officer}</span> / <span className="font-mono">agent:*</span>.
          </p>
        </div>
      </div>
    </div>
  )
}

function OfficerBubble({ text, by, at }: { text: string; by: string; at?: string }) {
  return (
    <div className="flex flex-col items-end gap-0.5">
      <div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-3.5 py-2 text-sm text-primary-foreground">
        {text}
      </div>
      <span className="font-mono text-[10px] text-muted-foreground">
        {by}
        {at && <> · {fmtTime(at)}</>}
      </span>
    </div>
  )
}

function OrchestratorBubble({ text, intent }: { text: string; intent?: string }) {
  return (
    <div className="flex gap-2.5">
      <div className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/10">
        <Waypoints className="size-3.5 text-primary" />
      </div>
      <div className="flex max-w-[85%] flex-col gap-0.5">
        <div className="rounded-2xl rounded-bl-md border bg-card px-3.5 py-2 text-sm leading-relaxed">{text}</div>
        {intent && intent !== 'reply' && (
          <span className="font-mono text-[10px] text-muted-foreground">routed: {intent}</span>
        )}
      </div>
    </div>
  )
}
