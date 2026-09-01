// The supervision map — the whole iterative loop, always on screen.
// Structure comes from GET /graph/full (real LangGraph node ids validated
// server-side, plus the supervisor/orchestrator hub and the caller-level
// return edges that make this a LOOP, not a pipeline: work fans out from
// the orchestrator and results come back to the conversation). Live runs
// light nodes from the same step events the chat's live block reads.
import { useMemo } from 'react'
import {
  Background,
  Handle,
  MarkerType,
  Panel,
  Position,
  ReactFlow,
  useReactFlow,
  type Edge,
  type Node,
} from '@xyflow/react'
import { Maximize, Minus, Plus, UserRound } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { nodeMeta, AGENT_ICON } from '@/lib/node-meta'
import type { FullMap, MapEdgeKind } from '@/lib/types'
import { cn } from '@/lib/utils'

export type NodeStatus = 'pending' | 'active' | 'done' | 'awaiting'

// Vertical, two-column layout tuned for a persistent side panel: the hub on
// top, the three lanes stacked beneath, loop edges bending back upward.
// Canvas is ~594 virtual px wide: the five workers sit in ONE row of
// compact chips (106px each), the 168px spine nodes center above and
// below them. fitView scales the whole thing into the panel.
const SPINE_X = 213  // centers a 168-wide node on the workers' row
const POSITIONS: Record<string, { x: number; y: number }> = {
  supervisor: { x: SPINE_X, y: 0 },
  orchestrator: { x: SPINE_X, y: 100 },
  dispatch: { x: SPINE_X, y: 200 },
  mandate: { x: 0, y: 306 },
  kya: { x: 122, y: 306 },
  log: { x: 244, y: 306 },
  drift: { x: 366, y: 306 },
  investigator: { x: 488, y: 306 },
  findings: { x: SPINE_X, y: 424 },
  synthesizer: { x: SPINE_X, y: 520 },
  draft_report: { x: SPINE_X, y: 676 },
  grounding_check: { x: SPINE_X, y: 772 },
  human_gate: { x: SPINE_X, y: 868 },
}

const LANE_LABELS: { id: string; label: string; y: number }[] = [
  { id: 'lane-drafting', label: 'REVIEW COMPLETE → REPORT & SIGN-OFF', y: 640 },
]

// The five parallel workers render as compact peer chips.
const WORKER_IDS = new Set(['mandate', 'kya', 'log', 'drift', 'investigator'])
// The investigator only joins when the orchestrator routes a question to
// it — dimmed until it actually lights.
const DIMMED_IDS = new Set(['investigator'])

// One-line captions under each node's name while idle.
const CAPTIONS: Record<string, string> = {
  supervisor: 'you',
  orchestrator: 'routes & briefs',
  dispatch: 'fans out',
  findings: 'typed output pool',
  human_gate: 'named decision',
}

const STATUS_RING: Record<NodeStatus, string> = {
  active: 'ring-2 ring-amber-500/60 shadow-[0_0_0_5px_rgba(245,158,11,0.14)] border-amber-500/70',
  done: 'ring-1 ring-emerald-500/50 border-emerald-500/50',
  pending: 'ring-1 ring-border border-border',
  awaiting: 'ring-2 ring-primary/50 shadow-[0_0_0_5px_oklch(0.55_0.21_262_/_0.12)] border-primary/60',
}

