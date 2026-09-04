// The supervision map — the whole iterative loop, always on screen.
// Structure comes from GET /graph/full (real LangGraph node ids validated
// server-side, plus the supervisor/orchestrator hub and the caller-level
// return edges that make this a LOOP, not a pipeline: work fans out from
// the orchestrator and results come back to the conversation). Live runs
// light nodes from the same step events the chat's live block reads.
import { useEffect, useMemo, useRef } from 'react'
import {
  Background,
  BaseEdge,
  Handle,
  MarkerType,
  Panel,
  Position,
  ReactFlow,
  useNodesState,
  useReactFlow,
  type Edge,
  type EdgeProps,
  type Node,
} from '@xyflow/react'
import { Maximize, Minus, Plus, UserRound } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { nodeMeta, AGENT_ICON } from '@/lib/node-meta'
import type { FullMap, MapEdgeKind } from '@/lib/types'
import { cn } from '@/lib/utils'

// unresolved: the specialist returned, but its judged rules are still open
// (a facts-only pass, a timed-out model call). Not a finding, not clean.
export type NodeStatus = 'pending' | 'active' | 'done' | 'awaiting' | 'clean' | 'findings' | 'unresolved'

type MapNodeData = { nodeId: string; label: string; status: NodeStatus; synthetic: boolean; worker?: boolean }
type MapNode = Node<MapNodeData, 'mapNode'>

// Keep the original chip/spine design. Membership comes from the backend's
// compiled graphs; wrap peers so new specialists cannot overlap at (0, 0).
const SPINE_X = 213
const DIMMED_IDS = new Set(['investigator', 'systemic', 'red_team'])
function layout(map: FullMap) {
  const peers = map.nodes.filter(n => n.role === 'peer')
  const requested = map.nodes.filter(n => n.role === 'on_request')
  const positions: Record<string, { x: number; y: number }> = {
    supervisor: { x: SPINE_X, y: 0 }, orchestrator: { x: SPINE_X, y: 100 },
  }
  peers.forEach((n, i) => { positions[n.id] = { x: 30 + (i % 4) * 140, y: 210 + Math.floor(i / 4) * 104 } })
  const y = 210 + Math.ceil(peers.length / 4) * 104
  requested.forEach((n, i) => { positions[n.id] = { x: 90 + i * 150, y } })
  const spine = ['control_assurance', 'findings', 'synthesizer', 'draft_report', 'grounding_check', 'human_gate']
  spine.forEach((id, i) => { positions[id] = { x: SPINE_X, y: y + 112 + i * 86 + (i >= 3 ? 40 : 0) } })
  // New support nodes get a visible row rather than silently overlapping.
  map.nodes.filter(n => !positions[n.id]).forEach((n, i) => { positions[n.id] = { x: SPINE_X, y: y + 680 + i * 86 } })
  return positions
}

// One-line captions under each node's name while idle.
const CAPTIONS: Record<string, string> = {
  supervisor: 'you',
  orchestrator: 'routes · briefs · dispatches',
  findings: 'typed output pool',
  human_gate: 'named decision',
}

const STATUS_RING: Record<NodeStatus, string> = {
  // Matches the chat's pills: blue is activity, red is findings.
  active: 'ring-2 ring-blue-500/60 shadow-[0_0_0_5px_rgba(59,130,246,0.16)] border-blue-500/70',
  clean: 'ring-1 ring-emerald-500/50 border-emerald-500/50',
  findings: 'ring-1 ring-red-500/50 border-red-500/50',
  unresolved: 'ring-1 ring-border border-dashed border-muted-foreground/50',
  done: 'ring-1 ring-emerald-500/50 border-emerald-500/50',
  pending: 'ring-1 ring-border border-border',
  awaiting: 'ring-2 ring-primary/50 shadow-[0_0_0_5px_oklch(0.55_0.21_262_/_0.12)] border-primary/60',
}

