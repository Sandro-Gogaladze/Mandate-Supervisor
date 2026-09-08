import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useCoAgent } from '@copilotkit/react-core'
import { useAgent } from '@copilotkit/react-core/v2'
import { toast } from 'sonner'
import {
  ArrowLeft,
  BadgeCheck,
  Expand,
  FolderOpen,
  History,
  ListChecks,
  MessageSquarePlus,
  MessageSquareText,
  PanelRightClose,
  PanelRightOpen,
  Waypoints,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { closeCase, getCase, getFullMap, getLedgerEvents, getDossier, resetReviewHistory } from '@/lib/api'
import type {
  CaseDetail,
  CaseRecord,
  CaseSummary,
  FullMap,
  GateContext,
  GateSubmission,
  LedgerEvent,
  ReviewerDirective,
} from '@/lib/types'
import { EMPTY_AGENT_STATE, type SupervisionAgentState } from '@/lib/agent-state'
import { usePipelineFeed } from '@/hooks/usePipelineFeed'
import { SupervisionMap, type NodeStatus } from '@/components/SupervisionMap'
import { CaseChat } from '@/components/CaseChat'
import { ReportCard } from '@/components/ReportCard'
import { ResultsPanel } from '@/components/ResultsPanel'
import { CaseTimeline } from '@/components/CaseTimeline'
import { ExecutionRuns, ExecutionInspector } from '@/components/ExecutionRuns'
import { AuthorisationPanel } from '@/components/AuthorisationPanel'
import { turnAnchor } from '@/components/AgentTurn'
import type { DossierDetail, SpecialistProgress } from '@/lib/supervision-types'
import { cn } from '@/lib/utils'
import { useOfficer } from '@/lib/officer'

const TRIAGE_AGENT = 'mandate_supervisor'
const SESSION_AGENT = 'supervisor_session'
const DRAFTER_AGENT = 'report_drafter'

// The map shows the supervisor's model of the loop; graph-internal
// plumbing steps fold onto the nearest visible node so live lighting
// still tells the truth. Dispatching (ingest prep, the plan+floor step,
// an escalation re-dispatch, session routing) is the ORCHESTRATOR's own
// act — there is no separate dispatch box; the hub fans straight out.
const STEP_ALIAS: Record<string, string | null> = {
  orchestrate: 'orchestrator',
  record: 'orchestrator',
  ingest: 'orchestrator',
  // The join after the fan-out is graph plumbing, not Control Assurance
  // starting; aliasing it there lit that node "complete" before Control
  // Assurance had begun. It lights from its own step instead.
  specialists_done: null,
  critic: 'findings',
  load_record: 'draft_report',
}

// The five workers run in PARALLEL, but the AG-UI adapter streams one
// active step at a time — trusting its per-worker STEP_FINISHED would show
// a single amber chip hopping around a concurrent fan-out. So: a worker
// goes active on its first step and STAYS active until the run moves past
// the fan (any non-worker step starting = the join), when every active
// worker settles at once — which is what actually happened.
const WORKER_NODES = new Set(['mandate', 'kya', 'provenance', 'injection', 'counterparty', 'consent', 'log', 'drift', 'investigator', 'systemic'])

function CaseReviewInner({ caseSummary, onBack }: { caseSummary: CaseSummary; onBack: () => void }) {
  const caseId = caseSummary.case_id
  const [tab, setTab] = useState('room')
  const [dossier, setDossier] = useState<DossierDetail | null>(null)
  const [selectedRun, setSelectedRun] = useState<string | null>(null)
  const [progress, setProgress] = useState<Record<string, SpecialistProgress>>({})
  const [mapOpen, setMapOpen] = useState<boolean>(() => typeof window !== 'undefined' && window.innerWidth >= 1280)
  const [mapExpanded, setMapExpanded] = useState(false)
  const [focusedStep, setFocusedStep] = useState<string | null>(null)
  const [loadError, setLoadError] = useState('')
  const [map, setMap] = useState<FullMap | null>(null)
  const [detail, setDetail] = useState<CaseDetail | null>(null)
  const [record, setRecord] = useState<CaseRecord | null>(null)
  const [ledger, setLedger] = useState<LedgerEvent[] | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [gate, setGate] = useState<{ id: string; context: GateContext } | null>(null)
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null)
  const [promptOverrides, setPromptOverrides] = useState<Record<string, string>>({})
  const [officer] = useOfficer()
  const [closeOpen, setCloseOpen] = useState(false)
  const [closeOfficer, setCloseOfficer] = useState('')
  const pendingRerun = useRef<ReviewerDirective | null>(null)
  const feed = usePipelineFeed()

  // The ledger IS the transcript; the projection feeds the findings tab.
  const refreshRecord = useCallback(() => {
    getCase(caseId)
      .then((d) => {
        setDetail(d)
        setRecord(d.record)
        setRefreshKey((k) => k + 1)
      })
      .catch(err => setLoadError(String(err)))
    getDossier(caseId).then(d => { setDossier(d); setLoadError('') }).catch(err => setLoadError(String(err)))
    getLedgerEvents(caseId)
      .then(setLedger)
      .catch(err => setLoadError(String(err)))
  }, [caseId])

  useEffect(() => {
    getFullMap().then(setMap).catch(() => setMap(null))
  }, [])
  useEffect(() => {
    refreshRecord()
  }, [refreshRecord])

  const triage = useCoAgent<SupervisionAgentState>({
    name: TRIAGE_AGENT,
    initialState: { ...EMPTY_AGENT_STATE, case_id: caseId },
  })
  const session = useCoAgent<SupervisionAgentState>({
    name: SESSION_AGENT,
    initialState: { ...EMPTY_AGENT_STATE, case_id: caseId },
  })
  const drafter = useCoAgent<SupervisionAgentState>({
    name: DRAFTER_AGENT,
    initialState: { ...EMPTY_AGENT_STATE, case_id: caseId },
  })
  const { agent: triageAgent } = useAgent({ agentId: TRIAGE_AGENT })
  const { agent: sessionAgent } = useAgent({ agentId: SESSION_AGENT })
  const { agent: drafterAgent } = useAgent({ agentId: DRAFTER_AGENT })

  const resetAgent = useCallback((agent: typeof triageAgent, state: SupervisionAgentState) => {
    // Fresh thread per run: the registry agents are shared singletons, and
    // running on a stale thread would merge reducer channels across runs.
    agent.threadId = crypto.randomUUID()
    agent.setMessages([])
    agent.setState({ ...EMPTY_AGENT_STATE, ...state })
  }, [])

  useEffect(() => {
    resetAgent(triageAgent, { case_id: caseId })
    resetAgent(sessionAgent, { case_id: caseId })
    resetAgent(drafterAgent, { case_id: caseId })
    setGate(null)
    setPendingQuestion(null)
    // Mount ≡ case change (keyed by case_id).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId])

  const activeWorkers = useRef<Set<string>>(new Set())
  const recordStep = useCallback(
    (stepName: string, status: 'inProgress' | 'complete') => {
      const target = stepName in STEP_ALIAS ? STEP_ALIAS[stepName] : stepName
      if (!target) return
      if (status === 'inProgress') feed.markStep(target)
      if (WORKER_NODES.has(target)) {
        if (status === 'inProgress') {
          activeWorkers.current.add(target)
          feed.recordNodeEvent(target, 'inProgress')
        }
        // a worker's STEP_FINISHED only means the stream moved to another
        // concurrent worker — ignored; the join below settles them together
        return
      }
      if (status === 'inProgress' && activeWorkers.current.size > 0) {
        for (const worker of activeWorkers.current) feed.recordNodeEvent(worker, 'complete')
        activeWorkers.current.clear()
      }
      feed.recordNodeEvent(target, status)
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  )

  // One feed across all three agents — the conversation's live block and
  // the supervision map read the same stream.
  useEffect(() => {
    const handlers = {
      onCustomEvent: ({ event }: any) => {
        if (event.name !== 'specialist_progress') return
        const p = event.value as SpecialistProgress
        setProgress(previous => ({ ...previous, [p.agent]: p }))
        if (p.events.length) {
          setLedger(previous => [...new Map([...(previous ?? []), ...p.events].map(e => [e.seq, e])).values()].sort((a, b) => a.seq - b.seq))
        }
        if (p.status === 'reasoning' && WORKER_NODES.has(p.agent)) {
          // The floor has landed and the model call is starting — the
          // specialist's own word that it is working, independent of how
          // the step stream interleaves the parallel nodes.
          activeWorkers.current.add(p.agent)
          feed.recordNodeEvent(p.agent, 'inProgress')
        }
        if (p.status === 'complete') {
          activeWorkers.current.delete(p.agent)
          feed.recordNodeEvent(p.agent, 'complete')
        }
      },
      onRunErrorEvent: ({ event }: any) => { toast.error(event.message ?? 'Review failed'); refreshRecord() },
      onStepStartedEvent: ({ event }: any) => recordStep(event.stepName, 'inProgress'),
      onStepFinishedEvent: ({ event }: any) => recordStep(event.stepName, 'complete'),
      // The AG-UI event stream, read directly: the library's typed tool-call
      // callbacks fire only when it can find the call's parent message, and
      // these runs carry no messages.
      onEvent: ({ event }: any) => {
        switch (event.type) {
          case 'REASONING_MESSAGE_START': feed.recordReasoning(event.messageId, 'start'); break
          case 'REASONING_MESSAGE_CONTENT': feed.recordReasoning(event.messageId, 'delta', event.delta ?? ''); break
          case 'REASONING_MESSAGE_END': feed.recordReasoning(event.messageId, 'end'); break
          case 'TEXT_MESSAGE_START': feed.recordText(event.messageId, 'start'); break
          case 'TEXT_MESSAGE_CONTENT': feed.recordText(event.messageId, 'delta', event.delta ?? ''); break
          case 'TEXT_MESSAGE_END': feed.recordText(event.messageId, 'end'); break
          case 'TOOL_CALL_START': feed.startTool(event.toolCallId, event.toolCallName); break
          case 'TOOL_CALL_ARGS': feed.toolArgs(event.toolCallId, event.delta ?? ''); break
          case 'TOOL_CALL_END': feed.endTool(event.toolCallId); break
        }
      },
    }
    const subs = [triageAgent, sessionAgent].map((agent) =>
      agent.subscribe({ ...handlers, onRunFinishedEvent: () => refreshRecord() }),
    )
    const drafterSub = drafterAgent.subscribe({
      ...handlers,
      // The human gate arrives as a run finishing with an interrupt outcome.
      onRunFinishedEvent: (params: any) => {
        refreshRecord()
        // The report is written before the graph reaches its human gate, so
        // this fires with an interrupt outcome on the ordinary path. Take the
        // reviewer to the document either way — it is something to read, not
        // another entry to scroll back to in the transcript. A rerun is the
        // exception: no report was issued, the case goes back for analysis.
        if (drafterAgent.state?.draft_report && !pendingRerun.current) setTab('findings')
        if ('interrupts' in params && params.interrupts.length > 0) {
          const intr = params.interrupts[0] as { id: string; metadata?: { langgraph?: { raw?: GateContext } } }
          const context = intr.metadata?.langgraph?.raw
          if (context) setGate({ id: intr.id, context })
        } else {
          setGate(null)
          const directive = pendingRerun.current
          if (directive) {
            // The rerun handoff: the drafting run ended with the directive on
            // the record; a directed triage pass carries it out.
            pendingRerun.current = null
            feed.reset()
            resetAgent(triageAgent, { case_id: caseId, reviewer_directive: directive })
            triageAgent.runAgent()
            toast(`Directed pass started — ${directive.target_agents.join(', ')}`)
          }
        }
      },
    })
    return () => {
      subs.forEach((s) => s.unsubscribe())
      drafterSub.unsubscribe()
    }
    // feed handlers are stable useCallbacks; agents are registry singletons.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [triageAgent, sessionAgent, drafterAgent, caseId])

  const anyRunning = triage.running || session.running || drafter.running

  // The orchestrator can route "run the review" / "draft the report" — the
  // decision is its; execution is ours (it routes, code runs).
  const sessionRuns = useRef(0)
  const handledSessionRuns = useRef(0)
  useEffect(() => {
    if (session.running) {
      sessionRuns.current += 1
      return
    }
    if (handledSessionRuns.current === sessionRuns.current) return
    handledSessionRuns.current = sessionRuns.current
    setPendingQuestion(null)
    // The routing turn is over — the hub settles green even if a step
    // event was lost across the SSE relay.
    feed.recordNodeEvent('orchestrator', 'complete')
    const intent = (session.state.orchestrator_decision as { intent?: string } | undefined)?.intent
    if (intent === 'draft_report') handleDraft()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.running])

  const handleRun = () => {
    feed.reset()
    activeWorkers.current.clear()
    setGate(null)
    resetAgent(triageAgent, {
      case_id: caseId,
      first_pass: true,
      // The rules-only switch was a developer affordance in a supervisor's
      // console. A review without its judged rules is not a review.
      deterministic_only: false,
      ...(Object.keys(promptOverrides).length ? { prompt_overrides: promptOverrides } : {}),
    })
    triageAgent.runAgent()
    if (Object.keys(promptOverrides).length) {
      setPromptOverrides({}) // per-run: consumed by this run, next starts default
      toast('Running with edited instructions — recorded on this run only.')
    }
  }

  const handleDraft = () => {
    feed.reset()
    activeWorkers.current.clear()
    setGate(null)
    resetAgent(drafterAgent, { case_id: caseId })
    drafterAgent.runAgent()
  }

  const handleSend = (text: string) => {
    feed.reset()
    activeWorkers.current.clear()
    setPendingQuestion(text)
    resetAgent(sessionAgent, { case_id: caseId, officer_message: text, officer })
    sessionAgent.runAgent()
  }

  // A genuinely clean slate. Hiding the transcript was never enough: every
  // run after the first is seeded from the case record, so a re-run inherited
  // the previous one's assessments and its observations piled up without
  // bound (measured: 0 -> 169 over twenty runs). This asks the server to
  // clear the review history too, so the next run starts from the submission
  // alone. Nothing is deleted — the ledger is append-only, the reset itself
  // is an event, and the timeline tab still shows all of it.
  const handleNewChat = async () => {
    for (const agent of [triageAgent, sessionAgent, drafterAgent]) {
      try { (agent as unknown as { abortRun?: () => void }).abortRun?.() } catch { /* nothing running */ }
    }
    feed.reset()
    activeWorkers.current.clear()
    setProgress({})
    setGate(null)
    setPendingQuestion(null)
    setFocusedStep(null)
    pendingRerun.current = null
    resetAgent(triageAgent, { case_id: caseId })
    resetAgent(sessionAgent, { case_id: caseId })
    resetAgent(drafterAgent, { case_id: caseId })
    try {
      await resetReviewHistory(caseId)
      refreshRecord()
      toast('Cleared — the next run starts fresh. Every event stays on the timeline.')
    } catch (e) {
      // The view is already clear; say plainly that the record is not, so
      // nobody reads a stale score as a fresh one.
      toast(`View cleared, but the record was not: ${e instanceof Error ? e.message : 'reset failed'}`)
    }
  }
  // The server decides what the case room sees, so the transcript is simply
  // whatever it returned. A cleared case comes back with its submission and
  // nothing else — the first-run state, not a hidden one.
  const visibleLedger = ledger
  const hiddenCount = 0
  const showEarlier = () => {}

  const handleDecision = (decision: GateSubmission) => {
    if (!gate) return
    setGate(null)
    if (decision.action === 'rerun' && decision.directive) {
      pendingRerun.current = decision.directive
      // Sending it back starts a directed pass. That work is watchable and the
      // decision page is not, so hand the reviewer back to the room to see it.
      setTab('room')
    }
    // Resume on the SAME thread, but make sure the case travels with it:
    // the state streamed back after the gate does not always carry case_id,
    // and a resume without it is indistinguishable from a brand-new run.
    drafterAgent.setState({ ...(drafterAgent.state ?? EMPTY_AGENT_STATE), case_id: caseId })
    drafterAgent.runAgent({ resume: [{ interruptId: gate.id, status: 'resolved', payload: decision }] })
  }

  const handleClose = () => {
    if (!closeOfficer.trim()) return
    closeCase(caseId, closeOfficer.trim())
      .then(() => {
        setCloseOpen(false)
        refreshRecord()
        toast(`Case closed — no action · by ${closeOfficer.trim()}`)
      })
      .catch((err) => toast.error(String(err)))
  }

  // The receipt: issuing a supervisory report is the gravest act in the
  // product — an explicit success moment when the record flips to issued.
  const prevStatus = useRef<string | undefined>(undefined)
  useEffect(() => {
    const status = record?.status
    if (!status || status === prevStatus.current) return
    if (prevStatus.current !== undefined && status === 'issued') {
      const last = record?.decisions.at(-1)
      toast.success(`Supervisory report issued — ${caseSummary.firm}`, {
        description: last ? `Signed by ${last.reviewer} · ${caseId}` : caseId,
      })
    }
    prevStatus.current = status
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [record?.status])

  // Map statuses: live feed, settled to done once nothing runs; the gate
  // holds its node in "awaiting" — the one state that is neither working
  // nor complete.
  const displayNodeStatus = useMemo<Record<string, NodeStatus>>(() => {
    const base: Record<string, NodeStatus> = anyRunning
      ? { ...feed.nodeStatus }
      : Object.fromEntries(
          Object.entries(feed.nodeStatus).map(([id, status]) => [id, status === 'active' ? ('done' as const) : status]),
        )
    if (session.running) base['orchestrator'] = 'active'
    // The supervisor is a real participant in the loop, not a label: light it
    // whenever the turn is actually theirs — before anything has been asked,
    // between passes, and at the gate — and settle it while the machine works.
    base['supervisor'] = anyRunning ? 'done' : 'awaiting'
    if (gate) {
      base['human_gate'] = 'awaiting'
      base['supervisor'] = 'awaiting'
    }
    return base
  }, [feed.nodeStatus, anyRunning, session.running, gate])

  // Settled specialists show what they returned. Memoised so the map gets
  // the same object between changes — it updates node data in place.
  const mapNodeStatus = useMemo<Record<string, NodeStatus>>(() => Object.fromEntries(Object.entries(displayNodeStatus).map(([name, status]) => {
    if (status !== 'done' || !progress[name]) return [name, status]
    const p = progress[name]
    const verdicts = (ledger ?? []).filter(e => e.run_id === p.run_id && e.event_type === 'assessment_recorded' && e.payload.agent === name).map(e => String(e.payload.verdict))
    // breach or concern → findings; only open judgements → unresolved; else clean
    return [name, verdicts.some(v => v === 'breach' || v === 'concern') ? 'findings' : verdicts.includes('inconclusive') ? 'unresolved' : 'clean']
  })), [displayNodeStatus, progress, ledger])

  const openSpecialistTurn = (name: string) => {
    const last = [...(ledger ?? [])].reverse().find((e) => e.event_type === 'dispatch_recorded' && e.payload.target === name)
    if (!last?.run_id) { toast('This specialist has no turn on this dossier yet.'); return }
    setFocusedStep(null)
    requestAnimationFrame(() => setFocusedStep(turnAnchor(name, last.run_id!)))
  }

  const liveLabel = triage.running
    ? 'Full review pass running'
    : session.running
      ? 'Orchestrator working'
      : drafter.running
        ? 'Drafting the report'
        : null

  // The orchestrator's message to the officer, as soon as it has decided —
  // for a question and for a first pass alike; the ledger's copy replaces it.
  const pendingReply = (() => {
    for (const a of [session, triage]) {
      if (a.running && typeof a.state.orchestrator_reply === 'string' && a.state.orchestrator_reply) return a.state.orchestrator_reply
    }
    return null
  })()

  const view = useMemo(() => {
    if (triage.running) {
      return {
        findings: triage.state.findings ?? [],
        failure_occurrences: triage.state.failure_occurrences ?? [],
        observations: triage.state.observations ?? [],
        correlations: triage.state.correlations ?? [],
        dispatch_plan: triage.state.dispatch_plan,
        escalation_round: triage.state.escalation_round,
        risk_score: triage.state.risk_score,
      }
    }
    const lastTriage = record?.runs.filter((r) => r.kind === 'triage').at(-1)
    return {
      findings: record?.findings ?? [],
      failure_occurrences: record?.failure_occurrences ?? [],
      observations: record?.observations ?? [],
      correlations: record?.correlations ?? [],
      dispatch_plan: lastTriage?.plan ?? undefined,
      escalation_round: record?.escalation_rounds,
      risk_score: record?.risk_score ?? undefined,
    }
  }, [triage.running, triage.state, record])

  const headerMeta = detail
    ? [(detail.raw.firm.sector ?? '').replace(/_/g, ' '), detail.raw.firm.hq, `${detail.raw.transaction_history.length} transactions on record`]
        .filter(Boolean)
        .join(' · ')
    : null

  const report = record?.draft_report ?? null
  const hasTriage = (record?.runs ?? []).some((r) => r.kind === 'triage')
  const closable = !!record && !['issued', 'closed_rejected', 'closed_no_action'].includes(record.status)
  const findingsBadge = view.findings.length + view.observations.length

  return (
    <Tabs value={tab} onValueChange={setTab} className="flex h-full min-h-0 flex-col gap-0">
      <header className="shrink-0 border-b bg-card px-5 pt-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <Button variant="ghost" size="icon" onClick={onBack} aria-label="Back to case queue" className="-ml-2">
              <ArrowLeft />
            </Button>
            <div>
              <h2 className="font-heading text-base font-semibold leading-tight">{caseSummary.firm}</h2>
              <p className="font-mono text-xs text-muted-foreground">
                {caseId}
                {headerMeta && <span className="font-sans"> · {headerMeta}</span>}
              </p>
            </div>
          </div>
        </div>
        <TabsList className="mt-2 h-auto gap-1 bg-transparent p-0">
          {[
            { value: 'room', icon: MessageSquareText, label: 'Case room', badge: 0 },
            { value: 'findings', icon: ListChecks, label: 'Findings', badge: findingsBadge },
            { value: 'runs', icon: FolderOpen, label: 'Submission', badge: dossier?.dossier.submission_context.runs_submitted ?? 0 },
            { value: 'decision', icon: BadgeCheck, label: 'Decision', badge: gate ? 1 : 0 },
            { value: 'timeline', icon: History, label: 'Timeline', badge: 0 },
          ].map(({ value, icon: Icon, label, badge }) => (
            <TabsTrigger
              key={value}
              value={value}
              className="gap-1.5 rounded-none border-0 border-b-2 border-transparent px-3 pb-2.5 pt-1.5 shadow-none data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none"
            >
              <Icon className="size-4" />
              {label}
              {badge > 0 && (
                <span className="rounded-full bg-muted px-1.5 font-mono text-[10px] text-muted-foreground">{badge}</span>
              )}
            </TabsTrigger>
          ))}
        </TabsList>
      </header>

      {/* The case room: the supervision map on the left, always visible —
          the whole loop, lanes lighting as runs move — and the
          conversation as the working surface. Findings live in their own
          tab; the transcript already carries them in context. */}
      <TabsContent value="room" className="min-h-0 flex-1">
        <div className="flex h-full min-h-0 flex-col">
          <div className="flex shrink-0 items-center gap-2 border-b bg-card/60 px-4 py-1.5 text-xs text-muted-foreground">
            <MessageSquareText className="size-3.5" />
            {liveLabel ? (
              <span className="inline-flex items-center gap-1.5 text-blue-700 dark:text-blue-400">
                <span className="size-1.5 animate-pulse rounded-full bg-blue-500" />
                {liveLabel}
              </span>
            ) : <span>idle</span>}
            <span className="ml-auto flex items-center gap-1">
              <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={handleNewChat} disabled={anyRunning && false}>
                <MessageSquarePlus data-icon="inline-start" />
                Clear
              </Button>
              <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setMapOpen((v) => !v)} aria-pressed={mapOpen}>
                {mapOpen ? <PanelRightClose data-icon="inline-start" /> : <PanelRightOpen data-icon="inline-start" />}
                Map
              </Button>
            </span>
          </div>
          <div className="flex min-h-0 flex-1">
            <div className="min-h-0 min-w-0 flex-1">
              <CaseChat
                events={visibleLedger}
                factsSource={ledger}
                hiddenCount={hiddenCount}
                onShowEarlier={showEarlier}
                live={feed.events}
                running={triage.running ? 'triage' : session.running ? 'session' : drafter.running ? 'drafting' : null}
                progress={progress}
                pendingQuestion={pendingQuestion}
                pendingReply={pendingReply}
                gate={gate}
                officer={officer}
                focusedStep={focusedStep}
                onOpenRun={setSelectedRun}
                onDecision={() => setTab('decision')}
                onOpenReport={() => setTab('findings')}
                onSend={handleSend}
                onRun={handleRun}
                onDraft={handleDraft}
                onCloseCase={() => setCloseOpen(true)}
                busy={anyRunning}
                hasTriage={hasTriage}
                closable={closable}
              />
            </div>
            {mapOpen && (
              <aside className="hidden w-[400px] shrink-0 border-l bg-card/40 lg:block xl:w-[470px] 2xl:w-[560px]">
                <div className="flex items-center gap-2 border-b px-4 py-2.5 text-xs font-semibold text-muted-foreground">
                  <Waypoints className="size-3.5" />
                  Supervision loop
                  <span className={cn('ml-auto font-normal', !liveLabel && 'text-muted-foreground/60')}>{liveLabel ?? 'idle'}</span>
                  {/* The rail is a glance view — nineteen boxes in 400px can
                      only ever be small. This opens the same map at a size a
                      person can actually read. */}
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    aria-label="Open the supervision map full screen"
                    title="Expand map"
                    onClick={() => setMapExpanded(true)}
                  >
                    <Expand />
                  </Button>
                </div>
                <div className="h-[calc(100%-2.4rem)]">
                  {map ? (
                    <SupervisionMap map={map} nodeStatus={mapNodeStatus} nodeStartSeq={feed.nodeStartSeq} onNodeClick={openSpecialistTurn} />
                  ) : (
                    <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Loading map…</div>
                  )}
                </div>
              </aside>
            )}
            <Dialog open={mapExpanded} onOpenChange={setMapExpanded}>
              <DialogContent className="flex h-[92vh] w-[96vw] max-w-[1500px] flex-col gap-0 p-0 sm:max-w-[1500px]">
                <DialogHeader className="flex-row items-center gap-2 border-b px-4 py-3 text-left">
                  <Waypoints className="size-4 text-muted-foreground" />
                  <DialogTitle className="font-heading text-sm font-semibold">Supervision loop</DialogTitle>
                  <span className={cn('text-xs', !liveLabel && 'text-muted-foreground/60')}>{liveLabel ?? 'idle'}</span>
                </DialogHeader>
                <div className="min-h-0 flex-1">
                  {map && (
                    <SupervisionMap
                      map={map}
                      nodeStatus={mapNodeStatus}
                      nodeStartSeq={feed.nodeStartSeq}
                      onNodeClick={(name) => { setMapExpanded(false); openSpecialistTurn(name) }}
                    />
                  )}
                </div>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </TabsContent>

      {loadError && <p role="alert" className="px-5 py-2 text-xs text-destructive">{loadError}</p>}
      <TabsContent value="runs" className="min-h-0 flex-1">
        <ExecutionRuns caseId={caseId} dossier={dossier} refreshKey={refreshKey} onOpenRun={setSelectedRun} />
      </TabsContent>
      {/* The one place a decision is made. The paused human gate renders at the
          top of this page — not in the case room, which only announces it —
          so the reviewer signs in one place instead of two. */}
      <TabsContent value="decision" className="min-h-0 flex-1">
        <AuthorisationPanel
          caseId={caseId}
          dossier={dossier}
          officer={officer}
          busy={anyRunning}
          onSaved={refreshRecord}
          onOpenRun={setSelectedRun}
          gate={gate}
          gateRisk={drafter.state.risk_score ?? record?.risk_score ?? null}
          findingsCount={view.findings.length}
          onGateDecide={handleDecision}
        />
      </TabsContent>
      <ExecutionInspector caseId={caseId} runId={selectedRun} onClose={() => setSelectedRun(null)} dossier={dossier} onOpenRun={setSelectedRun} onInvestigate={run => { setSelectedRun(null); setTab('room'); handleSend(`Review ${run} in depth. Re-dispatch only the relevant specialists, scoped to this execution, and explain its findings.`) }} />
      {/* One page, one scroll: the drafted document first, then the record it
          cites. The two used to be separate scrollers stacked on each other,
          which read as two unrelated panels and hid whichever one you were
          not in. */}
      <TabsContent value="findings" className="min-h-0 flex-1">
        <div className="h-full overflow-y-auto">
          <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-5">
            {report && record && (
              <>
                {/* Two different records can end a draft, and `signed` used to read
                    only the first: `record.decisions` are the drafting gate's
                    reviewer decisions, while the Decision tab writes an
                    `authorisation_decided` event that lands in `dossier.decisions`.
                    Signing a disposition there left the report still captioned
                    "draft" and still offering a Sign button. */}
                <ReportCard
                  report={report}
                  firm={record.firm}
                  findings={record.findings}
                  signed={(record.decisions ?? []).length > 0 || (dossier?.decisions ?? []).length > 0}
                  disposition={dossier?.decisions?.at(-1)?.disposition}
                  onSign={() => setTab('decision')}
                  onOpenRun={setSelectedRun}
                />
                {/* Names the boundary the draft depends on: everything below is
                    recorded by the specialists and scored deterministically,
                    whether or not a report was ever drafted from it. */}
                <div className="border-t pt-5">
                  <h2 className="font-heading text-sm font-semibold">The record the draft cites</h2>
                  <p className="mt-0.5 text-[12px] leading-5 text-muted-foreground">
                    Findings, catalogue failures and the risk score, established by the specialists and scored by
                    rule — independent of the prose above, and authoritative if the two ever disagree.
                  </p>
                </div>
              </>
            )}
            <ResultsPanel view={view} answers={record?.answers ?? []} />
          </div>
        </div>
      </TabsContent>


      <TabsContent value="timeline" className="min-h-0 flex-1">
        <CaseTimeline caseId={caseId} refreshKey={refreshKey} />
      </TabsContent>

      <Dialog open={closeOpen} onOpenChange={setCloseOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Close — no action</DialogTitle>
            <DialogDescription>
              A clean case's exit is a named decision on the record, not a drafted document. Closing{' '}
              <span className="font-mono text-[13px]">{caseId}</span> is appended to the ledger under your name.
            </DialogDescription>
          </DialogHeader>
          <Input
            placeholder="Your name — recorded with the decision"
            value={closeOfficer}
            onChange={(e) => setCloseOfficer(e.target.value)}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCloseOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleClose} disabled={!closeOfficer.trim()}>
              <BadgeCheck data-icon="inline-start" />
              Close case
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Tabs>
  )
}

export function CaseReview({ caseSummary, onBack }: { caseSummary: CaseSummary; onBack: () => void }) {
  return (
    <div className="h-full min-h-0">
      {/* Remounts (and resets all three agents) whenever the case changes. */}
      <CaseReviewInner key={caseSummary.case_id} caseSummary={caseSummary} onBack={onBack} />
    </div>
  )
}
