// The case room's transcript — ONE conversation that is the case, read the
// way a Claude conversation reads: the supervisor's requests on the right,
// the pipeline's work on the left as an assistant turn made of steps. Each
// specialist is a step with its own thinking (the working it wrote before
// recording, shown as "Thought for 12s" once it has finished), its
// verdicts in plain language, and — one level down — what it was briefed
// with. No function names, no raw payloads: the machine names stay on the
// ledger, which is what the timeline tab is for.
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
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
  Waypoints,
  XCircle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { nodeMeta, AGENT_ICON } from '@/lib/node-meta'
import { TIER_TONE } from '@/components/ResultsPanel'
import { ReviewGate, type GateSubmission } from '@/components/ReviewGate'
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

const PEER_ORDER = ['mandate', 'kya', 'provenance', 'injection', 'counterparty', 'consent', 'log', 'drift', 'control_assurance', 'systemic', 'red_team', 'investigator']
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
  kind: 'triage' | 'investigation' | 'drafting' | 'portfolio'
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
  if (runId.startsWith('por')) return 'portfolio'
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
      <div className="max-w-[80%] rounded-2xl bg-muted px-4 py-2.5 text-[15px] leading-6 text-foreground">{text}</div>
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
  const context = dispatch ? (pay(dispatch).context_blocks as Record<string, unknown> | undefined) : undefined
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
      {context && (
        <Section title="What it was given">
          {instruction && <p className="mb-2 text-[13px] italic leading-6">Briefing from the orchestrator: “{instruction}”</p>}
          <p className="text-[13px] leading-6 text-muted-foreground">Evidence: {Object.keys(context).filter((k) => k !== 'dossier_id').map((k) => k.replaceAll('_', ' ')).join(' · ')}</p>
          {context.supplementary_context ? <p className="mt-1 text-[12px] text-muted-foreground">Plus record items the orchestrator attached verbatim.</p> : null}
        </Section>
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

function RunTurn({ group, running, live, liveReply, progress, facts, officer, focusedStep, onOpenRun, onDecision, onDraft, gate, gateRisk, findingsCount, onDecide }: {
  group: RunGroup; running: boolean; live: FeedEvent[]; liveReply?: string | null; progress: Record<string, SpecialistProgress>
  facts: Map<string, Fact>; officer: string; focusedStep: string | null
  onOpenRun: (run: string) => void; onDecision: () => void; onDraft: () => void
  gate: { context: GateContext } | null; gateRisk: RiskScore | null; findingsCount: number; onDecide: (d: GateSubmission) => void
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
    : group.kind === 'triage' ? (sp.directive ? `Look again — ${sp.directive.instructions}` : sp.deterministic_only ? 'Run the review with the rules only, no model judgement' : String(sp.request || 'Run the full review'))
    : group.kind === 'drafting' ? 'Draft the supervisory report'
    : group.kind === 'portfolio' ? 'Sweep the portfolio' : null
  const by = question ? question.actor.replace('human:', '') : officer

  const orchestratorThinking = live.filter((e): e is ReasoningEvent => e.kind === 'reasoning' && ORCHESTRATOR_STEPS.has(e.node)).filter(spoken)
  const orchestratorTools = live.filter((e): e is ToolCallEvent => e.kind === 'tool' && ORCHESTRATOR_STEPS.has(e.node))
  const synthTools = live.filter((e): e is ToolCallEvent => e.kind === 'tool' && e.node === 'synthesizer')
  const draftTools = live.filter((e): e is ToolCallEvent => e.kind === 'tool' && e.node === 'draft_report')
  const synthThinking = live.filter((e): e is ReasoningEvent => e.kind === 'reasoning' && e.node === 'synthesizer').filter(spoken)
  const draftThinking = live.filter((e): e is ReasoningEvent => e.kind === 'reasoning' && e.node === 'draft_report').filter(spoken)
  const investigatorThinking = live.filter((e): e is ReasoningEvent => e.kind === 'reasoning' && e.node === 'investigator').filter(spoken)
  const investigatorTools = live.filter((e): e is ToolCallEvent => e.kind === 'tool' && e.node === 'investigator')

  const orchestratorFailure = all('specialist_failed').map(pay).find((f) => f.agent === 'orchestrator')
  const escalations = all('escalation_round_started')
  const critic = all('critic_checked')
  const correlations = all('correlation_recorded')
  const investigation = find('investigation_completed')
  const investigatorDispatched = dispatched.includes('investigator') || liveWorkers.includes('investigator')
  const reports = all('report_drafted')
  const groundings = all('grounding_checked')
  const blocked = find('report_blocked')
  const decisions = all('decision_recorded')
  const score = all('score_computed').at(-1)
  const recommendation = all('authorisation_computed').at(-1)
  const portfolioFindings = all('portfolio_finding_recorded')
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

          {group.kind !== 'drafting' && group.kind !== 'portfolio' && (
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

          {(correlations.length > 0 || synthThinking.length > 0 || synthTools.length > 0) && (
            <Step icon={GitMerge} tone={AGENT_ICON.indigo} title="Synthesizer" summary={correlations.length ? `Connected the findings · ${correlations.length} ${correlations.length === 1 ? 'link' : 'links'}` : 'Connecting the findings'} status={correlations.length ? 'done' : running ? 'working' : 'done'}>
              {synthThinking.map((r) => <Thinking key={r.key} text={r.text} working={!r.done} startedAt={r.at} endedAt={r.endedAt} />)}
              {synthTools.map((t) => <ToolReasoning key={t.key} tool={t} />)}
              {correlations.map((c) => (
                <div key={c.seq} className="rounded-lg border px-3 py-2.5 text-[13px]">
                  <span className="rounded-full bg-indigo-500/10 px-2 py-0.5 text-[11px] font-medium uppercase text-indigo-700 dark:text-indigo-400">{String(pay(c).relationship).replace('_', ' ')}</span>
                  <p className="mt-1.5 leading-6">{pay(c).explanation}</p>
                  <p className="mt-1 font-mono text-[10px] text-muted-foreground">{(pay(c).finding_ids as string[]).join(' · ')}</p>
                </div>
              ))}
            </Step>
          )}

          {reports.map((r, i) => (
            <div key={r.seq} className="space-y-3">
              {i === reports.length - 1 && draftThinking.map((t) => <Thinking key={t.key} text={t.text} working={!t.done} startedAt={t.at} endedAt={t.endedAt} />)}
              {i === reports.length - 1 && draftTools.map((t) => <ToolReasoning key={t.key} tool={t} />)}
              <div className="rounded-xl border bg-card px-4 py-3.5">
                <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"><FileText className="size-3.5" />Supervisory report · draft {reports.length > 1 ? i + 1 : ''}</p>
                <p className="mt-2 text-[14px] leading-6">{pay(r).overall_assessment}</p>
                <p className="mt-1.5 text-[13px] text-muted-foreground">
                  {(pay(r).sections ?? []).length} section{((pay(r).sections ?? []).length) === 1 ? '' : 's'}, each citing the findings it rests on. The full report is on the Findings tab.
                </p>
                {i === reports.length - 1 && (
                  <div className="mt-3 flex flex-wrap items-center gap-2 border-t pt-3">
                    <p className="text-[13px] text-muted-foreground">
                      {decisions.length ? 'A named decision is on the record.' : 'A report cannot issue without a named supervisory decision.'}
                    </p>
                    {!decisions.length && (
                      <Button size="sm" className="ml-auto" onClick={onDecision}>
                        <ScrollText data-icon="inline-start" />
                        Sign the decision
                      </Button>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
          {running && group.kind === 'drafting' && !reports.length && draftThinking.map((t) => <Thinking key={t.key} text={t.text} working={!t.done} startedAt={t.at} endedAt={t.endedAt} />)}
          {running && group.kind === 'drafting' && !reports.length && draftTools.map((t) => <ToolReasoning key={t.key} tool={t} />)}
          {groundings.map((g) => (
            <p key={g.seq} className="flex items-center gap-2 text-[13px] text-muted-foreground"><ShieldCheck className={cn('size-3.5', pay(g).passed ? 'text-emerald-600' : 'text-amber-600')} />{pay(g).passed ? 'Grounding passed — every claim cites a real finding.' : `Grounding failed on attempt ${pay(g).attempt} — regenerating with the validator's complaints.`}</p>
          ))}
          {blocked && <p className="rounded-lg border border-red-500/30 bg-red-500/[0.04] px-3 py-2 text-[13px] text-red-700 dark:text-red-400">Draft blocked after the retry cap: {(pay(blocked).problems as string[]).join('; ')}</p>}
          {decisions.map((d) => (
            <p key={d.seq} className="flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-[13px]">
              {pay(d).action === 'approve' ? <BadgeCheck className="size-4 text-emerald-600" /> : pay(d).action === 'reject' ? <XCircle className="size-4 text-muted-foreground" /> : <RotateCw className="size-4 text-muted-foreground" />}
              <span className="font-semibold">{pay(d).action === 'approve' ? 'Report issued' : pay(d).action === 'reject' ? 'Report rejected' : 'Sent back for another look'}</span>
              <span className="text-muted-foreground">signed by {pay(d).reviewer} · {fmtTime(pay(d).decided_at)}</span>
              {pay(d).comment && <span className="w-full italic text-muted-foreground">“{pay(d).comment}”</span>}
            </p>
          ))}

          {portfolioFindings.map((f) => (
            <div key={f.seq} className="rounded-lg border px-3 py-2.5 text-[13px]"><span className="font-semibold">{pay(f).failure}</span> · {pay(f).summary}<p className="mt-1 text-[11px] text-muted-foreground">{(pay(f).subject_refs ?? []).join(' · ')}</p></div>
          ))}

          {(score || recommendation) && (
            <Outcome score={score ? (pay(score) as unknown as RiskScore) : null} rec={recommendation ? pay(recommendation) : null} kind={group.kind} onDecision={onDecision} onDraft={onDraft} onOpenRun={onOpenRun} />
          )}

          {running && !ev.length && !live.length && (
            <p className="flex items-center gap-2 text-[13px] text-muted-foreground"><Loader2 className="size-3.5 animate-spin" />Starting…</p>
          )}

          {gate && group.kind === 'drafting' && !completed && (
            <ReviewGate key={gate.context.error ?? 'gate'} context={gate.context} onDecide={onDecide} risk={gateRisk} findingsCount={findingsCount} defaultReviewer={officer !== 'Case officer' ? officer : undefined} />
          )}
        </div>
      </div>
    </div>
  )
}

/** The turn's answer: what the review concluded, in sentences a supervisor
 * can act on, with the two things they can do next. */
function Outcome({ score, rec, kind, onDecision, onDraft, onOpenRun }: {
  score: RiskScore | null; rec: P | null; kind: RunGroup['kind']; onDecision: () => void; onDraft: () => void; onOpenRun: (run: string) => void
}) {
  const gates: P[] = rec?.hard_gates ?? []
  const adequacy: P[] = rec?.adequacy ?? []
  const breachRuns = (rec?.runs ?? []).filter((r: P) => r.verdict === 'breach').length
  return (
    <div className="space-y-3">
      <Prose>
        <p>
          <strong>{kind === 'investigation' ? 'Record updated.' : 'Review complete.'}</strong>{' '}
          {rec && <>{rec.factors?.length ?? 0} adverse {rec.factors?.length === 1 ? 'verdict' : 'verdicts'} across {breachRuns} {breachRuns === 1 ? 'run' : 'runs'}; {rec.clean_runs} of {rec.runs?.length ?? 0} runs are clean and {rec.rules_exercised} of {rec.active_rules} active rules produced a determinate result.</>}
        </p>
        {rec && (
          <p>
            Recommendation: <strong>{DISPOSITION_LABEL[rec.disposition as keyof typeof DISPOSITION_LABEL] ?? rec.disposition}</strong>
            {gates.length > 0 && <> — {gates.map((g) => g.reason).join('; ')}</>}.
            {gates.length > 0 && <span className="ml-1 inline-flex flex-wrap gap-x-2">{gates.flatMap((g) => g.run_refs ?? []).map((r: string) => <RunCitation key={r} run={r} onOpenRun={onOpenRun} />)}</span>}
          </p>
        )}
        {adequacy.length > 0 && (
          <div>
            <p className="text-[14px] font-medium">Still needed before authorisation</p>
            <ul className="ml-5 list-disc text-[14px] leading-6 text-foreground/90">{adequacy.map((a, i) => <li key={i}>{a.reason}</li>)}</ul>
          </div>
        )}
      </Prose>
      <div className="flex flex-wrap items-center gap-2">
        {score && (
          <span className={cn('inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[12px] font-medium', TIER_TONE[score.tier])}>
            Risk score {score.total.toFixed(2)} · {score.tier_label}
          </span>
        )}
        {rec && <span className="text-[12px] text-muted-foreground">Policy {rec.policy_version}</span>}
        <span className="ml-auto flex gap-2">
          {kind !== 'investigation' && <Button size="sm" variant="outline" onClick={onDraft}><FileText data-icon="inline-start" />Draft report</Button>}
          <Button size="sm" onClick={onDecision}><BadgeCheck data-icon="inline-start" />Open the decision</Button>
        </span>
      </div>
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
  gateRisk: RiskScore | null
  findingsCount: number
  officer: string
  focusedStep: string | null
  onOpenRun: (run: string) => void
  onDecision: () => void
  onDecide: (d: GateSubmission) => void
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
  events, factsSource, hiddenCount, onShowEarlier, live, running, progress, pendingQuestion, pendingReply, gate, gateRisk, findingsCount,
  officer, focusedStep, onOpenRun, onDecision, onDecide, onSend, onRun, onDraft, onCloseCase, busy, hasTriage, closable,
}: CaseChatProps) {
  const [draft, setDraft] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
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
    const onScroll = () => { followRef.current = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 120 }
    viewport.addEventListener('scroll', onScroll, { passive: true })
    return () => viewport.removeEventListener('scroll', onScroll)
  }, [])
  useEffect(() => {
    const viewport = bottomRef.current?.closest('[data-slot="scroll-area-viewport"]') as HTMLElement | null
    if (viewport && followRef.current) viewport.scrollTop = viewport.scrollHeight
  }, [items, live, pendingQuestion, pendingReply, gate, progress])

  const send = () => {
    const text = draft.trim()
    if (!text || busy) return
    setDraft('')
    onSend(text)
  }

  const turnProps = { progress, facts, officer, focusedStep, onOpenRun, onDecision, onDraft, gate, gateRisk, findingsCount, onDecide }

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
            return <RunTurn key={item.group.runId} group={item.group} running={isLive && !!running} live={isLive ? live : []} liveReply={isLive ? pendingReply : null} {...turnProps} />
          })}
          {liveGroup?.runId === 'live' && (
            <>
              {pendingQuestion && <UserBubble text={pendingQuestion} by={officer} />}
              <RunTurn group={liveGroup} running live={live} liveReply={pendingReply} {...turnProps} />
            </>
          )}
          {gate && !runs.some((r) => r.group.kind === 'drafting' && !r.group.events.some((e) => e.event_type === 'run_completed')) && (
            <div className="pl-10">
              <ReviewGate key={gate.context.error ?? 'gate'} context={gate.context} onDecide={onDecide} risk={gateRisk} findingsCount={findingsCount} defaultReviewer={officer !== 'Case officer' ? officer : undefined} />
            </div>
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
                {/* Read-only here: the name is set once in the sidebar, because
                    it is recorded on everything and two edit points can
                    disagree between a review and the signature on it. */}
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