function MapNodeView({ data }: { data: MapNodeData }) {
  const meta = nodeMeta(data.nodeId)
  const Icon = data.nodeId === 'supervisor' ? UserRound : meta.icon
  const icon = AGENT_ICON[meta.color]
  const worker = data.worker
  const dimmed = DIMMED_IDS.has(data.nodeId) && data.status === 'pending'

  const iconWrap =
    data.status === 'active'
      ? 'bg-blue-500 text-white'
      : data.status === 'findings'
        ? 'bg-red-500/20 text-red-700 dark:text-red-400'
        : data.status === 'unresolved'
        ? 'bg-muted text-muted-foreground'
        : ['done', 'clean'].includes(data.status)
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
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-500 opacity-75" />
          <span className="relative inline-flex size-2.5 rounded-full bg-blue-500" />
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
          {data.status === 'active' ? 'working…' : data.status === 'findings' ? 'returned · findings' : data.status === 'unresolved' ? 'returned · unresolved' : data.status === 'clean' ? 'returned · clean' : data.status === 'done' ? 'complete' : dimmed ? 'on request' : 'ready'}
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
            : data.status === 'findings' ? 'returned · findings'
              : data.status === 'unresolved' ? 'returned · unresolved'
              : data.status === 'clean' ? 'returned · clean'
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
const edgeTypes = { detour: DetourEdge }

// Long return/route edges must never pass under a box. Each gets an
// explicit DETOUR LANE — a vertical channel in the margins, clear of every
// node — and a custom edge draws source → lane → target orthogonally.
// Lanes are spread so two edges sharing a side never overlap.
const EDGE_ROUTING: Record<string, { sourceHandle: string; targetHandle: string; laneX: number }> = {
  // supervisor ⇄ orchestrator loop: back up the near-left lane
  'orchestrator-supervisor': { sourceHandle: 'ls', targetHandle: 'lt', laneX: -44 },
  // results return to the hub around the far right, outside the worker row
  'synthesizer-orchestrator': { sourceHandle: 'rs', targetHandle: 'rt', laneX: 648 },
  // the draft_report routing runs down the far-left lane, around everything
  'orchestrator-draft_report': { sourceHandle: 'ls', targetHandle: 'lt', laneX: -76 },
  // grounding retry: short hop in the right margin of the report lane
  'grounding_check-draft_report': { sourceHandle: 'rs', targetHandle: 'rt', laneX: 428 },
}

function DetourEdge({ sourceX, sourceY, targetX, targetY, style, markerEnd, data }: EdgeProps) {
  const laneX = (data as { laneX?: number } | undefined)?.laneX ?? sourceX
  const r = 14
  const dirIn = laneX > sourceX ? 1 : -1
  const dirV = targetY > sourceY ? 1 : -1
  const dirOut = targetX > laneX ? 1 : -1
  const path = [
    `M ${sourceX} ${sourceY}`,
    `L ${laneX - dirIn * r} ${sourceY}`,
    `Q ${laneX} ${sourceY} ${laneX} ${sourceY + dirV * r}`,
    `L ${laneX} ${targetY - dirV * r}`,
    `Q ${laneX} ${targetY} ${laneX + dirOut * r} ${targetY}`,
    `L ${targetX} ${targetY}`,
  ].join(' ')
  return <BaseEdge path={path} style={style} markerEnd={markerEnd} />
}

const EDGE_STYLE: Record<MapEdgeKind, { dash?: string; opacity: number; width?: number }> = {
  main: { opacity: 1 },
  route: { dash: '6 4', opacity: 0.95, width: 2 },
  loop: { dash: '3 4', opacity: 0.8 },
  return: { dash: '4 4', opacity: 0.9, width: 2 },
}

function MapControls() {
  const { zoomIn, zoomOut, fitBounds, getNodesBounds, getNodes } = useReactFlow()
  // fitView() only QUEUES on a fully-static graph — fitBounds sets the
  // viewport directly (the React Flow v12 trap found in phase 10).
  const fit = () => fitBounds(getNodesBounds(getNodes()), { padding: 0.16, duration: 200 })
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
  onNodeClick,
}: {
  map: FullMap
  nodeStatus: Record<string, NodeStatus>
  nodeStartSeq?: Record<string, number>
  onNodeClick?: (id: string) => void
}) {
  // Node objects are created once per map and afterwards only their
  // `data.status` changes. React Flow keeps a node's measured size on the
  // object it was handed; rebuilding the objects on every status change made
  // it re-measure every node, and while a run's stream kept the main thread
  // busy the unmeasured nodes rendered invisible — the boxes vanished
  // mid-run and came back one at a time. Controlled nodes keep their size.
  const [nodes, setNodes, onNodesChange] = useNodesState<MapNode>([])
  const latestStatus = useRef(nodeStatus)
  latestStatus.current = nodeStatus
  useEffect(() => {
    const positions = layout(map)
    setNodes(map.nodes.map((n) => ({
      id: n.id,
      type: 'mapNode',
      position: positions[n.id],
      data: { nodeId: n.id, label: n.label, status: latestStatus.current[n.id] ?? 'pending', synthetic: n.synthetic, worker: n.role === 'peer' || n.role === 'on_request' },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    })))
  }, [map, setNodes])
  useEffect(() => {
    setNodes((current) => current.map((n) => {
      const status = nodeStatus[n.id] ?? 'pending'
      return n.data.status === status ? n : { ...n, data: { ...n.data, status } }
    }))
  }, [nodeStatus, setNodes])

  const edges = useMemo<Edge[]>(
    () =>
      map.edges.map((e) => {
        const style = EDGE_STYLE[e.kind]
        const sourceStart = nodeStartSeq[e.source]
        const targetStart = nodeStartSeq[e.target]
        const traversed = sourceStart !== undefined && targetStart !== undefined && targetStart > sourceStart
        const live = traversed && nodeStatus[e.target] === 'active'
        const holding = traversed && nodeStatus[e.target] === 'awaiting'
        const settled = traversed && ['done', 'clean', 'findings', 'unresolved'].includes(nodeStatus[e.target])
        const routing = EDGE_ROUTING[`${e.source}-${e.target}`]
        return {
          id: `${e.source}-${e.target}-${e.kind}`,
          source: e.source,
          target: e.target,
          // Margin edges take an explicit detour lane around every box;
          // spine edges step. No labels — dash styles carry the meaning.
          type: routing ? 'detour' : 'smoothstep',
          ...(routing ? { sourceHandle: routing.sourceHandle, targetHandle: routing.targetHandle, data: { laneX: routing.laneX } } : {}),
          animated: live || holding,
          style: {
            stroke: live ? '#f59e0b' : holding ? 'oklch(0.55 0.21 262)' : settled ? '#10b981' : 'var(--border)',
            strokeWidth: live || holding ? 2.5 : settled ? 2 : (style.width ?? 1.5),
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
        onNodesChange={onNodesChange}
        onNodeClick={(_, node) => onNodeClick?.(node.id)}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.16 }}
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
