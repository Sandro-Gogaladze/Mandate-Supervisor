// The case room's transcript — ONE conversation that is the case, read the
// way a Claude conversation reads: the supervisor's requests on the right,
// the pipeline's work on the left as an assistant turn made of steps. Each
// specialist is a step with its own thinking (the working it wrote before
// recording, shown as "Thought for 12s" once it has finished), its
// verdicts in plain language, and — one level down — what it was briefed
// with. No function names, no raw payloads: the machine names stay on the
// ledger, which is what the timeline tab is for.
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  ArrowUp,
  BadgeCheck,
  Check,
  ChevronRight,
  Eye,
  FileText,
  GitMerge,
  Inbox,
  Loader2,
  Play,
  RotateCw,
  ScrollText,
  SearchCheck,
  ShieldCheck,
  TriangleAlert,
  UserRound,
  UserRoundCheck,
  Waypoints,
  XCircle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { nodeMeta, AGENT_ICON } from '@/lib/node-meta'
import { TIER_TONE } from '@/components/ResultsPanel'
import { EvidenceFields, FactCard, RunCitation, turnAnchor } from '@/components/AgentTurn'
import { FailureList, failureSummary } from '@/components/FailureList'
import type { FeedEvent, ReasoningEvent, ToolCallEvent } from '@/hooks/usePipelineFeed'
import type { FailureOccurrence, GateContext, LedgerEvent, RiskScore } from '@/lib/types'
import { DISPOSITION_LABEL, type Assessment, type Fact, type SpecialistProgress } from '@/lib/supervision-types'
import { ORCHESTRATOR_STEPS, RUN_TITLE, VERDICT_LABEL, VERDICT_TONE, durationLabel, fmtTime, skillAgent, specialistSummary, toolLabel } from '@/lib/humanize'
import { cn } from '@/lib/utils'

/* eslint-disable @typescript-eslint/no-explicit-any */
type P = Record<string, any>
const pay = (e: LedgerEvent): P => e.payload as P
const unique = <T,>(xs: T[]) => [...new Set(xs)]

/** The scalar arguments of a lookup, for a one-line "Looked up a counterparty · MER-QVC-8801". */
function argsSummary(args: unknown): string {
  if (!args || typeof args !== 'object') return ''
  return Object.values(args as P).filter((v) => typeof v === 'string' || typeof v === 'number').map(String).join(' · ')
}

/** The adapter opens a reasoning message for every thinking block the model
 * emits, and this model's thinking blocks carry no text — only a signature.
 * A block with nothing in it is not a thought. */
const spoken = (r: ReasoningEvent) => r.text.trim().length > 0

const PEER_ORDER = ['mandate', 'kya', 'provenance', 'injection', 'counterparty', 'consent', 'log', 'drift', 'control_assurance', 'systemic', 'investigator']
const SUPPORT_NODES = new Set(['findings', 'critic', 'synthesizer', 'draft_report', 'grounding_check', 'human_gate', 'specialists_done', 'supervisor'])

function orderAgents(agents: string[], selected: string[]): string[] {
  const rank = (a: string) => {
    const s = selected.findIndex((skill) => skillAgent(skill) === a)
    return s >= 0 ? s : 100 + Math.max(0, PEER_ORDER.indexOf(a))
  }
  return [...agents].sort((a, b) => rank(a) - rank(b))
}

// ---------------------------------------------------------------------------
// Transcript model — straight from the ledger, grouped by run
// ---------------------------------------------------------------------------

export interface RunGroup {
  runId: string
  kind: 'triage' | 'investigation' | 'drafting'
  events: LedgerEvent[]
}

type Item =
  | { type: 'system'; icon: typeof Inbox; text: string; at: string }
  | { type: 'run'; group: RunGroup }

/** A run's kind from its id prefix — for a live run whose start event has
 * not reached the transcript yet (only its specialists' events have). */
function kindFromRunId(runId: string): RunGroup['kind'] {
  if (runId.startsWith('inv')) return 'investigation'
  if (runId.startsWith('dra')) return 'drafting'
  return 'triage'
}

function buildTranscript(events: LedgerEvent[]): Item[] {
  const items: Item[] = []
  const groups = new Map<string, RunGroup>()
  for (const event of events) {
    const p = pay(event)
    if (event.run_id) {
      let group = groups.get(event.run_id)
      if (!group) {
        group = { runId: event.run_id, kind: p.kind ?? kindFromRunId(event.run_id), events: [] }
        groups.set(event.run_id, group)
        items.push({ type: 'run', group })
      }
      if (event.event_type === 'run_started') group.kind = p.kind
      group.events.push(event)
      continue
    }
    switch (event.event_type) {
      case 'dossier_submitted':
      case 'case_submitted':
        items.push({ type: 'system', icon: Inbox, text: 'Dossier submitted · signed execution runs on the record', at: event.recorded_at })
        break
      case 'authorisation_decided':
        items.push({ type: 'system', icon: BadgeCheck, text: `${DISPOSITION_LABEL[p.disposition as keyof typeof DISPOSITION_LABEL] ?? p.disposition} · signed by ${p.reviewer}`, at: event.recorded_at })
        break
      case 'case_watched':
        items.push({ type: 'system', icon: Eye, text: 'Standing watch recorded', at: event.recorded_at })
        break
      case 'case_opened':
        items.push({ type: 'system', icon: UserRound, text: `Case opened by ${event.actor.replace('human:', '')}`, at: event.recorded_at })
        break
      case 'case_closed':
        items.push({ type: 'system', icon: BadgeCheck, text: `Case closed · ${p.reason ?? 'no action'} · by ${event.actor.replace('human:', '')}`, at: event.recorded_at })
        break
      default:
        break
    }
  }
  return items
}

// ---------------------------------------------------------------------------
// Building blocks, in Claude's grammar: bubbles, thinking, steps, sections
// ---------------------------------------------------------------------------

function UserBubble({ text, by, at }: { text: string; by: string; at?: string }) {
  return (
    <div className="flex flex-col items-end gap-1">
      <span className="pr-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">You asked</span>
      <div className="max-w-[80%] rounded-2xl border border-primary/15 bg-muted px-4 py-2.5 text-[15px] leading-6 text-foreground">{text}</div>
      <span className="pr-1 text-[11px] text-muted-foreground">
        {by}
        {at && <> · {fmtTime(at)}</>}
      </span>
    </div>
  )
}

/** The model's own reasoning. Open while it thinks; afterwards a one-line
 * "Thought for 12s" the reader can reopen — the reader's toggle always wins. */
