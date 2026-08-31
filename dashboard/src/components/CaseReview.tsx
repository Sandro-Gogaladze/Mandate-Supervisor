import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useCoAgent } from '@copilotkit/react-core'
// useAgent isn't re-exported from the v1-compat root path (only used
// internally there) but resolves the same shared registry instance either
// way — see the comment above the agents below.
import { useAgent } from '@copilotkit/react-core/v2'
import { toast } from 'sonner'
import {
  ArrowLeft,
  BadgeCheck,
  FileText,
  FolderOpen,
  History,
  ListChecks,
  Loader2,
  MessageCircleQuestion,
  MonitorPlay,
  Play,
  Radio,
  UserRoundCheck,
  Waypoints,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
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
import { closeCase, getCase, getGraphStructure } from '@/lib/api'
import type { CaseDetail, CaseRecord, CaseSummary, GraphStructure, GateContext, ReviewerDirective } from '@/lib/types'
import { EMPTY_AGENT_STATE, type SupervisionAgentState } from '@/lib/agent-state'
import { usePipelineFeed } from '@/hooks/usePipelineFeed'
import { PipelineGraph } from '@/components/PipelineGraph'
import { StepFeed } from '@/components/StepFeed'
import { ResultsPanel } from '@/components/ResultsPanel'
import { CaseFilePanel } from '@/components/CaseFilePanel'
import { CaseTimeline } from '@/components/CaseTimeline'
import { QuestionBox, type SessionExchange } from '@/components/QuestionBox'
import { PromptOverridesDialog } from '@/components/PromptOverridesDialog'
import { ReportPanel, reportStatus } from '@/components/ReportPanel'
import { ReviewGate, type GateSubmission } from '@/components/ReviewGate'
import { cn } from '@/lib/utils'

const TRIAGE_AGENT = 'mandate_supervisor'
const SESSION_AGENT = 'supervisor_session'
const DRAFTER_AGENT = 'report_drafter'

function PanelHeader({
  icon: Icon,
  title,
  meta,
  live,
  children,
}: {
  icon: typeof Waypoints
  title: string
  meta?: string
  live?: boolean
  children?: React.ReactNode
}) {
  return (
    <div className="flex items-center justify-between border-b px-4 py-3">
      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Icon className="size-4 text-muted-foreground" />
        {title}
      </div>
      <div className="flex items-center gap-2">
        {live && (
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-500 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-500" />
          </span>
        )}
        {meta && <span className="text-xs font-medium text-muted-foreground">{meta}</span>}
        {children}
      </div>
    </div>
  )
}

function CaseReviewInner({ caseSummary, onBack }: { caseSummary: CaseSummary; onBack: () => void }) {
  const caseId = caseSummary.case_id
  const [graph, setGraph] = useState<GraphStructure | null>(null)
  const [detail, setDetail] = useState<CaseDetail | null>(null)
  const [record, setRecord] = useState<CaseRecord | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [gate, setGate] = useState<{ id: string; context: GateContext } | null>(null)
  const [exchanges, setExchanges] = useState<SessionExchange[]>([])
  const [promptOverrides, setPromptOverrides] = useState<Record<string, string>>({})
  const [closeOpen, setCloseOpen] = useState(false)
  const [closeOfficer, setCloseOfficer] = useState('')
  const gateRef = useRef<HTMLDivElement>(null)
  const pendingRerun = useRef<ReviewerDirective | null>(null)
  const feed = usePipelineFeed()

  // The ledger projection is the durable truth; live agent state overlays it
  // only while a run is streaming.
  const refreshRecord = useCallback(() => {
    getCase(caseId)
      .then((d) => {
        setDetail(d)
        setRecord(d.record)
        setRefreshKey((k) => k + 1)
      })
      .catch(() => undefined)
  }, [caseId])

  useEffect(() => {
    getGraphStructure().then(setGraph).catch(() => setGraph(null))
  }, [])
  useEffect(() => {
    refreshRecord()
  }, [refreshRecord])

  // Three runs, three agents (architecture-v2 §14): triage streams the
  // multi-agent pass, session carries the orchestrator conversation,
  // drafter holds the human gate. useCoAgent for state/running; useAgent
  // for the correctly-bound runAgent/subscribe (the v1-compat run() drops
  // its `this` binding — confirmed live in phase 10).
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

  const resetAgent = useCallback(
    (agent: typeof triageAgent, state: SupervisionAgentState) => {
      // Fresh thread per run: the registry agents are shared singletons, and
      // running on a stale thread would merge reducer channels across runs.
      agent.threadId = crypto.randomUUID()
      agent.setMessages([])
      agent.setState({ ...EMPTY_AGENT_STATE, ...state })
    },
    [],
  )

  useEffect(() => {
    resetAgent(triageAgent, { case_id: caseId })
    resetAgent(sessionAgent, { case_id: caseId })
    resetAgent(drafterAgent, { case_id: caseId })
    setGate(null)
    setExchanges([])
    // Mount ≡ case change (keyed by case_id).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId])

  // One feed across all three agents — node/tool events land in the same
  // step list and drive the same graph highlighting.
  useEffect(() => {
    const subscriptions = [triageAgent, sessionAgent].map((agent) =>
      agent.subscribe({
        onStepStartedEvent: ({ event }) => feed.recordNodeEvent(event.stepName, 'inProgress'),
        onStepFinishedEvent: ({ event }) => feed.recordNodeEvent(event.stepName, 'complete'),
        onToolCallStartEvent: ({ event }) => feed.recordToolEvent(event.toolCallName, 'inProgress', {}),
        onToolCallArgsEvent: ({ toolCallName, partialToolCallArgs }) =>
          feed.recordToolEvent(toolCallName, 'executing', partialToolCallArgs),
        onToolCallEndEvent: ({ toolCallName, toolCallArgs }) => feed.recordToolEvent(toolCallName, 'complete', toolCallArgs),
        onRunFinishedEvent: () => refreshRecord(),
      }),
    )
    const drafterSub = drafterAgent.subscribe({
      onStepStartedEvent: ({ event }) => feed.recordNodeEvent(event.stepName, 'inProgress'),
      onStepFinishedEvent: ({ event }) => feed.recordNodeEvent(event.stepName, 'complete'),
      onToolCallStartEvent: ({ event }) => feed.recordToolEvent(event.toolCallName, 'inProgress', {}),
      onToolCallArgsEvent: ({ toolCallName, partialToolCallArgs }) =>
        feed.recordToolEvent(toolCallName, 'executing', partialToolCallArgs),
      onToolCallEndEvent: ({ toolCallName, toolCallArgs }) => feed.recordToolEvent(toolCallName, 'complete', toolCallArgs),
      // The human gate arrives as a run finishing with an interrupt outcome
      // (emit_interrupt_outcome=True on the drafter).
      onRunFinishedEvent: (params) => {
        refreshRecord()
        if ('interrupts' in params && params.interrupts.length > 0) {
          const intr = params.interrupts[0] as { id: string; metadata?: { langgraph?: { raw?: GateContext } } }
          const context = intr.metadata?.langgraph?.raw
          if (context) setGate({ id: intr.id, context })
        } else {
          setGate(null)
          const directive = pendingRerun.current
          if (directive) {
            // The rerun handoff: the drafting run ended with the directive
            // on the record; a directed triage pass carries it out.
            pendingRerun.current = null
            resetAgent(triageAgent, { case_id: caseId, reviewer_directive: directive })
            triageAgent.runAgent()
            toast(`Directed pass started — ${directive.target_agents.join(', ')}`)
          }
        }
      },
    })
    return () => {
      subscriptions.forEach((s) => s.unsubscribe())
      drafterSub.unsubscribe()
    }
    // feed handlers are stable useCallbacks; agents are registry singletons.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [triageAgent, sessionAgent, drafterAgent, caseId])

  // The orchestrator's reply streams into session state; patch it onto the
  // newest in-flight exchange.
  useEffect(() => {
    const reply = session.state.orchestrator_reply
    if (!reply) return
    setExchanges((prev) => {
      const idx = prev.findLastIndex((e) => e.reply === null)
      if (idx === -1) return prev
      const next = [...prev]
      next[idx] = { ...next[idx], reply }
      return next
    })
  }, [session.state.orchestrator_reply])

  const anyRunning = triage.running || session.running || drafter.running

  const displayNodeStatus = useMemo(() => {
    // Once nothing is running, nothing can still legitimately be active —
    // a started-but-unresolved node reads as done, not a stale spinner.
    if (anyRunning) return feed.nodeStatus
    return Object.fromEntries(
      Object.entries(feed.nodeStatus).map(([id, status]) => [id, status === 'active' ? ('done' as const) : status]),
    )
  }, [feed.nodeStatus, anyRunning])

  // The view model: live triage state while streaming, the projected record
  // otherwise.
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

  const reportView: SupervisionAgentState = useMemo(() => {
    if (drafter.running || drafter.state.draft_report) {
      return { ...drafter.state, case_id: caseId }
    }
    return {
      case_id: caseId,
      draft_report: record?.draft_report ?? undefined,
      report_blocked: record?.report_blocked,
      grounding_problems: record?.grounding_problems,
      reviewer_decisions: record?.decisions,
      report_status:
        record?.status === 'issued' ? 'issued' : record?.status === 'closed_rejected' ? 'rejected' : undefined,
    }
  }, [drafter.running, drafter.state, record, caseId])

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
      toast('Running with edited instructions — recorded on this run, next run returns to defaults.')
    }
  }

  const handleDraft = () => {
    setGate(null)
    resetAgent(drafterAgent, { case_id: caseId })
    drafterAgent.runAgent()
  }

  const handleAsk = (question: string) => {
    setExchanges((prev) => [...prev, { question, reply: null }])
    resetAgent(sessionAgent, { case_id: caseId, officer_message: question, officer: 'Case officer' })
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
  // product — an explicit success moment naming what was issued.
  const prevStatus = useRef<string | undefined>(undefined)
  useEffect(() => {
    const status = reportView.report_status
    if (status === prevStatus.current) return
    const last = reportView.reviewer_decisions?.at(-1)
    if (status === 'issued') {
      toast.success(`Supervisory report issued — ${caseSummary.firm}`, {
        description: last ? `Signed by ${last.reviewer} · ${caseId}` : caseId,
      })
    } else if (status === 'rejected' && prevStatus.current !== undefined) {
      toast(`Report rejected — ${caseSummary.firm}`, {
        description: last ? `By ${last.reviewer} · the findings remain on record` : undefined,
      })
    }
    prevStatus.current = status
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reportView.report_status])

  // The gate should never be invisible — scroll it into view on arrival.
  const scrollToGate = () => gateRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  useEffect(() => {
    if (gate) {
      const frame = requestAnimationFrame(scrollToGate)
      return () => cancelAnimationFrame(frame)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gate?.id])

  const findingsCount = view.findings.length
  const observationsCount = view.observations.length
  const resultsMeta =
    findingsCount || observationsCount
      ? [
          findingsCount && `${findingsCount} finding${findingsCount === 1 ? '' : 's'}`,
          observationsCount && `${observationsCount} observation${observationsCount === 1 ? '' : 's'}`,
        ]
          .filter(Boolean)
          .join(' · ')
      : undefined

  const headerMeta = detail
    ? [detail.raw.firm.sector.replace(/_/g, ' '), detail.raw.firm.hq, `${detail.raw.transaction_history.length} transactions on record`]
        .filter(Boolean)
        .join(' · ')
    : null

  const hasTriage = (record?.runs ?? []).some((r) => r.kind === 'triage')
  const closable = record && !['issued', 'closed_rejected', 'closed_no_action'].includes(record.status)
  const canDraft = hasTriage && !anyRunning && record?.status !== 'closed_no_action'

  return (
    <Tabs defaultValue="review" className="flex h-full min-h-0 flex-col gap-0">
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
          <div className="flex items-center gap-2">
            <PromptOverridesDialog overrides={promptOverrides} onChange={setPromptOverrides} />
            {closable && !gate && (
              <Button variant="outline" onClick={() => setCloseOpen(true)} disabled={anyRunning}>
                <BadgeCheck data-icon="inline-start" />
                Close — no action
              </Button>
            )}
            {gate && !drafter.running ? (
              <Button onClick={scrollToGate}>
                <UserRoundCheck />
                Review decision
              </Button>
            ) : (
              <Button onClick={handleRun} disabled={anyRunning} className={cn(triage.running && 'animate-pulse')}>
                {triage.running ? <Loader2 className="animate-spin" /> : <Play />}
                {triage.running ? 'Reviewing…' : hasTriage ? 'Run again' : 'Run review'}
              </Button>
            )}
          </div>
        </div>
        <TabsList className="mt-2 h-auto gap-1 bg-transparent p-0">
          {[
            { value: 'review', icon: MonitorPlay, label: 'Live review' },
            { value: 'file', icon: FolderOpen, label: 'Case file' },
            { value: 'timeline', icon: History, label: 'Timeline' },
          ].map(({ value, icon: Icon, label }) => (
            <TabsTrigger
              key={value}
              value={value}
              className="gap-1.5 rounded-none border-0 border-b-2 border-transparent px-3 pb-2.5 pt-1.5 shadow-none data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none"
            >
              <Icon className="size-4" />
              {label}
            </TabsTrigger>
          ))}
        </TabsList>
      </header>

      <TabsContent value="review" className="min-h-0 flex-1 overflow-y-auto">
        <div className="flex flex-col gap-3 p-3">
          <Card className="h-[420px] gap-0 overflow-hidden p-0">
            <PanelHeader icon={Waypoints} title="Triage pipeline" meta={graph ? `${graph.nodes.length} agents & checkpoints` : undefined} />
            <div className="min-h-0 flex-1">
              {graph ? (
                <PipelineGraph structure={graph} nodeStatus={displayNodeStatus} nodeStartSeq={feed.nodeStartSeq} />
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Loading graph…</div>
              )}
            </div>
          </Card>

          <div className="grid gap-3 lg:grid-cols-[3fr_2fr]">
            <Card className="h-96 gap-0 overflow-hidden p-0">
              <PanelHeader icon={Radio} title="Live activity" live={anyRunning} />
              <div className="min-h-0 flex-1">
                <StepFeed events={feed.events} running={anyRunning} />
              </div>
            </Card>
            <Card className="h-96 gap-0 overflow-hidden p-0">
              <PanelHeader icon={ListChecks} title="Findings & observations" meta={resultsMeta} />
              <div className="min-h-0 flex-1">
                <ResultsPanel view={view} answers={record?.answers ?? []} />
              </div>
            </Card>
          </div>

          <Card className="h-80 gap-0 overflow-hidden p-0">
            <PanelHeader
              icon={MessageCircleQuestion}
              title="Ask the orchestrator"
              live={session.running}
              meta={record?.answers.length ? `${record.answers.length} answered` : undefined}
            />
            <div className="min-h-0 flex-1">
              <QuestionBox exchanges={exchanges} running={session.running} onAsk={handleAsk} />
            </div>
          </Card>

          {gate && (
            <div ref={gateRef} className="scroll-mt-3">
              <ReviewGate
                key={`${gate.id}-${gate.context.error ?? ''}`}
                context={gate.context}
                onDecide={handleDecision}
                risk={drafter.state.risk_score ?? record?.risk_score ?? null}
                findingsCount={findingsCount}
              />
            </div>
          )}

          <Card className="gap-0 overflow-hidden p-0">
            <PanelHeader icon={FileText} title="Supervisory report" meta={reportStatus(reportView, !!gate)}>
              {canDraft && !gate && !reportView.draft_report && (
                <Button size="sm" onClick={handleDraft} disabled={drafter.running}>
                  {drafter.running ? <Loader2 className="animate-spin" /> : <FileText />}
                  Draft report
                </Button>
              )}
            </PanelHeader>
            <div className="min-h-32">
              <ReportPanel
                state={reportView}
                onDraft={canDraft && !gate ? handleDraft : undefined}
                drafting={drafter.running}
              />
            </div>
          </Card>
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
