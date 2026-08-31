import { useEffect, useMemo, useRef, useState } from 'react'
import { useCoAgent } from '@copilotkit/react-core'
// useAgent isn't re-exported from the v1-compat root path (only used
// internally there) but resolves the same shared registry instance either
// way — see the comment above `useAgent(...)` below.
import { useAgent } from '@copilotkit/react-core/v2'
import { toast } from 'sonner'
import { ArrowLeft, FileText, FolderOpen, Play, Loader2, UserRoundCheck, Waypoints, Radio, ListChecks, MonitorPlay } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { getCase, getGraphStructure } from '@/lib/api'
import type { CaseDetail, GraphStructure, CaseSummary } from '@/lib/types'
import { EMPTY_AGENT_STATE, type SupervisionAgentState } from '@/lib/agent-state'
import { usePipelineFeed } from '@/hooks/usePipelineFeed'
import { PipelineGraph } from '@/components/PipelineGraph'
import { StepFeed } from '@/components/StepFeed'
import { ResultsPanel } from '@/components/ResultsPanel'
import { CaseFilePanel } from '@/components/CaseFilePanel'
import { ReportPanel, reportStatus } from '@/components/ReportPanel'
import { ReviewGate, type GateSubmission } from '@/components/ReviewGate'
import type { GateContext, ReportStatus } from '@/lib/types'
import { cn } from '@/lib/utils'

const AGENT_NAME = 'mandate_supervisor'

function PanelHeader({
  icon: Icon,
  title,
  meta,
  live,
}: {
  icon: typeof Waypoints
  title: string
  meta?: string
  live?: boolean
}) {
  return (
    <div className="flex items-center justify-between border-b px-4 py-3">
      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Icon className="size-4 text-muted-foreground" />
        {title}
      </div>
      <div className="flex items-center gap-1.5">
        {live && (
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-500 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-500" />
          </span>
        )}
        {meta && <span className="text-xs font-medium text-muted-foreground">{meta}</span>}
      </div>
    </div>
  )
}

