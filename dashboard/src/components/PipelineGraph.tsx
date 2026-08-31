import { useMemo } from 'react'
import { ReactFlow, Background, Handle, Panel, useReactFlow, type Edge, type Node, MarkerType, Position } from '@xyflow/react'
import { CheckCheck, Maximize, Minus, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { nodeMeta, AGENT_ICON } from '@/lib/node-meta'
import type { GraphStructure } from '@/lib/types'

export type NodeStatus = 'pending' | 'active' | 'done' | 'awaiting'

// Fixed layout: the graph's own shape (pipeline/graph.py) is small and
// stable — dispatch fans out to four specialists, which join at
// escalate_check, which may loop back through bump_round. A hardcoded
// layout reads far more clearly than an auto-layout pass would for eight
// nodes, and the structure itself (nodes/edges) still comes from
// `/graph` -> `graph.get_graph()`, never hand-maintained. Spacing is wide —
// this graph is the product's visual centerpiece, not a compact diagram.
// The TRIAGE graph — since the run split (architecture-v2 §14) drafting and
// the human gate live in their own short run, surfaced by the report panel,
// not on this canvas.
const POSITIONS: Record<string, { x: number; y: number }> = {
  ingest: { x: 0, y: 280 },
  dispatch: { x: 300, y: 280 },
  mandate: { x: 660, y: 0 },
  kya: { x: 660, y: 190 },
  log: { x: 660, y: 380 },
  drift: { x: 660, y: 570 },
  escalate_check: { x: 1040, y: 280 },
  bump_round: { x: 1360, y: 60 },
  critic: { x: 1360, y: 280 },
  synthesizer: { x: 1680, y: 280 },
  risk_score: { x: 2000, y: 280 },
}

const STATUS_RING: Record<NodeStatus, string> = {
  active: 'ring-4 ring-amber-500/60 shadow-[0_0_0_9px_rgba(245,158,11,0.16)] border-amber-500/70',
  done: 'ring-2 ring-emerald-500/50 border-emerald-500/50',
  pending: 'ring-1 ring-border border-border',
  // The human gate holding for a decision — deliberately its own state:
  // not "working" (no machine is computing) and not "complete" (nothing
  // was decided yet). Primary blue = the human's color in this system.
  awaiting: 'ring-4 ring-primary/50 shadow-[0_0_0_9px_oklch(0.55_0.21_262_/_0.12)] border-primary/60',
}

const STATUS_CAPTION: Record<NodeStatus, string> = {
  active: 'Working…',
  done: 'Complete',
  pending: 'Waiting',
  awaiting: 'Awaiting reviewer',
}

function StatusNode({ data }: { data: { nodeId: string; status: NodeStatus } }) {
  const meta = nodeMeta(data.nodeId)
  const Icon = meta.icon
  const icon = AGENT_ICON[meta.color]

  const iconWrapClass =
    data.status === 'active'
      ? 'bg-amber-500 text-white'
      : data.status === 'done'
        ? 'bg-emerald-500 text-white'
        : data.status === 'awaiting'
          ? 'bg-primary text-primary-foreground'
          : cn(icon.bg, icon.text)

  return (
    <div
      className={cn(
        'relative flex items-center gap-3.5 rounded-2xl border-2 bg-card px-5 py-4 shadow-md transition-all duration-300',
        STATUS_RING[data.status],
      )}
      style={{ width: 236 }}
    >
      <Handle type="target" position={Position.Left} className="!h-3 !w-3 !border-2 !border-card !bg-muted-foreground/50" />
      <div className={cn('flex size-11 shrink-0 items-center justify-center rounded-xl transition-colors duration-300', iconWrapClass)}>
        <Icon className="size-6" strokeWidth={2.25} />
      </div>
      <div className="min-w-0 flex-1">
        <div className={cn('truncate text-base font-semibold', data.status === 'pending' ? 'text-muted-foreground' : 'text-foreground')}>
          {meta.label}
        </div>
        <div className="mt-0.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {STATUS_CAPTION[data.status]}
        </div>
      </div>
      {data.status === 'active' && (
        <span className="absolute -right-1.5 -top-1.5 flex size-4">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-500 opacity-75" />
          <span className="relative inline-flex size-4 rounded-full bg-amber-500" />
        </span>
      )}
      {data.status === 'awaiting' && (
        <span className="absolute -right-1.5 -top-1.5 flex size-4">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-60" />
          <span className="relative inline-flex size-4 rounded-full bg-primary" />
        </span>
      )}
      {data.status === 'done' && (
        <span className="absolute -right-1.5 -top-1.5 flex size-4 items-center justify-center rounded-full bg-emerald-500 text-white">
          <CheckCheck className="size-2.5" strokeWidth={3} />
        </span>
      )}
      <Handle type="source" position={Position.Right} className="!h-3 !w-3 !border-2 !border-card !bg-muted-foreground/50" />
    </div>
  )
}

const nodeTypes = { status: StatusNode }

// Zoom/fit controls in the product's own chrome — React Flow's default
// <Controls> looks like a foreign widget. Rendered as a ReactFlow child so
// useReactFlow resolves against this graph's store. Fit is the escape
// hatch: any pan, wheel-zoom, or stray double-click has a one-click way
// back to the full pipeline.
function GraphControls() {
  const { zoomIn, zoomOut, fitBounds, getNodesBounds, getNodes } = useReactFlow()
  // fitView() only QUEUES a fit, consumed when the next node change flows
  // through the store — on this fully static graph (nothing draggable,
  // nothing selectable) that next change never comes, so the button would
  // silently do nothing (measured live: transform unchanged). fitBounds
  // computes and sets the viewport directly, no queue involved.
  const fit = () => fitBounds(getNodesBounds(getNodes()), { padding: 0.15, duration: 200 })
  return (
    <Panel position="bottom-left" className="!m-2.5">
      <div className="flex items-center gap-0.5 rounded-lg border bg-card p-0.5 shadow-sm">
        <Button variant="ghost" size="icon-xs" aria-label="Zoom in" onClick={() => zoomIn({ duration: 150 })}>
          <Plus />
        </Button>
        <Button variant="ghost" size="icon-xs" aria-label="Zoom out" onClick={() => zoomOut({ duration: 150 })}>
          <Minus />
        </Button>
        <Button variant="ghost" size="icon-xs" aria-label="Fit pipeline in view" onClick={fit}>
          <Maximize />
        </Button>
      </div>
    </Panel>
  )
}

export function PipelineGraph({
  structure,
  nodeStatus,
  nodeStartSeq = {},
}: {
  structure: GraphStructure
  nodeStatus: Record<string, NodeStatus>
  /** Last STARTED sequence per node (usePipelineFeed) — edge colors derive
   * from actual traversal order, not node status alone. */
  nodeStartSeq?: Record<string, number>
}) {
  const nodes = useMemo<Node[]>(
    () =>
      structure.nodes.map((n) => ({
        id: n.id,
        type: 'status',
        position: POSITIONS[n.id] ?? { x: 0, y: 0 },
        data: { nodeId: n.id, status: nodeStatus[n.id] ?? 'pending' },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      })),
    [structure.nodes, nodeStatus],
  )

  const edges = useMemo<Edge[]>(
    () =>
      structure.edges.map((e) => {
        // Every edge color derives from one predicate: was this edge
        // actually TRAVERSED? True only when both ends have started and the
        // target started AFTER the source — start order is the only signal
        // the step events give us, and it's the right one. Three prior
        // status-based heuristics each produced a real, user-reported false
        // positive on the gate/bump return edges (amber while the gate
        // held; amber on return edges into the working node; green on
        // return edges into any finished node). Ordering kills the whole
        // family: human_gate→mandate stays dark unless a reviewer rerun
        // really sent the case back — because only then does mandate start
        // *after* the gate did.
        const sourceStart = nodeStartSeq[e.source]
        const targetStart = nodeStartSeq[e.target]
        const traversed = sourceStart !== undefined && targetStart !== undefined && targetStart > sourceStart
        const live = traversed && nodeStatus[e.target] === 'active'
        const holding = traversed && nodeStatus[e.target] === 'awaiting'
        const settled = traversed && nodeStatus[e.target] === 'done'
        return {
          id: `${e.source}-${e.target}`,
          source: e.source,
          target: e.target,
          type: 'smoothstep',
          animated: live || holding,
          style: {
            stroke: live ? '#f59e0b' : holding ? 'oklch(0.55 0.21 262)' : settled ? '#10b981' : 'var(--border)',
            strokeWidth: live || holding ? 3 : settled ? 2.5 : 2,
            strokeDasharray: e.conditional ? '6 4' : undefined,
            opacity: settled && !live ? 0.6 : 1,
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 20,
            height: 20,
            color: live ? '#f59e0b' : holding ? 'oklch(0.55 0.21 262)' : settled ? '#10b981' : '#9ca3af',
          },
        }
      }),
    [structure.edges, nodeStatus],
  )

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        zoomOnScroll={true}
        panOnDrag={true}
        minZoom={0.4}
        maxZoom={1.25}
      >
        <Background gap={24} size={1.5} className="opacity-70" />
        <GraphControls />
      </ReactFlow>
    </div>
  )
}
