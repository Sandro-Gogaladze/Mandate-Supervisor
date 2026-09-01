import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useCoAgent } from '@copilotkit/react-core'
// useAgent isn't re-exported from the v1-compat root path (only used
// internally there) but resolves the same shared registry instance either
// way — see the agents below.
import { useAgent } from '@copilotkit/react-core/v2'
import { toast } from 'sonner'
import {
  ArrowLeft,
  BadgeCheck,
  FolderOpen,
  History,
  ListChecks,
  MessageSquareText,
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
import { closeCase, getCase, getFullMap, getLedgerEvents } from '@/lib/api'
import type {
  CaseDetail,
  CaseRecord,
  CaseSummary,
  FullMap,
  GateContext,
  LedgerEvent,
  ReviewerDirective,
} from '@/lib/types'
import { EMPTY_AGENT_STATE, type SupervisionAgentState } from '@/lib/agent-state'
import { usePipelineFeed } from '@/hooks/usePipelineFeed'
import { SupervisionMap, type NodeStatus } from '@/components/SupervisionMap'
import { Conversation } from '@/components/Conversation'
import { ResultsPanel } from '@/components/ResultsPanel'
import { CaseFilePanel } from '@/components/CaseFilePanel'
import { CaseTimeline } from '@/components/CaseTimeline'
import { PromptOverridesDialog } from '@/components/PromptOverridesDialog'
import type { GateSubmission } from '@/components/ReviewGate'
import { cn } from '@/lib/utils'

const TRIAGE_AGENT = 'mandate_supervisor'
const SESSION_AGENT = 'supervisor_session'
const DRAFTER_AGENT = 'report_drafter'

// The map shows the supervisor's model of the loop; graph-internal
// plumbing steps fold onto the nearest visible node so live lighting
// still tells the truth: ingest is dispatch prep, an escalation round is
// a re-dispatch, the critic checks the output pool, the score is the
// result returning to the orchestrator, load_record is drafting prep.
const STEP_ALIAS: Record<string, string | null> = {
  orchestrate: 'orchestrator',
  load_context: 'orchestrator',
  record: 'orchestrator',
  ingest: 'dispatch',
  bump_round: 'dispatch',
  escalate_check: 'findings',
  critic: 'findings',
  risk_score: 'orchestrator',
  load_record: 'draft_report',
}

function CaseReviewInner({ caseSummary, onBack }: { caseSummary: CaseSummary; onBack: () => void }) {
  const caseId = caseSummary.case_id
  const [map, setMap] = useState<FullMap | null>(null)
  const [detail, setDetail] = useState<CaseDetail | null>(null)
  const [record, setRecord] = useState<CaseRecord | null>(null)
  const [ledger, setLedger] = useState<LedgerEvent[] | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [gate, setGate] = useState<{ id: string; context: GateContext } | null>(null)
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null)
  const [promptOverrides, setPromptOverrides] = useState<Record<string, string>>({})
  const [officer, setOfficer] = useState('Case officer')
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
      .catch(() => undefined)
    getLedgerEvents(caseId)
      .then(setLedger)
      .catch(() => undefined)
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

  const recordStep = useCallback(
    (stepName: string, status: 'inProgress' | 'complete') => {
      const target = stepName in STEP_ALIAS ? STEP_ALIAS[stepName] : stepName
      if (target) feed.recordNodeEvent(target, status)
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  )

  // In an investigation run the orchestrator dispatches a worker directly —
  // there is no `dispatch` graph node to stream. Lighting audit finding:
  // the worker lit with no lit path into it. When the session stream starts
  // a worker step, synthesize the dispatch hop first (start-before-worker
  // keeps the edge-traversal ordering correct); a reply-only turn never
  // touches it, so Dispatch stays dark when nothing was dispatched.
  const WORKER_STEPS = useMemo(() => new Set(['mandate', 'kya', 'log', 'drift', 'investigator']), [])
  const recordSessionStep = useCallback(
    (stepName: string, status: 'inProgress' | 'complete') => {
      if (status === 'inProgress' && WORKER_STEPS.has(stepName)) {
        feed.recordNodeEvent('dispatch', 'inProgress')
        feed.recordNodeEvent('dispatch', 'complete')
      }
      recordStep(stepName, status)
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  )

  // One feed across all three agents — the conversation's live block and
  // the supervision map read the same stream.
  useEffect(() => {
    const handlers = {
      onStepStartedEvent: ({ event }: any) => recordStep(event.stepName, 'inProgress'),
      onStepFinishedEvent: ({ event }: any) => recordStep(event.stepName, 'complete'),
      onToolCallStartEvent: ({ event }: any) => feed.recordToolEvent(event.toolCallName, 'inProgress', {}),
      onToolCallArgsEvent: ({ toolCallName, partialToolCallArgs }: any) =>
        feed.recordToolEvent(toolCallName, 'executing', partialToolCallArgs),
      onToolCallEndEvent: ({ toolCallName, toolCallArgs }: any) =>
        feed.recordToolEvent(toolCallName, 'complete', toolCallArgs),
    }
    const triageSub = triageAgent.subscribe({ ...handlers, onRunFinishedEvent: () => refreshRecord() })
    const sessionSub = sessionAgent.subscribe({
      ...handlers,
      onStepStartedEvent: ({ event }: any) => recordSessionStep(event.stepName, 'inProgress'),
      onStepFinishedEvent: ({ event }: any) => recordSessionStep(event.stepName, 'complete'),
      onRunFinishedEvent: () => refreshRecord(),
    })
    const subs = [triageSub, sessionSub]
    const drafterSub = drafterAgent.subscribe({
      ...handlers,
      // The human gate arrives as a run finishing with an interrupt outcome.
      onRunFinishedEvent: (params: any) => {
        refreshRecord()
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
    if (intent === 'run_triage') handleRun()
    else if (intent === 'draft_report') handleDraft()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.running])

  const handleRun = () => {
    feed.reset()
    setGate(null)
    resetAgent(triageAgent, {
      case_id: caseId,
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
    setGate(null)
    resetAgent(drafterAgent, { case_id: caseId })
    drafterAgent.runAgent()
  }

  const handleSend = (text: string) => {
    feed.reset()
    setPendingQuestion(text)
    resetAgent(sessionAgent, { case_id: caseId, officer_message: text, officer })
    sessionAgent.runAgent()
  }

  const handleDecision = (decision: GateSubmission) => {
    if (!gate) return
    setGate(null)
    if (decision.action === 'rerun' && decision.directive) {
      pendingRerun.current = decision.directive
    }
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
    if (gate) {
      base['human_gate'] = 'awaiting'
      base['supervisor'] = 'awaiting'
    }
    return base
  }, [feed.nodeStatus, anyRunning, session.running, gate])

  const liveLabel = triage.running
    ? 'Full review pass running'
    : session.running
      ? 'Orchestrator working'
      : drafter.running
        ? 'Drafting the report'
        : null

  const pendingReply =
    session.running && typeof session.state.orchestrator_reply === 'string' && session.state.orchestrator_reply
      ? session.state.orchestrator_reply
      : null

  const view = useMemo(() => {
    if (triage.running) {
      return {
        findings: triage.state.findings ?? [],
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
      observations: record?.observations ?? [],
      correlations: record?.correlations ?? [],
      dispatch_plan: lastTriage?.plan ?? undefined,
      escalation_round: record?.escalation_rounds,
      risk_score: record?.risk_score ?? undefined,
    }
  }, [triage.running, triage.state, record])

  const headerMeta = detail
    ? [detail.raw.firm.sector.replace(/_/g, ' '), detail.raw.firm.hq, `${detail.raw.transaction_history.length} transactions on record`]
        .filter(Boolean)
        .join(' · ')
    : null

  const hasTriage = (record?.runs ?? []).some((r) => r.kind === 'triage')
  const closable = !!record && !['issued', 'closed_rejected', 'closed_no_action'].includes(record.status)
  const findingsBadge = view.findings.length + view.observations.length

  return (
    <Tabs defaultValue="room" className="flex h-full min-h-0 flex-col gap-0">
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
          <PromptOverridesDialog overrides={promptOverrides} onChange={setPromptOverrides} />
        </div>
        <TabsList className="mt-2 h-auto gap-1 bg-transparent p-0">
          {[
            { value: 'room', icon: MessageSquareText, label: 'Case room', badge: 0 },
            { value: 'findings', icon: ListChecks, label: 'Findings', badge: findingsBadge },
            { value: 'file', icon: FolderOpen, label: 'Case file', badge: 0 },
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
        <div className="flex h-full min-h-0">
          <aside className="hidden w-[380px] shrink-0 border-r bg-card/40 lg:block xl:w-[430px]">
            <div className="flex items-center gap-2 border-b px-4 py-2.5 text-xs font-semibold text-muted-foreground">
              <Waypoints className="size-3.5" />
              Supervision loop
              {anyRunning && (
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-500 opacity-75" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-amber-500" />
                </span>
              )}
              <span className={cn('ml-auto font-normal', !liveLabel && 'text-muted-foreground/60')}>
                {liveLabel ?? 'idle'}
              </span>
            </div>
            <div className="h-[calc(100%-2.4rem)]">
              {map ? (
                <SupervisionMap map={map} nodeStatus={displayNodeStatus} nodeStartSeq={feed.nodeStartSeq} />
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Loading map…</div>
              )}
            </div>
          </aside>

          <div className="min-h-0 min-w-0 flex-1">
            <Conversation
              events={ledger}
              liveEvents={feed.events}
              liveLabel={liveLabel}
              pendingQuestion={pendingQuestion}
              pendingReply={pendingReply}
              gate={gate}
              gateRisk={drafter.state.risk_score ?? record?.risk_score ?? null}
              findingsCount={view.findings.length}
              officer={officer}
              onOfficerChange={setOfficer}
              onDecide={handleDecision}
              onSend={handleSend}
              onRun={handleRun}
              onDraft={handleDraft}
              onCloseCase={() => setCloseOpen(true)}
              busy={anyRunning}
              hasTriage={hasTriage}
              closable={closable}
            />
          </div>
        </div>
      </TabsContent>

      <TabsContent value="findings" className="min-h-0 flex-1">
        <div className="mx-auto h-full max-w-3xl">
          <ResultsPanel view={view} answers={record?.answers ?? []} />
        </div>
      </TabsContent>

      <TabsContent value="file" className="min-h-0 flex-1">
        {detail ? (
          <CaseFilePanel raw={detail.raw} label={caseSummary.label} />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Loading case file…</div>
        )}
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