function Thinking({ text, working, startedAt, endedAt, label = 'Thinking' }: {
  text: string; working: boolean; startedAt?: number; endedAt?: number; label?: string
}) {
  const [userOpen, setUserOpen] = useState<boolean | null>(null)
  const open = userOpen ?? working
  const took = startedAt && endedAt ? durationLabel(endedAt - startedAt) : null
  return (
    <div>
      <button type="button" onClick={() => setUserOpen(!open)} className="flex items-center gap-1.5 text-[13px] text-muted-foreground transition-colors hover:text-foreground">
        <ChevronRight className={cn('size-3.5 transition-transform', open && 'rotate-90')} />
        {working ? <span className="animate-pulse">{label}…</span> : took ? `Thought for ${took}` : label}
      </button>
      {open && (text || !working) && (
        <div className="mt-2 ml-1.5 whitespace-pre-wrap border-l-2 border-border pl-3.5 text-[13px] leading-6 text-muted-foreground">
          {text || 'No reasoning was recorded for this step.'}
        </div>
      )}
    </div>
  )
}

/** The working an agent writes before it records anything — the leading
 * `reasoning` field of its tool call. Shown like model thinking: "Thinking…"
 * while the call is open, "Thought for 12s" with the text once it has ended. */
function ToolReasoning({ tool }: { tool: ToolCallEvent }) {
  const text = typeof tool.args.reasoning === 'string' ? tool.args.reasoning : ''
  return <Thinking text={text} working={tool.status !== 'complete'} startedAt={tool.at} endedAt={tool.endedAt} />
}

/** One correlation the synthesizer drew, collapsed to a single line.
 *
 * Sixteen of these opened at once was a wall of prose nobody read: the step
 * they live in is already a disclosure, and opening it should hand back a
 * scannable list, not a document. The relationship and the finding count carry
 * the shape of the link; the paragraph behind it is there when it is wanted. */
function CorrelationLink({ relationship, explanation, findingIds }: {
  relationship: string; explanation: string; findingIds: string[]
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-lg border">
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-2 px-3 py-2 text-left">
        <ChevronRight className={cn('size-3.5 shrink-0 text-muted-foreground transition-transform', open && 'rotate-90')} />
        <span className="shrink-0 rounded-full bg-indigo-500/10 px-2 py-0.5 text-[11px] font-medium uppercase text-indigo-700 dark:text-indigo-400">{relationship}</span>
        {!open && <span className="min-w-0 flex-1 truncate text-[13px] text-muted-foreground">{explanation}</span>}
        <span className="ml-auto shrink-0 font-mono text-[10px] text-muted-foreground">{findingIds.length} finding{findingIds.length === 1 ? '' : 's'}</span>
      </button>
      {open && (
        <div className="border-t px-3 py-2.5">
          <p className="text-[13px] leading-6">{explanation}</p>
          <p className="mt-1 font-mono text-[10px] text-muted-foreground">{findingIds.join(' · ')}</p>
        </div>
      )}
    </div>
  )
}

type StepStatus = 'queued' | 'working' | 'done' | 'failed' | 'flagged'

// One hue per state, and no hue used twice. `working` and `flagged` were both
// amber, so "still running" and "finished, and found something" looked the
// same — the single most confusing thing on the page. Activity is blue,
// findings are red, a lost judgement is amber (degraded, not adverse), done is
// green, queued is grey.
function StatusPill({ status }: { status: StepStatus }) {
  if (status === 'working') return <span className="inline-flex items-center gap-1 rounded-full bg-blue-500/10 px-2 py-0.5 text-[11px] font-medium text-blue-700 dark:text-blue-400"><Loader2 className="size-3 animate-spin" />Working</span>
  if (status === 'failed') return <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:text-amber-400"><XCircle className="size-3" />Judgement unavailable</span>
  if (status === 'flagged') return <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2 py-0.5 text-[11px] font-medium text-red-700 dark:text-red-400"><TriangleAlert className="size-3" />Findings</span>
  if (status === 'done') return <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:text-emerald-400"><Check className="size-3" />Done</span>
  return <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">Queued</span>
}

/** One piece of work inside an assistant turn. Open while working, collapsed
 * to its summary line once done — unless the reader opened it. */
function Step({ id, icon: Icon, tone, title, summary, status, focused, took, nested, children }: {
  id?: string; icon: React.ComponentType<{ className?: string; strokeWidth?: number }>; tone: { bg: string; text: string }
  title: string; summary: ReactNode; status: StepStatus; took?: string | null; focused?: boolean
  /** A specialist working inside the orchestrator's pass, rather than a stage
   * of the pass itself. Indented behind a rule and set a size down, so the
   * spine of the run — orchestrate, control, critic, synthesise — stays
   * readable at a glance instead of competing with eight peers. */
  nested?: boolean; children?: ReactNode
}) {
  const [userOpen, setUserOpen] = useState<boolean | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (focused) {
      setUserOpen(true)
      ref.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [focused])
  // Closed until asked for — nothing opens itself.
  const open = userOpen ?? false
  return (
    <div
      id={id}
      ref={ref}
      className={cn(
        'rounded-xl border transition-shadow',
        nested ? 'ml-5 border-l-2 bg-card/40' : 'bg-card/70',
        status === 'working' && 'border-blue-500/40 shadow-[0_0_0_3px_rgba(59,130,246,0.10)]',
        focused && 'ring-2 ring-primary/30',
      )}
    >
      <button type="button" onClick={() => setUserOpen(!open)} className={cn('flex w-full items-center text-left', nested ? 'gap-2.5 px-3 py-2' : 'gap-3 px-3.5 py-2.5')}>
        <span className={cn('flex shrink-0 items-center justify-center rounded-lg', nested ? 'size-6' : 'size-8', tone.bg, tone.text)}>
          <Icon className={nested ? 'size-3.5' : 'size-4'} strokeWidth={2.25} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className={cn('font-semibold', nested ? 'text-[13px]' : 'text-[14px]')}>{title}</span>
            <StatusPill status={status} />
            {took && <span className="text-[11px] text-muted-foreground">{took}</span>}
          </span>
          <span className={cn('mt-0.5 block leading-5 text-muted-foreground', nested ? 'text-[12px]' : 'text-[13px]')}>{summary}</span>
        </span>
        <ChevronRight className={cn('shrink-0 text-muted-foreground transition-transform', nested ? 'size-3.5' : 'size-4', open && 'rotate-90')} />
      </button>
      {open && children && <div className={cn('space-y-3 border-t', nested ? 'px-3 py-2.5' : 'px-3.5 py-3')}>{children}</div>}
    </div>
  )
}

/** A collapsed drawer inside a step. Its content renders only when open, so a
 * turn with six hundred rule results costs nothing until asked for. */
function Section({ title, defaultOpen = false, children }: { title: ReactNode; defaultOpen?: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div>
      <button type="button" onClick={() => setOpen(!open)} className="flex items-center gap-1.5 text-[12.5px] font-medium text-muted-foreground hover:text-foreground">
        <ChevronRight className={cn('size-3.5 transition-transform', open && 'rotate-90')} />
        {title}
      </button>
      {open && <div className="mt-2">{children}</div>}
    </div>
  )
}