function MapNodeView({ data }: { data: { nodeId: string; label: string; status: NodeStatus; synthetic: boolean } }) {
  const meta = nodeMeta(data.nodeId)
  const Icon = data.nodeId === 'supervisor' ? UserRound : meta.icon
  const icon = AGENT_ICON[meta.color]
  const worker = WORKER_IDS.has(data.nodeId)
  const dimmed = DIMMED_IDS.has(data.nodeId) && data.status === 'pending'

  const iconWrap =
    data.status === 'active'
      ? 'bg-amber-500 text-white'
      : data.status === 'done'
        ? 'bg-emerald-500 text-white'
        : data.status === 'awaiting'
          ? 'bg-primary text-primary-foreground'
          : data.synthetic
            ? 'bg-primary/10 text-primary'
            : cn(icon.bg, icon.text)

  const statusDot = (
    <>
      {data.status === 'active' && (
        <span className="absolute -right-1 -top-1 flex size-2.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-500 opacity-75" />
          <span className="relative inline-flex size-2.5 rounded-full bg-amber-500" />
        </span>
      )}
      {data.status === 'awaiting' && (
        <span className="absolute -right-1 -top-1 flex size-2.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-60" />
          <span className="relative inline-flex size-2.5 rounded-full bg-primary" />
        </span>
      )}
    </>
  )

  if (worker) {
    // Compact peer chip — five of these share one row.
    return (
      <div
        className={cn(
          'relative flex flex-col items-center gap-1 rounded-xl border bg-card px-2 py-2 shadow-sm transition-all duration-300',
          STATUS_RING[data.status],
          dimmed && 'border-dashed bg-card/50 opacity-60',
        )}
        style={{ width: 106 }}
      >
        <Handle type="target" position={Position.Top} className="!h-2 !w-2 !border !border-card !bg-muted-foreground/50" />
      <Handle id="lt" type="target" position={Position.Left} className="!h-1.5 !w-1.5 !border-0 !bg-transparent" />
      <Handle id="ls" type="source" position={Position.Left} className="!h-1.5 !w-1.5 !border-0 !bg-transparent" />
      <Handle id="rt" type="target" position={Position.Right} className="!h-1.5 !w-1.5 !border-0 !bg-transparent" />
      <Handle id="rs" type="source" position={Position.Right} className="!h-1.5 !w-1.5 !border-0 !bg-transparent" />
        <div className={cn('flex size-8 items-center justify-center rounded-lg transition-colors duration-300', iconWrap)}>
          <Icon className="size-4.5" strokeWidth={2.25} />
        </div>
        <div className={cn('max-w-full truncate text-[11px] font-semibold', data.status === 'pending' ? 'text-muted-foreground' : 'text-foreground')}>
          {data.label}
        </div>
        <div className="text-[8px] font-medium uppercase tracking-wide text-muted-foreground">
          {data.status === 'active' ? 'working…' : data.status === 'done' ? 'complete' : dimmed ? 'on request' : 'ready'}
        </div>
        {statusDot}
        <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !border !border-card !bg-muted-foreground/50" />
      </div>
    )
  }

  return (
    <div
      className={cn(
        'relative flex items-center gap-2 rounded-xl border bg-card px-2.5 py-2 shadow-sm transition-all duration-300',
        STATUS_RING[data.status],
        data.synthetic && data.status === 'pending' && 'border-primary/40',
      )}
      style={{ width: 168 }}
    >
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !border !border-card !bg-muted-foreground/50" />
      <Handle id="lt" type="target" position={Position.Left} className="!h-1.5 !w-1.5 !border-0 !bg-transparent" />
      <Handle id="ls" type="source" position={Position.Left} className="!h-1.5 !w-1.5 !border-0 !bg-transparent" />
      <Handle id="rt" type="target" position={Position.Right} className="!h-1.5 !w-1.5 !border-0 !bg-transparent" />
      <Handle id="rs" type="source" position={Position.Right} className="!h-1.5 !w-1.5 !border-0 !bg-transparent" />
      <div className={cn('flex size-7 shrink-0 items-center justify-center rounded-lg transition-colors duration-300', iconWrap)}>
        <Icon className="size-4" strokeWidth={2.25} />
      </div>
      <div className="min-w-0 flex-1">
        <div className={cn('truncate text-xs font-semibold', data.status === 'pending' && !data.synthetic ? 'text-muted-foreground' : 'text-foreground')}>
          {data.label}
        </div>
        <div className="text-[9px] font-medium uppercase tracking-wide text-muted-foreground">
          {data.status === 'active'
            ? 'working…'
            : data.status === 'done'
              ? 'complete'
              : data.status === 'awaiting'
                ? 'awaiting you'
                : (CAPTIONS[data.nodeId] ?? 'ready')}
        </div>
      </div>
      {statusDot}
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !border !border-card !bg-muted-foreground/50" />
    </div>
  )
}

function LaneLabelView({ data }: { data: { label: string } }) {
  return (
    <div className="w-[594px] border-t border-dashed border-border pt-1 text-[9px] font-semibold uppercase tracking-[0.14em] text-muted-foreground/70">
      {data.label}
    </div>
  )
}

const nodeTypes = { mapNode: MapNodeView, laneLabel: LaneLabelView }

// Long return/route edges leave the spine and travel the MARGINS as
// curves — they never overlap the main top-to-bottom flow. Everything
// else runs straight down the spine as smoothstep.
const EDGE_ROUTING: Record<string, { sourceHandle: string; targetHandle: string }> = {
  'orchestrator-supervisor': { sourceHandle: 'ls', targetHandle: 'lt' },
  'synthesizer-orchestrator': { sourceHandle: 'rs', targetHandle: 'rt' },
  'supervisor-draft_report': { sourceHandle: 'ls', targetHandle: 'lt' },
  'grounding_check-draft_report': { sourceHandle: 'rs', targetHandle: 'rt' },
}