function CaseReviewInner({
  caseSummary,
  casePath,
  onBack,
}: {
  caseSummary: CaseSummary
  casePath: string
  onBack: () => void
}) {
  const [graph, setGraph] = useState<GraphStructure | null>(null)
  const [detail, setDetail] = useState<CaseDetail | null>(null)
  // The paused human gate (PLAN item 13): set when a run finishes with the
  // AG-UI interrupt outcome, cleared when the reviewer's decision resumes it.
  const [gate, setGate] = useState<{ id: string; context: GateContext } | null>(null)
  const [confirmRerun, setConfirmRerun] = useState(false)
  const gateRef = useRef<HTMLDivElement>(null)
  const feed = usePipelineFeed()

  useEffect(() => {
    getGraphStructure().then(setGraph).catch(() => setGraph(null))
  }, [])

  useEffect(() => {
    getCase(caseSummary.case_id).then(setDetail).catch(() => setDetail(null))
  }, [caseSummary.case_id])

  const { state, running } = useCoAgent<SupervisionAgentState>({
    name: AGENT_NAME,
    initialState: { ...EMPTY_AGENT_STATE, case_path: casePath },
  })

  // useCoAgent's own `run()` (v1-deprecated compat, this CopilotKit release)
  // extracts `agent.runAgent` as a bare reference before returning it, which
  // drops its `this` binding — calling it throws inside @ag-ui/client's
  // HttpAgent.runAgent ("Cannot set properties of undefined (setting
  // 'abortController')"), confirmed live. useAgent() resolves the same
  // shared registry instance useCoAgent binds to internally, so calling
  // agent.runAgent() directly here (a normal, correctly-bound method call)
  // routes around the bug without giving up useCoAgent for state/running.
  const { agent } = useAgent({ agentId: AGENT_NAME })

  // The registry agent is a shared singleton: one client state, one
  // threadId, across every case the officer opens. Without a hard reset
  // per case, opening case B renders case A's findings/report — and worse,
  // running case B on case A's thread makes LangGraph's checkpoint MERGE
  // the runs (the findings/observations/decisions channels are reducers,
  // so case A's entries survive into case B's record). Confirmed live.
  // Fresh thread + empty state per case isolates both sides.
  const resetAgentForCase = () => {
    agent.threadId = crypto.randomUUID()
    agent.setMessages([])
    agent.setState({ ...EMPTY_AGENT_STATE, case_path: casePath })
  }

  useEffect(() => {
    resetAgentForCase()
    setGate(null)
    // Runs when the officer opens a (different) case; CaseReview keys this
    // component by case_id, so mount ≡ case change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agent, caseSummary.case_id])

  // LangGraph retries a node on a transient error (its default retry
  // policy — seen live via a raw /agent trace: the same stepName's
  // STARTED/FINISHED pair repeating several times in one run), and that
  // retry's real completion event doesn't always survive three hops of SSE
  // relaying (FastAPI -> Node CopilotKit runtime -> browser) intact. Rather
  // than trust every event arrived and risk a node stuck showing "active"
  // forever, this derives the *displayed* status fresh on every render:
  // once the run itself is no longer running, nothing can still be
  // legitimately active, full stop — a started-but-unresolved node reads
  // as done, not as a stale spinner.
  const displayNodeStatus = useMemo(() => {
    const base = running
      ? { ...feed.nodeStatus }
      : Object.fromEntries(
          Object.entries(feed.nodeStatus).map(([id, status]) => [id, status === 'active' ? ('done' as const) : status]),
        )
    // The gate never emits STEP_FINISHED when it interrupts — while a
    // decision is pending it's neither "working" nor "complete", it's
    // holding. Its own visual state prevents both wrong readings (green
    // Complete during the pause, and the stale amber the settle pass used
    // to leave behind).
    if (gate) base['human_gate'] = 'awaiting'
    return base
  }, [feed.nodeStatus, running, gate])

  // The live feed: CopilotKit's higher-level useCoAgentStateRender /
  // useCopilotAction('*') hooks (CLAUDE.md's named hooks for this) turned
  // out to only fire for runs kicked off through useCoAgent's own run() —
  // which is unusable here (see the note above agent.runAgent() below), and
  // never fired at all against a run started via agent.runAgent() directly.
  // agent.subscribe() is the same AG-UI client both of those hooks are
  // built on, just without that gap: step/tool-call events land here
  // exactly as ag_ui_langgraph emits them from the LangGraph run, giving
  // React Flow's node highlighting and the step feed their live data —
  // still headless, still no chat widget, per CLAUDE.md's intent.
  useEffect(() => {
    const subscription = agent.subscribe({
      onStepStartedEvent: ({ event }) => feed.recordNodeEvent(event.stepName, 'inProgress'),
      onStepFinishedEvent: ({ event }) => feed.recordNodeEvent(event.stepName, 'complete'),
      onToolCallStartEvent: ({ event }) => feed.recordToolEvent(event.toolCallName, 'inProgress', {}),
      onToolCallArgsEvent: ({ toolCallName, partialToolCallArgs }) =>
        feed.recordToolEvent(toolCallName, 'executing', partialToolCallArgs),
      onToolCallEndEvent: ({ toolCallName, toolCallArgs }) => feed.recordToolEvent(toolCallName, 'complete', toolCallArgs),
      // The human gate arrives as a run that *finishes with an interrupt
      // outcome* (api/main.py sets emit_interrupt_outcome=True). The full
      // gate context dict lives under the AG-UI interrupt's
      // metadata.langgraph.raw (ag_ui_langgraph/interrupts.py).
      onRunFinishedEvent: (params) => {
        if ('interrupts' in params && params.interrupts.length > 0) {
          const intr = params.interrupts[0] as { id: string; metadata?: { langgraph?: { raw?: GateContext } } }
          const context = intr.metadata?.langgraph?.raw
          if (context) setGate({ id: intr.id, context })
        } else {
          setGate(null)
        }
      },
    })
    return () => subscription.unsubscribe()
    // feed.recordNodeEvent/recordToolEvent are stable (useCallback, no deps);
    // omitting `feed` avoids resubscribing on every event it causes to be recorded.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agent])

  // Resumes the interrupted run with the reviewer's decision — the graph
  // validates it server-side (a bad payload re-interrupts with an error,
  // which lands right back here as a fresh gate).
  const handleDecision = (decision: GateSubmission) => {
    if (!gate) return
    setGate(null)
    agent.runAgent({ resume: [{ interruptId: gate.id, status: 'resolved', payload: decision }] })
  }

  const handleRun = () => {
    feed.reset()
    setGate(null)
    // A fresh run gets a fresh thread too — re-running the same case on
    // its old thread would merge into the previous run's reducer channels
    // (accumulated decisions, stale report_status) instead of starting
    // clean. Setting state synchronously before runAgent() is also what
    // actually lands case_path in the request: useCoAgent's initialState
    // never reaches the first request in this release (confirmed live —
    // ingestion crashed with KeyError: 'case_path' before this).
    resetAgentForCase()
    agent.runAgent()
  }

  // A fresh run wipes everything on screen (by design — see handleRun), so
  // when results exist the wipe needs a deliberate yes first, not a
  // one-click accident.
  const hasResults =
    (state.findings?.length ?? 0) > 0 || (state.observations?.length ?? 0) > 0 || !!state.draft_report
  const handleRunClick = () => {
    if (hasResults) setConfirmRerun(true)
    else handleRun()
  }

  // The gate renders below the fold at common viewport heights; the one
  // moment the whole system waits on a human should never be invisible.
  // Scroll it into view when it arrives (also on a validation re-interrupt,
  // which changes the interrupt id), and keep an always-visible header
  // anchor as the persistent affordance.
  const scrollToGate = () => gateRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  useEffect(() => {
    if (gate) {
      const frame = requestAnimationFrame(scrollToGate)
      return () => cancelAnimationFrame(frame)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gate?.id])

  // The receipt: issuing a supervisory report is the gravest act in the
  // product — it gets an explicit success moment naming what was issued,
  // not just a status meta-string (a mere upload already earned a toast).
  const prevReportStatus = useRef<ReportStatus | undefined>(undefined)
  useEffect(() => {
    const status = state.report_status
    if (status === prevReportStatus.current) return
    const last = state.reviewer_decisions?.[state.reviewer_decisions.length - 1]
    if (status === 'issued') {
      toast.success(`Supervisory report issued — ${caseSummary.firm}`, {
        description: last ? `Signed by ${last.reviewer} · ${caseSummary.case_id}` : caseSummary.case_id,
      })
    } else if (status === 'rejected') {
      toast(`Report rejected — ${caseSummary.firm}`, {
        description: last ? `By ${last.reviewer} · the findings remain on record` : 'The findings remain on record',
      })
    }
    prevReportStatus.current = status
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.report_status])

  const findingsCount = state.findings?.length ?? 0
  const observationsCount = state.observations?.length ?? 0
  const resultsMeta =
    findingsCount || observationsCount
      ? [findingsCount && `${findingsCount} finding${findingsCount === 1 ? '' : 's'}`, observationsCount && `${observationsCount} observation${observationsCount === 1 ? '' : 's'}`]
          .filter(Boolean)
          .join(' · ')
      : undefined

  const headerMeta = detail
    ? [detail.raw.firm.sector.replace(/_/g, ' '), detail.raw.firm.hq, `${detail.raw.transaction_history.length} transactions on record`]
        .filter(Boolean)
        .join(' · ')
    : null

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
                {caseSummary.case_id}
                {headerMeta && <span className="font-sans"> · {headerMeta}</span>}
              </p>
            </div>
          </div>
          {gate && !running ? (
            // While the gate holds, the header's primary action IS the
            // decision — an enabled anchor down to it, not a disabled
            // "Awaiting decision" dead end.
            <Button onClick={scrollToGate}>
              <UserRoundCheck />
              Review decision
            </Button>
          ) : (
            <Button onClick={handleRunClick} disabled={running} className={cn(running && 'animate-pulse')}>
              {running ? <Loader2 className="animate-spin" /> : <Play />}
              {running ? 'Reviewing…' : 'Run review'}
            </Button>
          )}
        </div>
        <TabsList className="mt-2 h-auto gap-1 bg-transparent p-0">
          <TabsTrigger
            value="review"
            className="gap-1.5 rounded-none border-0 border-b-2 border-transparent px-3 pb-2.5 pt-1.5 shadow-none data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none"
          >
            <MonitorPlay className="size-4" />
            Live review
          </TabsTrigger>
          <TabsTrigger
            value="file"
            className="gap-1.5 rounded-none border-0 border-b-2 border-transparent px-3 pb-2.5 pt-1.5 shadow-none data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none"
          >
            <FolderOpen className="size-4" />
            Case file
          </TabsTrigger>
        </TabsList>
      </header>

      {/* Pipeline is the hero; live activity + findings share the next
          row; the drafted report closes the page — the tab scrolls as a
          normal page now that four surfaces no longer fit one viewport. */}
      <TabsContent value="review" className="min-h-0 flex-1 overflow-y-auto">
        <div className="flex flex-col gap-3 p-3">
          <Card className="h-[440px] gap-0 overflow-hidden p-0">
            <PanelHeader icon={Waypoints} title="Pipeline" meta={graph ? `${graph.nodes.length} agents & checkpoints` : undefined} />
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
              <PanelHeader icon={Radio} title="Live activity" live={running} />
              <div className="min-h-0 flex-1">
                <StepFeed events={feed.events} running={running} />
              </div>
            </Card>
            <Card className="h-96 gap-0 overflow-hidden p-0">
              <PanelHeader icon={ListChecks} title="Findings & observations" meta={resultsMeta} />
              <div className="min-h-0 flex-1">
                <ResultsPanel state={state} />
              </div>
            </Card>
          </div>

          {gate && (
            <div ref={gateRef} className="scroll-mt-3">
              <ReviewGate
                key={`${gate.id}-${gate.context.error ?? ''}`}
                context={gate.context}
                onDecide={handleDecision}
                risk={state.risk_score ?? null}
                findingsCount={findingsCount}
              />
            </div>
          )}

          <Card className="gap-0 overflow-hidden p-0">
            <PanelHeader icon={FileText} title="Supervisory report" meta={reportStatus(state, !!gate)} />
            <div className="min-h-32">
              <ReportPanel state={state} />
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

      <Dialog open={confirmRerun} onOpenChange={setConfirmRerun}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Re-run this review?</DialogTitle>
            <DialogDescription>
              A fresh run starts clean: the findings, risk score, report, and decision record currently on screen for{' '}
              <span className="font-mono text-[13px]">{caseSummary.case_id}</span> are cleared.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmRerun(false)}>
              Keep results
            </Button>
            <Button
              onClick={() => {
                setConfirmRerun(false)
                handleRun()
              }}
            >
              <Play />
              Re-run review
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
      {/* Remounts (and resets useCoAgent's internal state) whenever the
          selected case changes. */}
      <CaseReviewInner key={caseSummary.case_id} caseSummary={caseSummary} casePath={caseSummary.case_path} onBack={onBack} />
    </div>
  )
}