function Prose({ children }: { children: ReactNode }) {
  return <div className="space-y-2.5 text-[15px] leading-7 text-foreground">{children}</div>
}

function VerdictCard({ a, facts, onOpenRun, loaded, hideRuns }: {
  a: Assessment; facts: Map<string, Fact>; onOpenRun: (run: string) => void; loaded: boolean
  /** The failure row this card sits inside already names the runs. */
  hideRuns?: boolean
}) {
  return (
    <div className={cn('rounded-lg border px-3 py-2.5', VERDICT_TONE[a.verdict])}>
      <div className="flex flex-wrap items-center gap-2 text-[12px]">
        <span className="font-semibold">{VERDICT_LABEL[a.verdict]}</span>
        {a.rule_id && <span className="font-mono text-[11px] opacity-80">{a.rule_id}</span>}
        <span className="ml-auto text-[11px] opacity-70">{a.confidence} · severity {a.severity_assessed.toFixed(2)}</span>
      </div>
      <p className="mt-1.5 text-[13.5px] leading-6 text-foreground">{a.narrative}</p>
      {a.run_refs.length > 0 && !hideRuns && (
        <div className="mt-1.5 flex flex-wrap gap-x-2 gap-y-1">{a.run_refs.slice(0, 12).map((run) => <RunCitation key={run} run={run} onOpenRun={onOpenRun} />)}{a.run_refs.length > 12 && <span className="text-[10px] text-muted-foreground">and {a.run_refs.length - 12} more</span>}</div>
      )}
      {a.fact_ids.length > 0 && (
        <div className="mt-2">
          <Section title={`Evidence · ${a.fact_ids.length} ${a.fact_ids.length === 1 ? 'fact' : 'facts'}`}>
            {loaded ? (
              <div className="space-y-1">
                {a.fact_ids.slice(0, 20).map((id) => facts.has(id) ? <FactCard key={id} fact={facts.get(id)!} onOpenRun={onOpenRun} /> : <p key={id} className="text-xs text-muted-foreground">{id}</p>)}
                {a.fact_ids.length > 20 && <p className="text-xs text-muted-foreground">and {a.fact_ids.length - 20} more on the record.</p>}
              </div>
            ) : <p className="text-xs text-muted-foreground">The facts are on the ledger and load when the run finishes.</p>}
          </Section>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// A specialist's turn
// ---------------------------------------------------------------------------

function SpecialistStep({ agent, group, running, live, progress, facts, factsLoaded, focused, onOpenRun }: {
  agent: string; group: RunGroup; running: boolean; live: FeedEvent[]
  progress?: SpecialistProgress; facts: Map<string, Fact>; factsLoaded: boolean; focused: boolean; onOpenRun: (run: string) => void
}) {
  const meta = nodeMeta(agent)
  const tone = AGENT_ICON[meta.color]
  const own = group.events.filter((e) => e.actor === `agent:${agent}` || (e.event_type === 'dispatch_recorded' && pay(e).target === agent))
  const dispatch = own.find((e) => e.event_type === 'dispatch_recorded')
  const assessments = own.filter((e) => e.event_type === 'assessment_recorded').map((e) => e.payload as unknown as Assessment)
  // What this specialist established, in the catalogue's own vocabulary. The
  // stream carries every non-fact event for the agent, so these are present
  // live as well as on read-back.
  const occurrences = own.filter((e) => e.event_type === 'failure_occurrence_recorded')
    .map((e) => e.payload as unknown as FailureOccurrence)
  // An occurrence names the assessment it was projected from, so the two join
  // exactly. Whatever no occurrence claims is shown separately.
  const byAssessment = new Map(assessments.map((a) => [a.assessment_id, a]))
  const claimed = new Set(occurrences.map((o) => o.assessment_id))
  const otherVerdicts = assessments
    .filter((a) => !claimed.has(a.assessment_id))
    .sort((x, y) => ['breach', 'concern', 'inconclusive', 'explained', 'clear'].indexOf(x.verdict)
      - ['breach', 'concern', 'inconclusive', 'explained', 'clear'].indexOf(y.verdict))
  // The specialist's own line for the officer, written over its assessments
  // only. A later round re-narrates with the fuller picture, so take the last.
  const narration = own.filter((e) => e.event_type === 'specialist_narrated')
    .map((e) => String(pay(e).narration)).at(-1)
  const observations = own.filter((e) => e.event_type === 'observation_recorded').map(pay)
  const postures = own.filter((e) => e.event_type === 'control_posture_recorded').map(pay)
  const failure = own.find((e) => e.event_type === 'specialist_failed')
  const ownFacts = useMemo(() => {
    // The floor's current picture for this agent: every fact of its domain,
    // latest version per rule-and-run. A later round re-records only what
    // changed, so a turn's own fact events understate what it checked.
    const latest = new Map<string, Fact>()
    for (const f of facts.values()) if (f.domain === agent) latest.set(f.fact_id.split('@')[0], f)
    return [...latest.values()]
  }, [facts, agent])
  const counts = progress?.fact_counts ?? (ownFacts.length ? {
    total: ownFacts.length,
    satisfied: ownFacts.filter((f) => f.kind === 'satisfied').length,
    breach: ownFacts.filter((f) => f.kind === 'breach').length,
    absent: ownFacts.filter((f) => f.kind === 'absent').length,
    measurement: ownFacts.filter((f) => f.kind === 'measurement').length,
  } : null)

  const nodeEvents = live.filter((e): e is Extract<FeedEvent, { kind: 'node' }> => e.kind === 'node' && e.node === agent)
  const startedLive = nodeEvents.find((e) => e.status === 'inProgress')
  const completeLive = [...nodeEvents].reverse().find((e) => e.status === 'complete')
  const runDone = group.events.some((e) => e.event_type === 'run_completed')
  const adverse = assessments.some((a) => ['breach', 'concern'].includes(a.verdict))

  let status: StepStatus
  if (failure) status = 'failed'
  else if (progress?.status === 'complete' || runDone || (!running && assessments.length)) status = adverse ? 'flagged' : 'done'
  else if (running && (progress || startedLive)) status = 'working'
  else if (running) status = 'queued'
  else status = adverse ? 'flagged' : 'done'

  const took = startedLive && completeLive ? durationLabel(completeLive.at - startedLive.at)
    : dispatch && assessments.length && !running ? null : null
  // The header answers "what did it find" before "what did it check".
  const failures = failureSummary(occurrences)
  const summary = [failures, specialistSummary(counts, assessments, status === 'flagged' ? 'done' : status,
    { verdictCounts: !failures })].filter(Boolean).join(' · ')
  const instruction = dispatch ? (pay(dispatch).instruction as string) : ''

  return (
    <Step id={turnAnchor(agent, group.runId)} icon={meta.icon} tone={tone} title={meta.label} summary={summary} status={status} took={took} focused={focused} nested>
      {/* No thinking drawer here, from either source — the streamed reasoning
          blocks OR the `reasoning` field of the tool call. A specialist's
          working reaches the reader as the narrative under the failure it
          explains; a row of "Thought for under a second" per agent was pure
          noise. The orchestrator and synthesizer keep theirs, because their
          reasoning has nowhere else to go. */}
      {status === 'working' && (
        <p className="flex items-center gap-1.5 text-[13px] text-muted-foreground"><Loader2 className="size-3 animate-spin" />Rules checked; reasoning over the evidence.</p>
      )}
      {/* First: what a supervisor should be worried about, in two or three
          sentences, before the evidence that establishes it. Grounded in this
          specialist's assessments — it cannot carry a claim they do not make. */}
      {narration && (
        <p className="rounded-lg border-l-2 border-brand-blue/50 bg-muted/40 px-3 py-2.5 text-[13px] leading-6">
          {narration}
        </p>
      )}
      {failure && <p className="rounded-lg border border-red-500/30 bg-red-500/[0.04] px-3 py-2 text-[13px] text-red-700 dark:text-red-400">{String(pay(failure).message)} The judged rules are recorded as inconclusive, not as clear.</p>}
      {occurrences.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[12.5px] font-medium text-muted-foreground">
            {occurrences.length === 1 ? 'Failure found' : `${occurrences.length} failures found`} · catalogue {occurrences[0].catalogue_version}
          </p>
          {/* An occurrence is a projection of exactly one assessment, so the
              "why" belongs inside the row it explains — two lists saying the
              same thing left the reader matching them up by eye. */}
          <FailureList
            occurrences={occurrences}
            onOpenRun={onOpenRun}
            detail={(o) => {
              const a = byAssessment.get(o.assessment_id)
              return a ? <VerdictCard a={a} facts={facts} onOpenRun={onOpenRun} loaded={factsLoaded} hideRuns /> : undefined
            }}
          />
        </div>
      )}
      {otherVerdicts.length > 0 && (
        // Verdicts that map to no catalogue failure: a clean judged rule, a
        // data gap, a broad reconciliation concern. Real output, but not the
        // headline, so they stay behind a disclosure.
        <Section title={`${otherVerdicts.length} other verdict${otherVerdicts.length === 1 ? '' : 's'} · no catalogue failure`}>
          <div className="space-y-2">
            {otherVerdicts.map((a) => <VerdictCard key={a.assessment_id} a={a} facts={facts} onOpenRun={onOpenRun} loaded={factsLoaded} />)}
          </div>
        </Section>
      )}
      {postures.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[12.5px] font-medium text-muted-foreground">Control posture</p>
          {postures.map((p, i) => (
            <div key={i} className="flex items-start gap-2 rounded-lg border px-3 py-2 text-[13px]">
              <span className={cn('mt-0.5 rounded-full px-2 py-0.5 text-[11px] font-medium', p.posture === 'effective' ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400' : 'bg-amber-500/10 text-amber-700 dark:text-amber-400')}>{String(p.posture)}</span>
              <span className="leading-6">{p.control_id && <span className="font-mono text-[11px] text-muted-foreground">{p.control_id} · </span>}{p.narrative}</span>
            </div>
          ))}
        </div>
      )}
      {observations.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[12.5px] font-medium text-muted-foreground">Also noted · not verified, never scored</p>
          {observations.map((o, i) => <p key={i} className="rounded-lg border border-dashed px-3 py-2 text-[13px] leading-6">{o.note}<span className="block text-[11px] italic text-muted-foreground">{o.cited_evidence}</span></p>)}
        </div>
      )}
      {/* "What it was given" lived here — a list of evidence block names. The
          exact context is still recorded on dispatch_recorded and readable in
          the timeline, which is where an auditor looks; inside a turn it sat
          between the reader and the findings. The orchestrator's briefing
          stays, because it is an instruction someone gave, not a manifest. */}
      {instruction && (
        <p className="text-[13px] italic leading-6 text-muted-foreground">
          Briefing from the orchestrator: &ldquo;{instruction}&rdquo;
        </p>
      )}
      {/* The full rule-by-rule dump used to live here. The counts are still in
          the step's summary line, and every rule result stays on the ledger and
          in the timeline; six hundred rows inside a turn only buried the
          findings. Facts a claim actually cites are under that claim. */}
    </Step>
  )
}


// ---------------------------------------------------------------------------
// One run = one assistant turn
// ---------------------------------------------------------------------------

function RunTurn({ group, running, live, liveReply, pendingQuestion, progress, facts, officer, focusedStep, onOpenRun, onDecision, onOpenReport, gate }: {
  group: RunGroup; running: boolean; live: FeedEvent[]; liveReply?: string | null; progress: Record<string, SpecialistProgress>
  pendingQuestion?: string | null
  facts: Map<string, Fact>; officer: string; focusedStep: string | null
  onOpenRun: (run: string) => void; onDecision: () => void; onOpenReport: () => void
  gate: { context: GateContext } | null
}) {
  const ev = group.events
  const find = (type: string) => ev.find((e) => e.event_type === type)
  const all = (type: string) => ev.filter((e) => e.event_type === type)
  const started = find('run_started')
  const completed = find('run_completed')
  const sp = started ? pay(started) : {}
  const question = find('question_asked')
  const reply = find('orchestrator_replied')
  const planned = find('dispatch_planned')
  const selected: string[] = planned ? (pay(planned).selected_skills ?? []) : []
  const factsLoaded = facts.size > 0

  const dispatched = unique(all('dispatch_recorded').map((e) => String(pay(e).target)))
  const liveWorkers = unique(live.filter((e) => e.kind === 'node' && !ORCHESTRATOR_STEPS.has(e.node) && !SUPPORT_NODES.has(e.node)).map((e) => e.node))
  const agents = orderAgents(unique([...dispatched, ...liveWorkers]).filter((a) => a !== 'investigator'), selected)

  const userText = question ? String(pay(question).question)
    : group.kind === 'investigation' && pendingQuestion ? pendingQuestion
    : group.kind === 'triage' ? (sp.directive ? `Look again — ${sp.directive.instructions}` : sp.deterministic_only ? 'Run the review with the rules only, no model judgement' : String(sp.request || 'Run the full review'))
    : group.kind === 'drafting' ? 'Draft the supervisory report' : null
  const by = question ? question.actor.replace('human:', '') : officer

  // The orchestrator speaks twice in a turn from two different nodes: it
  // routes at `orchestrate` and closes at `record`. Keep the second one out
  // of the routing step — it belongs to the closing brief at the bottom.
  const orchestratorThinking = live.filter((e): e is ReasoningEvent => e.kind === 'reasoning' && ORCHESTRATOR_STEPS.has(e.node) && e.node !== 'record').filter(spoken)
  const orchestratorTools = live.filter((e): e is ToolCallEvent => e.kind === 'tool' && ORCHESTRATOR_STEPS.has(e.node) && e.node !== 'record')
  const closingThinking = live.filter((e): e is ReasoningEvent => e.kind === 'reasoning' && e.node === 'record').filter(spoken)
  const closingTools = live.filter((e): e is ToolCallEvent => e.kind === 'tool' && e.node === 'record')
  const synthTools = live.filter((e): e is ToolCallEvent => e.kind === 'tool' && e.node === 'synthesizer')
  const synthThinking = live.filter((e): e is ReasoningEvent => e.kind === 'reasoning' && e.node === 'synthesizer').filter(spoken)
  const investigatorThinking = live.filter((e): e is ReasoningEvent => e.kind === 'reasoning' && e.node === 'investigator').filter(spoken)
  const investigatorTools = live.filter((e): e is ToolCallEvent => e.kind === 'tool' && e.node === 'investigator')

  const orchestratorFailure = all('specialist_failed').map(pay).find((f) => f.agent === 'orchestrator')
  const escalations = all('escalation_round_started')
  const critic = all('critic_checked')
  const correlations = all('correlation_recorded')
  const closing = all('orchestrator_summarised').at(-1)
  const investigation = find('investigation_completed')
  const investigatorDispatched = dispatched.includes('investigator') || liveWorkers.includes('investigator')
  const reports = all('report_drafted')
  const groundings = all('grounding_checked')
  // Not a block, and never rendered as one: the drafting model returning
  // nothing usable is the only way a requested report fails to exist, and the
  // officer who pressed the button has to be told.
  const draftingFailed = all('specialist_failed').map(pay).find((f) => f.agent === 'drafting')
  const decisions = all('decision_recorded')
  const score = all('score_computed').at(-1)
  const recommendation = all('authorisation_computed').at(-1)
  const took = started && completed ? durationLabel(new Date(completed.recorded_at).getTime() - new Date(started.recorded_at).getTime()) : null

  const plan: P = planned ? (pay(planned).plan ?? {}) : {}
  // The orchestrator's finished route call, before the ledger's copy of the
  // plan has been fetched: the skills it named and its message to the officer.
  const routeCall = [...orchestratorTools].reverse().find((t) => t.status === 'complete')
  const routed: P = routeCall?.args ?? {}
  const routedSkills = Array.isArray(routed.dispatches)
    ? routed.dispatches.map((d: unknown) => (d && typeof d === 'object' ? (d as P).skill : undefined)).filter((skill: unknown): skill is string => typeof skill === 'string')
    : []
  const skillsUsed: string[] = unique([...((plan.skills ?? selected) as string[]), ...routedSkills])
  const leftOut: string[] = (plan.not_dispatched ?? []) as string[]
  const intent: string | undefined = plan.intent ?? (typeof routed.intent === 'string' ? routed.intent : undefined)
  const orchestratorDecided = !!planned || !!liveReply || !!routeCall
  const orchestratorSummary = !orchestratorDecided
    ? (running ? (group.kind === 'investigation' ? 'Reading your question' : 'Deciding what to run') : 'Routed')
    : intent === 'reply' ? 'Answered from the record'
    : intent === 'draft_report' ? 'Started the report'
    : skillsUsed.length ? `Briefed ${skillsUsed.length === 1 ? nodeMeta(skillAgent(skillsUsed[0])).label : `${skillsUsed.length} specialists`}` : 'Routed'
  const orchestratorStatus: StepStatus = orchestratorFailure ? 'failed' : running && !orchestratorDecided && group.kind !== 'drafting' ? 'working' : leftOut.length ? 'flagged' : 'done'
  const message = reply ? String(pay(reply).message) : (liveReply || (typeof routed.message_to_officer === 'string' ? routed.message_to_officer : ''))

  return (
    <div className="flex flex-col gap-4">
      {userText && <UserBubble text={userText} by={by} at={started?.recorded_at} />}
      <div className="flex gap-3">
        <span className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Waypoints className="size-4" strokeWidth={2.25} />
        </span>
        <div className="min-w-0 flex-1 space-y-3">
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <span className="font-medium">{RUN_TITLE[group.kind] ?? group.kind}</span>
            <span className="font-mono">{group.runId}</span>
            {took && <span>· {took}</span>}
            {running && <span className="ml-1 inline-flex items-center gap-1 text-amber-700 dark:text-amber-400"><span className="size-1.5 animate-pulse rounded-full bg-amber-500" />live</span>}
          </div>

          {group.kind !== 'drafting' && (
            <Step icon={Waypoints} tone={{ bg: 'bg-primary/10', text: 'text-primary' }} title="Orchestrator" summary={orchestratorSummary} status={orchestratorStatus}>
              {orchestratorThinking.map((r) => <Thinking key={r.key} text={r.text} working={!r.done} startedAt={r.at} endedAt={r.endedAt} />)}
              {orchestratorTools.map((t) => <ToolReasoning key={t.key} tool={t} />)}
              {planned && !orchestratorTools.length && plan.reasoning && <Thinking text={String(plan.reasoning)} working={false} />}
              {orchestratorFailure && (
                <p className="flex items-center gap-1.5 text-[13px] text-red-700 dark:text-red-400"><XCircle className="size-3.5" />{String(orchestratorFailure.message)}</p>
              )}
              {skillsUsed.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[12px] text-muted-foreground">Skills used</span>
                  {skillsUsed.map((skill) => {
                    const meta = nodeMeta(skillAgent(skill)); const tone = AGENT_ICON[meta.color]
                    return <span key={skill} className={cn('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium', tone.bg, tone.text)}><meta.icon className="size-3" />{meta.label}</span>
                  })}
                </div>
              )}
              {leftOut.length > 0 && (
                <p className="flex items-center gap-1.5 text-[13px] text-amber-700 dark:text-amber-400"><TriangleAlert className="size-3.5" />Left out of the first pass: {leftOut.map((s) => nodeMeta(skillAgent(s)).label).join(', ')}. Nothing was added behind its back; this is on the record.</p>
              )}
            </Step>
          )}

          {message && (
            <div className="rounded-xl border border-primary/20 bg-primary/[0.03] px-4 py-3">
              <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-primary">Orchestrator</p>
              <Prose><p>{message}</p></Prose>
            </div>
          )}

          {(investigatorDispatched || investigation) && (
            <Step icon={SearchCheck} tone={AGENT_ICON.teal} title="Investigator" summary={investigation ? 'Answered from the record with read-only lookups' : 'Looking it up'} status={investigation ? 'done' : running ? 'working' : 'done'} nested>
              {investigatorThinking.map((r) => <Thinking key={r.key} text={r.text} working={!r.done} startedAt={r.at} endedAt={r.endedAt} />)}
              {investigatorTools.filter((t) => t.name.startsWith('record_')).map((t) => <ToolReasoning key={t.key} tool={t} />)}
              {investigatorTools.filter((t) => !t.name.startsWith('record_')).map((t) => (
                <p key={t.key} className="flex items-center gap-1.5 text-[13px] text-muted-foreground">
                  {t.status === 'complete' ? <Check className="size-3.5 text-emerald-600" /> : <Loader2 className="size-3.5 animate-spin" />}
                  {toolLabel(t.name)}
                  {argsSummary(t.args) && <span className="font-mono text-[11px]">{argsSummary(t.args)}</span>}
                </p>
              ))}
              {investigation && (
                <>
                  <Prose><p>{pay(investigation).answer}</p></Prose>
                  {(pay(investigation).cited_evidence ?? []).length > 0 && <p className="text-[12px] text-muted-foreground">Cited: {(pay(investigation).cited_evidence as string[]).join(' · ')}</p>}
                  {(pay(investigation).tool_calls ?? []).length > 0 && <p className="text-[12px] text-muted-foreground">{(pay(investigation).tool_calls as P[]).map((t) => toolLabel(t.tool)).join(' · ')} — every result recorded by digest.</p>}
                </>
              )}
            </Step>
          )}

          {agents.filter((a) => a !== 'control_assurance').map((agent) => (
            <SpecialistStep key={agent} agent={agent} group={group} running={running} live={live} progress={progress[agent]?.run_id === group.runId ? progress[agent] : undefined} facts={facts} factsLoaded={factsLoaded} focused={focusedStep === turnAnchor(agent, group.runId)} onOpenRun={onOpenRun} />
          ))}

          {escalations.map((e) => (
            <p key={e.seq} className="flex items-center gap-2 text-[13px] text-muted-foreground"><RotateCw className="size-3.5" />Second look · asked {(pay(e).targets as string[]).map((t) => nodeMeta(t).label).join(' and ')} to resolve what they left open.</p>
          ))}

          {agents.includes('control_assurance') && (
            <SpecialistStep agent="control_assurance" group={group} running={running} live={live} progress={progress.control_assurance?.run_id === group.runId ? progress.control_assurance : undefined} facts={facts} factsLoaded={factsLoaded} focused={focusedStep === turnAnchor('control_assurance', group.runId)} onOpenRun={onOpenRun} />
          )}

          {critic.length > 0 && (
            <Step icon={ShieldCheck} tone={AGENT_ICON.slate} title="Critic" summary={`Checked every number the specialists quoted · ${critic.filter((c) => pay(c).passed).length} verified, ${critic.filter((c) => !pay(c).passed).length} flagged`} status={critic.some((c) => !pay(c).passed) ? 'flagged' : 'done'}>
              {critic.map((c) => (
                <p key={c.seq} className="flex flex-wrap items-center gap-1.5 text-[13px]">
                  {pay(c).passed ? <Check className="size-3.5 text-emerald-600" /> : <TriangleAlert className="size-3.5 text-amber-600" />}
                  <span className="font-medium">{nodeMeta(pay(c).target).label}</span>
                  <span className="text-muted-foreground">{pay(c).passed ? `quoted values verified (${pay(c).checked} checked)` : `quoted values not found in its briefing: ${(pay(c).unquoted_values ?? []).join(', ')} — those judgements count as undecided`}</span>
                </p>
              ))}
            </Step>
          )}

          {/* Reasoning is deliberately NOT rendered here. The synthesizer records
              none — every open pass showed "No reasoning was recorded for this
              step", a disclosure control that only ever disclosed its own
              emptiness. Its live activity still opens the step (the condition
              below), so "Working · Connecting the findings" is unaffected. */}
          {(correlations.length > 0 || synthThinking.length > 0 || synthTools.length > 0) && (
            <Step icon={GitMerge} tone={AGENT_ICON.indigo} title="Synthesizer" summary={correlations.length ? `Connected the findings · ${correlations.length} ${correlations.length === 1 ? 'link' : 'links'}` : 'Connecting the findings'} status={correlations.length ? 'done' : running ? 'working' : 'done'}>
              {correlations.map((c) => (
                <CorrelationLink
                  key={c.seq}
                  relationship={String(pay(c).relationship).replaceAll('_', ' ')}
                  explanation={String(pay(c).explanation)}
                  findingIds={(pay(c).finding_ids ?? []) as string[]}
                />
              ))}
            </Step>
          )}

          {(closing || closingThinking.length > 0 || closingTools.length > 0) && (
            <div className="rounded-xl border border-primary/20 bg-primary/[0.03] px-4 py-3">
              <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-primary">Orchestrator</p>
              {!closing && closingThinking.map((r) => <Thinking key={r.key} text={r.text} working={!r.done} startedAt={r.at} endedAt={r.endedAt} />)}
              {closing
                ? <Prose><p>{String(pay(closing).message)}</p></Prose>
                : <p className="flex items-center gap-2 text-[13px] text-muted-foreground"><Loader2 className="size-3.5 animate-spin" />Reading back what came in</p>}
            </div>
          )}

          {reports.map((r, i) => (
            <div key={r.seq} className="space-y-3">
              {/* No thinking drawer on the drafter either, for the reason given
                  at the specialist step: its working reaches the reader as the
                  report. One drawer per internal attempt — and the drafter
                  retries a malformed reply — stacked seven of them above the
                  report, most reading "n/a" because there was no text to show. */}
              <div className="rounded-xl border bg-card px-4 py-3.5">
                <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"><FileText className="size-3.5" />Supervisory report · draft {reports.length > 1 ? i + 1 : ''}</p>
                <p className="mt-2 text-[14px] leading-6">{pay(r).overall_assessment}</p>
                <p className="mt-1.5 text-[13px] text-muted-foreground">
                  {(pay(r).sections ?? []).length} section{((pay(r).sections ?? []).length) === 1 ? '' : 's'}, each citing the findings it rests on.
                </p>
                {i === reports.length - 1 && (
                  <div className="mt-3 flex flex-wrap items-center gap-3 border-t pt-3">
                    <p className="flex-1 text-[13px] text-muted-foreground">
                      {decisions.length
                        ? 'A named decision is on the record.'
                        : 'Read the draft in full, then sign it on the Decision tab: a report cannot issue until a named supervisor records the decision it rests on.'}
                    </p>
                    {/* The transcript used to name the tab and leave the reader
                        to find it. The draft is the case's principal artefact —
                        it gets a door, not a direction. */}
                    <Button size="sm" variant="outline" onClick={onOpenReport}>
                      <FileText data-icon="inline-start" />
                      Open the draft
                    </Button>
                  </div>
                )}
              </div>
            </div>
          ))}
          {running && group.kind === 'drafting' && !reports.length && (
            <p className="flex items-center gap-1.5 text-[13px] text-muted-foreground"><Loader2 className="size-3 animate-spin" />Writing the report from the findings on the record.</p>
          )}
          {groundings.map((g) => (
            <p key={g.seq} className="flex items-center gap-2 text-[13px] text-muted-foreground"><ShieldCheck className={cn('size-3.5', pay(g).passed ? 'text-emerald-600' : 'text-amber-600')} />{pay(g).passed ? 'Grounding passed — every claim cites a real finding.' : `Grounding flagged ${(pay(g).problems as string[]).length} point(s) on this draft — recorded for the reviewer.`}</p>
          ))}
          {draftingFailed && (
            <p className="rounded-lg border border-amber-500/30 bg-amber-500/[0.05] px-3 py-2 text-[13px] text-amber-700 dark:text-amber-400">
              {String(draftingFailed.message)} Ask again when you are ready.
            </p>
          )}
          {decisions.map((d) => (
            <p key={d.seq} className="flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-[13px]">
              {pay(d).action === 'approve' ? <BadgeCheck className="size-4 text-emerald-600" /> : pay(d).action === 'reject' ? <XCircle className="size-4 text-muted-foreground" /> : <RotateCw className="size-4 text-muted-foreground" />}
              <span className="font-semibold">{pay(d).action === 'approve' ? 'Report issued' : pay(d).action === 'reject' ? 'Report rejected' : 'Sent back for another look'}</span>
              <span className="text-muted-foreground">signed by {pay(d).reviewer} · {fmtTime(pay(d).decided_at)}</span>
              {pay(d).comment && <span className="w-full italic text-muted-foreground">“{pay(d).comment}”</span>}
            </p>
          ))}

          {(score || recommendation) && (
            <Outcome score={score ? (pay(score) as unknown as RiskScore) : null} rec={recommendation ? pay(recommendation) : null} kind={group.kind} drafted={reports.length > 0} />
          )}

          {running && !ev.length && !live.length && (
            <p className="flex items-center gap-2 text-[13px] text-muted-foreground"><Loader2 className="size-3.5 animate-spin" />Starting…</p>
          )}

          {gate && group.kind === 'drafting' && !completed && <GateNotice onDecision={onDecision} />}
        </div>
      </div>
    </div>
  )
}

/** The gate itself is NOT here. A paused pipeline is a state the room has to
 * announce, but the sign-off — reviewer name, approve/reject, send-back with
 * instructions — is one act with one home, the Decision tab. The room says
 * what is waiting and hands the officer over; it does not offer a second copy
 * of the form. */
function GateNotice({ onDecision }: { onDecision: () => void }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-primary/40 bg-primary/5 px-4 py-3 ring-1 ring-primary/10">
      <UserRoundCheck className="size-4 shrink-0 text-primary" />
      <div className="min-w-[14rem] flex-1">
        <p className="text-sm font-semibold">Reviewer decision required</p>
        <p className="text-[13px] text-muted-foreground">The pipeline is paused — nothing issues without a named sign-off.</p>
      </div>
      <Button size="sm" onClick={onDecision}>
        <ScrollText data-icon="inline-start" />
        Go to the decision
      </Button>
    </div>
  )
}

/** Where the turn leaves the officer: the numbers the orchestrator's brief
 * does NOT state, and the choice of what to do next.
 *
 * The prose that used to live here — the verdict counts, the recommendation,
 * the outstanding-evidence list — is now the orchestrator's closing brief a
 * few lines above, said once in its own voice instead of twice in two
 * registers. What stays is what the brief does not say: the score, the policy
 * that produced it, and the two ways forward. No decision is offered here;
 * a decision follows a report, and the report has not been drafted yet. */
function Outcome({ score, rec, kind, drafted }: {
  score: RiskScore | null; rec: P | null; kind: RunGroup['kind']; drafted: boolean
}) {
  // Both ways forward stay open after a review AND after a follow-up: the
  // officer either asks another question below or draws the report.
  const canDraft = kind !== 'drafting' && !drafted
  return (
    <div className="space-y-2.5">
      <div className="flex flex-wrap items-center gap-2">
        {score && (
          <span className={cn('inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[12px] font-medium', TIER_TONE[score.tier])}>
            Risk score {score.total.toFixed(2)} · {score.tier_label}
          </span>
        )}
        {rec && (
          <span className="text-[12px] text-muted-foreground">
            {DISPOSITION_LABEL[rec.disposition as keyof typeof DISPOSITION_LABEL] ?? rec.disposition} · policy {rec.policy_version}
          </span>
        )}
      </div>
      {canDraft && (
        <p className="text-[13px] text-muted-foreground">
          Ask a follow-up below to take this further, or use <span className="font-medium text-foreground">Draft report</span> in the composer when you have seen enough — the report is what a signed decision rests on.
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// The conversation surface
// ---------------------------------------------------------------------------

export interface CaseChatProps {
  events: LedgerEvent[] | null
  /** The whole record, for evidence lookups — the transcript may be showing
   * only the events after a "New chat", but a verdict still cites facts
   * recorded before it. */
  factsSource?: LedgerEvent[] | null
  hiddenCount: number
  onShowEarlier: () => void
  live: FeedEvent[]
  running: 'triage' | 'session' | 'drafting' | null
  progress: Record<string, SpecialistProgress>
  pendingQuestion: string | null
  pendingReply: string | null
  gate: { context: GateContext } | null
  officer: string
  focusedStep: string | null
  onOpenRun: (run: string) => void
  onDecision: () => void
  onOpenReport: () => void
  onSend: (text: string) => void
  onRun: () => void
  onDraft: () => void
  onCloseCase: () => void
  busy: boolean
  hasTriage: boolean
  closable: boolean
}

const LIVE_KIND: Record<NonNullable<CaseChatProps['running']>, RunGroup['kind']> = { triage: 'triage', session: 'investigation', drafting: 'drafting' }

export function CaseChat({
  events, factsSource, hiddenCount, onShowEarlier, live, running, progress, pendingQuestion, pendingReply, gate,
  officer, focusedStep, onOpenRun, onDecision, onOpenReport, onSend, onRun, onDraft, onCloseCase, busy, hasTriage, closable,
}: CaseChatProps) {
  const [draft, setDraft] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const viewportRef = useRef<HTMLElement | null>(null)
  const followRef = useRef(true)

  const items = useMemo(() => buildTranscript(events ?? []), [events])
  const facts = useMemo(() => new Map((factsSource ?? events ?? []).filter((e) => e.event_type === 'fact_recorded').map((e) => [String(pay(e).fact_id), e.payload as unknown as Fact])), [factsSource, events])

  // The turn the live stream belongs to: the newest unfinished run of the
  // running kind, or a placeholder until the ledger has a run id for it.
  // After a run finishes, its thinking stays attached to that run until the
  // next run or a new chat clears the feed.
  const runs = items.filter((i): i is Extract<Item, { type: 'run' }> => i.type === 'run')
  const liveGroup: RunGroup | null = useMemo(() => {
    if (!live.length && !running) return null
    const kind = running ? LIVE_KIND[running] : null
    const candidates = kind ? runs.filter((r) => r.group.kind === kind) : runs
    const last = candidates.at(-1)?.group ?? null
    if (running && (!last || last.events.some((e) => e.event_type === 'run_completed'))) return { runId: 'live', kind: kind ?? 'triage', events: [] }
    return last
  }, [live.length, running, runs])

  useEffect(() => {
    const viewport = bottomRef.current?.closest('[data-slot="scroll-area-viewport"]') as HTMLElement | null
    if (!viewport) return
    viewportRef.current = viewport

    const isAtBottom = () => viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 120
    const onScroll = () => { followRef.current = isAtBottom() }
    // A streamed update can render before the browser has dispatched the
    // corresponding scroll event.  Mark an upward gesture immediately, so
    // that update cannot pull someone reading earlier activity back down.
    const onWheel = (event: WheelEvent) => {
      if (event.deltaY < 0) followRef.current = false
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (['ArrowUp', 'PageUp', 'Home'].includes(event.key) || (event.key === ' ' && event.shiftKey)) {
        followRef.current = false
      }
    }

    // The room is remounted whenever the officer returns from another case
    // page. A fresh viewport starts at its top, so deliberately reopen at
    // the latest turn instead.
    followRef.current = true
    viewport.scrollTop = viewport.scrollHeight
    viewport.addEventListener('scroll', onScroll, { passive: true })
    viewport.addEventListener('wheel', onWheel, { passive: true })
    viewport.addEventListener('keydown', onKeyDown)
    return () => {
      viewport.removeEventListener('scroll', onScroll)
      viewport.removeEventListener('wheel', onWheel)
      viewport.removeEventListener('keydown', onKeyDown)
      if (viewportRef.current === viewport) viewportRef.current = null
    }
  }, [])
  useLayoutEffect(() => {
    const viewport = viewportRef.current
    if (viewport && followRef.current) viewport.scrollTop = viewport.scrollHeight
  }, [items, live, pendingQuestion, pendingReply, gate, progress])

  const send = () => {
    const text = draft.trim()
    if (!text || busy) return
    setDraft('')
    onSend(text)
  }

  const turnProps = { progress, facts, officer, focusedStep, onOpenRun, onDecision, onOpenReport, gate }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ScrollArea className="min-h-0 flex-1">
        <div className="mx-auto flex max-w-3xl flex-col gap-6 px-5 py-6">
          {hiddenCount > 0 && (
            <button type="button" onClick={onShowEarlier} className="mx-auto rounded-full border px-3 py-1 text-[11px] text-muted-foreground hover:text-foreground">
              Earlier activity hidden · show {hiddenCount} events
            </button>
          )}
          {events === null && <p className="py-10 text-center text-sm text-muted-foreground">Loading the record…</p>}
          {events !== null && items.length === 0 && !running && (
            <div className="py-14 text-center">
              <p className="font-heading text-lg font-semibold">A clean slate.</p>
              <p className="mt-1 text-sm text-muted-foreground">Run the review, or ask the orchestrator anything about this dossier.</p>
            </div>
          )}
          {items.map((item) => {
            if (item.type === 'system') {
              const Icon = item.icon
              return (
                <div key={`${item.text}-${item.at}`} className="flex items-center justify-center gap-1.5 text-[11.5px] text-muted-foreground">
                  <Icon className="size-3" />
                  {item.text}
                  <span className="font-mono text-[10px] text-muted-foreground/60">{fmtTime(item.at)}</span>
                </div>
              )
            }
            const isLive = liveGroup?.runId === item.group.runId
            return <RunTurn key={item.group.runId} group={item.group} running={isLive && !!running} live={isLive ? live : []} liveReply={isLive ? pendingReply : null} pendingQuestion={isLive ? pendingQuestion : null} {...turnProps} />
          })}
          {liveGroup?.runId === 'live' && (
            <>
              {pendingQuestion && <UserBubble text={pendingQuestion} by={officer} />}
              <RunTurn group={liveGroup} running live={live} liveReply={pendingReply} pendingQuestion={pendingQuestion} {...turnProps} />
            </>
          )}
          {gate && !runs.some((r) => r.group.kind === 'drafting' && !r.group.events.some((e) => e.event_type === 'run_completed')) && (
            <div className="pl-10"><GateNotice onDecision={onDecision} /></div>
          )}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      <div className="px-5 pb-4 pt-2">
        <div className="mx-auto max-w-3xl">
          <div className={cn('rounded-2xl border shadow-sm transition-all', busy ? 'border-border/60 bg-muted/60 text-muted-foreground shadow-none' : 'bg-card focus-within:shadow-md focus-within:ring-2 focus-within:ring-ring/25')}>
            {/* Nothing to ask about until a review has run: before the first
                pass the composer is the Run button and a line saying so, not
                an empty prompt the orchestrator cannot usefully answer. */}
            {hasTriage ? (
              <textarea
                value={draft}
                disabled={busy}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    send()
                  }
                }}
                placeholder={busy ? 'Waiting for the orchestrator…' : 'Ask the orchestrator — “who is Quickvale?”, “have Log look at the same-day pair again”, “draft the report”'}
                rows={2}
                className="w-full resize-none bg-transparent px-4 pt-3.5 text-[15px] leading-6 outline-none placeholder:text-muted-foreground"
              />
            ) : (
              <p className="px-4 pt-3.5 text-[15px] leading-6 text-muted-foreground">
                {busy ? 'Running the first pass — every specialist over the whole dossier.' : 'Run the first pass to review this dossier.'}
              </p>
            )}
            <div className="flex flex-wrap items-center gap-1 px-2 pb-2">
              <Button size="sm" variant={hasTriage ? 'ghost' : 'secondary'} onClick={onRun} disabled={busy} className="h-8">
                <Play data-icon="inline-start" />
                Run
              </Button>
              <Button size="sm" variant="ghost" onClick={onDraft} disabled={busy || !hasTriage} className="h-8">
                <FileText data-icon="inline-start" />
                Draft report
              </Button>
              <Button size="sm" variant="ghost" onClick={onDecision} disabled={busy || !hasTriage} className="h-8">
                <ScrollText data-icon="inline-start" />
                Decision
              </Button>
              {closable && !hasTriage && (
                <Button size="sm" variant="ghost" onClick={onCloseCase} disabled={busy} className="h-8">
                  <BadgeCheck data-icon="inline-start" />
                  Close — no action
                </Button>
              )}
              <span className="ml-auto flex items-center gap-2">
                {/* Read-only here: the name is set once in the top bar,
                    because it is recorded on everything and two edit points
                    can disagree between a review and the signature on it. */}
                <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <UserRound className="size-3.5" />
                  {officer}
                </span>
                <Button size="icon" className="size-8 rounded-full" onClick={send} disabled={busy || !draft.trim()} aria-label="Send">
                  {busy ? <Loader2 className="animate-spin" /> : <ArrowUp />}
                </Button>
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export type { Item as TranscriptItem }
export { EvidenceFields }