const EDGE_STYLE: Record<MapEdgeKind, { dash?: string; opacity: number }> = {
  main: { opacity: 1 },
  route: { dash: '6 4', opacity: 0.9 },
  loop: { dash: '3 4', opacity: 0.75 },
  return: { dash: '2 5', opacity: 0.55 },
}

function MapControls() {
  const { zoomIn, zoomOut, fitBounds, getNodesBounds, getNodes } = useReactFlow()
  // fitView() only QUEUES on a fully-static graph — fitBounds sets the
  // viewport directly (the React Flow v12 trap found in phase 10).
  const fit = () => fitBounds(getNodesBounds(getNodes()), { padding: 0.1, duration: 200 })
  return (
    <Panel position="bottom-right" className="!m-2">
      <div className="flex items-center gap-0.5 rounded-lg border bg-card p-0.5 shadow-sm">
        <Button variant="ghost" size="icon-xs" aria-label="Zoom in" onClick={() => zoomIn({ duration: 150 })}>
          <Plus />
        </Button>
        <Button variant="ghost" size="icon-xs" aria-label="Zoom out" onClick={() => zoomOut({ duration: 150 })}>
          <Minus />
        </Button>
        <Button variant="ghost" size="icon-xs" aria-label="Fit map in view" onClick={fit}>
          <Maximize />
        </Button>
      </div>
    </Panel>
  )
}

export function SupervisionMap({
  map,
  nodeStatus,
  nodeStartSeq = {},
}: {
  map: FullMap
  nodeStatus: Record<string, NodeStatus>
  nodeStartSeq?: Record<string, number>
}) {
  const nodes = useMemo<Node[]>(() => {
    const flow: Node[] = map.nodes.map((n) => ({
      id: n.id,
      type: 'mapNode',
      position: POSITIONS[n.id] ?? { x: 0, y: 0 },
      data: { nodeId: n.id, label: n.label, status: nodeStatus[n.id] ?? 'pending', synthetic: n.synthetic },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    }))
    for (const lane of LANE_LABELS) {
      flow.push({
        id: lane.id,
        type: 'laneLabel',
        position: { x: 0, y: lane.y },
        data: { label: lane.label },
        selectable: false,
        draggable: false,
      })
    }
    return flow
  }, [map.nodes, nodeStatus])

  const edges = useMemo<Edge[]>(
    () =>
      map.edges.map((e) => {
        const style = EDGE_STYLE[e.kind]
        const sourceStart = nodeStartSeq[e.source]
        const targetStart = nodeStartSeq[e.target]
        const traversed = sourceStart !== undefined && targetStart !== undefined && targetStart > sourceStart
        const live = traversed && nodeStatus[e.target] === 'active'
        const holding = traversed && nodeStatus[e.target] === 'awaiting'
        const settled = traversed && nodeStatus[e.target] === 'done'
        const routing = EDGE_ROUTING[`${e.source}-${e.target}`]
        return {
          id: `${e.source}-${e.target}-${e.kind}`,
          source: e.source,
          target: e.target,
          // Margin-routed edges curve; spine edges step. No labels — the
          // dash styles carry the meaning (solid flow, dashed route/return).
          type: routing ? 'default' : 'smoothstep',
          ...(routing ?? {}),
          animated: live || holding,
          style: {
            stroke: live ? '#f59e0b' : holding ? 'oklch(0.55 0.21 262)' : settled ? '#10b981' : 'var(--border)',
            strokeWidth: live || holding ? 2.25 : settled ? 2 : 1.5,
            strokeDasharray: style.dash,
            opacity: live || settled || holding ? 1 : style.opacity,
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 14,
            height: 14,
            color: live ? '#f59e0b' : holding ? 'oklch(0.55 0.21 262)' : settled ? '#10b981' : '#9ca3af',
          },
        }
      }),
    [map.edges, nodeStatus, nodeStartSeq],
  )

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.08 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        zoomOnScroll={true}
        panOnDrag={true}
        minZoom={0.3}
        maxZoom={1.4}
      >
        <Background gap={20} size={1} className="opacity-60" />
        <MapControls />
      </ReactFlow>
    </div>
  )
}
