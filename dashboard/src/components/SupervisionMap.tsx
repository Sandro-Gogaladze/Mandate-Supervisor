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
  useNodesInitialized,
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

// ---------------------------------------------------------------------------
// Geometry. The bench is a 4-column grid; everything else is a centred spine.
// Every long edge is routed orthogonally through a named CHANNEL that is
// clear of every box, so no line ever passes under a node. Channels are
// spaced so two lines sharing a corridor stay visibly apart.
// ---------------------------------------------------------------------------
const W_WORKER = 122
const W_SPINE = 196
const H_WORKER = 91
const H_SPINE = 54
const COLS = 4
const COL_PITCH = 154 // 122 wide + a 32px gutter that carries one channel
const ROW_PITCH = 135 // 91 tall + a 44px gap, which carries two rails
const ROW_TOP = 214
const SPINE_PITCH = 76 // 53 tall + a 23px step; tighter than the bench's
const GRID_W = (COLS - 1) * COL_PITCH + W_WORKER
const SPINE_X = Math.round((GRID_W - W_SPINE) / 2)
const ORCH_Y = 92

// Vertical channels, left of the bench then right of it. Nothing is drawn
// between them except the grid itself, so these never cross a box.
// Two trunks flank the bench and nothing crosses it: work goes OUT down the
// left, results come BACK up the right. Every specialist therefore has exactly
// one line in at its top and one out at its bottom.
const LANE_SUP = -114 // orchestrator → supervisor
const LANE_RETURN = -78 // the join's short-circuit back to the orchestrator
const LANE_DISPATCH = -36 // orchestrator → every specialist
const LANE_COLLECT = GRID_W + 40 // every specialist → the join
const LANE_LOOP = SPINE_X + W_SPINE + 26 // grounding check → draft report
const LANE_SYNTH = GRID_W + 78 // synthesizer → orchestrator
const LANE_DRAFT = GRID_W + 116 // orchestrator → draft report

const DIMMED_IDS = new Set(['investigator', 'systemic'])
const SPINE_ORDER = ['specialists_done', 'control_assurance', 'findings', 'synthesizer', 'draft_report', 'grounding_check', 'human_gate']

/** One orthogonal move. The router walks these from the source point, then
 *  closes the last leg onto the target. */
type Step = { axis: 'x' | 'y'; v: number }
type Route = { sourceHandle?: string; targetHandle?: string; steps: Step[] }

function buildGeometry(map: FullMap) {
  const peers = map.nodes.filter((n) => n.role === 'peer')
  const requested = map.nodes.filter((n) => n.role === 'on_request')
  const peerRows = Math.max(1, Math.ceil(peers.length / COLS))
  const cell: Record<string, { col: number; row: number }> = {}
  peers.forEach((n, i) => { cell[n.id] = { col: i % COLS, row: Math.floor(i / COLS) } })
  requested.forEach((n, i) => { cell[n.id] = { col: i % COLS, row: peerRows + Math.floor(i / COLS) } })
  const rows = peerRows + Math.ceil(requested.length / COLS)

  const positions: Record<string, { x: number; y: number }> = {
    supervisor: { x: SPINE_X, y: 0 },
    orchestrator: { x: SPINE_X, y: ORCH_Y },
  }
  Object.entries(cell).forEach(([id, { col, row }]) => {
    positions[id] = { x: col * COL_PITCH, y: ROW_TOP + row * ROW_PITCH }
  })
  const benchBottom = ROW_TOP + (rows - 1) * ROW_PITCH + H_WORKER
  // The collector is the horizontal the bench's drop channels land on; the
  // join node sits just under it, so every specialist's single outgoing edge
  // reads as one flow down into the barrier.
  const collectorY = benchBottom + 30
  // Only the spine nodes this map actually carries get a slot. Reserving one
  // for a node the backend didn't send (an API still running older code, say)
  // leaves a hole and drops everything below it by a full step.
  const present = new Set(map.nodes.map((n) => n.id))
  const spine = SPINE_ORDER.filter((id) => present.has(id))
  const gapBefore = spine.indexOf('draft_report')
  const spineY = (i: number) => collectorY + 30 + i * SPINE_PITCH + (gapBefore >= 0 && i >= gapBefore ? 30 : 0)
  spine.forEach((id, i) => { positions[id] = { x: SPINE_X, y: spineY(i) } })
  // Anything the backend adds later gets its own row rather than stacking at 0,0.
  map.nodes.filter((n) => !positions[n.id]).forEach((n, i) => {
    positions[n.id] = { x: SPINE_X, y: spineY(spine.length + i) }
  })

  const mid = (id: string) => positions[id].y + (cell[id] ? H_WORKER : H_SPINE) / 2
  // Each 44px row gap carries two rails, 16px apart: the row below being
  // dispatched to, and the row above handing its results out to the right.
  const dispatchRailY = (row: number) => ROW_TOP + row * ROW_PITCH - 14
  const collectRailY = (row: number) => ROW_TOP + row * ROW_PITCH + H_WORKER + 14

  const routes: Record<string, Route> = {}
  for (const e of map.edges) {
    const key = `${e.source}-${e.target}`
    const from = cell[e.source]
    const to = cell[e.target]
    if (e.source === 'orchestrator' && to) {
      // Down the dispatch trunk, along this row's bus, into the box's top.
      routes[key] = { sourceHandle: 'bs', targetHandle: 'tt', steps: [{ axis: 'y', v: ORCH_Y + H_SPINE + 18 }, { axis: 'x', v: LANE_DISPATCH }, { axis: 'y', v: dispatchRailY(to.row) }] }
    } else if (from && e.target === 'specialists_done') {
      // A specialist's one outgoing edge: straight down out of the box into
      // the rail under its row, right to the collect trunk, down to the join.
      routes[key] = { sourceHandle: 'bs', targetHandle: 'tt', steps: [{ axis: 'y', v: collectRailY(from.row) }, { axis: 'x', v: LANE_COLLECT }, { axis: 'y', v: collectorY }] }
    } else if (from && e.target === 'control_assurance') {
      // Legacy shape (backend without the join drawn): route it like a
      // collection edge rather than letting it fall through to the spine.
      routes[key] = { sourceHandle: 'bs', targetHandle: 'tt', steps: [{ axis: 'y', v: collectRailY(from.row) }, { axis: 'x', v: LANE_COLLECT }, { axis: 'y', v: collectorY }] }
    } else if (from && e.target === 'orchestrator') {
      // Legacy shape: the phantom per-specialist return. Send it round the
      // left trunk instead of straight up the middle.
      routes[key] = { sourceHandle: 'bs', targetHandle: 'lt', steps: [{ axis: 'y', v: collectRailY(from.row) + 16 }, { axis: 'x', v: LANE_RETURN }, { axis: 'y', v: mid('orchestrator') }] }
    } else if (key === 'specialists_done-orchestrator') {
      // The join's conditional short-circuit — the only edge in the bench that
      // goes back to the orchestrator.
      routes[key] = { sourceHandle: 'ls', targetHandle: 'lt', steps: [{ axis: 'x', v: LANE_RETURN }, { axis: 'y', v: mid('orchestrator') }] }
    } else if (key === 'orchestrator-control_assurance') {
      // Down the same dispatch trunk, in through the side: the top of this box
      // belongs to the ten collection edges.
      routes[key] = { sourceHandle: 'bs', targetHandle: 'lt', steps: [{ axis: 'y', v: ORCH_Y + H_SPINE + 18 }, { axis: 'x', v: LANE_DISPATCH }, { axis: 'y', v: mid('control_assurance') }] }
    } else if (key === 'orchestrator-supervisor') {
      routes[key] = { sourceHandle: 'ls', targetHandle: 'lt', steps: [{ axis: 'x', v: LANE_SUP }, { axis: 'y', v: mid('supervisor') }] }
    } else if (key === 'synthesizer-orchestrator') {
      routes[key] = { sourceHandle: 'rs', targetHandle: 'rt', steps: [{ axis: 'x', v: LANE_SYNTH }, { axis: 'y', v: mid('orchestrator') }] }
    } else if (key === 'orchestrator-draft_report') {
      // Arrives on the TOP so it never runs collinear with the grounding loop.
      routes[key] = { sourceHandle: 'bs', targetHandle: 'tt', steps: [{ axis: 'y', v: ORCH_Y + H_SPINE + 18 }, { axis: 'x', v: LANE_DRAFT }, { axis: 'y', v: positions.draft_report.y - 24 }] }
    } else if (key === 'grounding_check-draft_report') {
      routes[key] = { sourceHandle: 'rs', targetHandle: 'rt', steps: [{ axis: 'x', v: LANE_LOOP }, { axis: 'y', v: mid('draft_report') }] }
    } else {
      routes[key] = { sourceHandle: 'bs', targetHandle: 'tt', steps: [] } // spine hops: straight down
    }
  }
  return { positions, routes }
}

// One-line captions under each node's name while idle.
const CAPTIONS: Record<string, string> = {
  supervisor: 'you',
  specialists_done: 'join point',
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
        style={{ width: W_WORKER }}
      >
        <Handle id="tt" type="target" position={Position.Top} className="!h-2 !w-2 !border !border-card !bg-muted-foreground/50" />
      <Handle id="lt" type="target" position={Position.Left} className="!h-1.5 !w-1.5 !border-0 !bg-transparent" />
      <Handle id="ls" type="source" position={Position.Left} className="!h-1.5 !w-1.5 !border-0 !bg-transparent" />
      <Handle id="rt" type="target" position={Position.Right} className="!h-1.5 !w-1.5 !border-0 !bg-transparent" />
      <Handle id="rs" type="source" position={Position.Right} className="!h-1.5 !w-1.5 !border-0 !bg-transparent" />
        <div className={cn('flex size-8 items-center justify-center rounded-lg transition-colors duration-300', iconWrap)}>
          <Icon className="size-4.5" strokeWidth={2.25} />
        </div>
        <div className={cn('max-w-full truncate text-[12px] font-semibold', data.status === 'pending' ? 'text-muted-foreground' : 'text-foreground')}>
          {data.label}
        </div>
        <div className="truncate text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          {data.status === 'active' ? 'working…' : data.status === 'findings' ? 'returned · findings' : data.status === 'unresolved' ? 'returned · unresolved' : data.status === 'clean' ? 'returned · clean' : data.status === 'done' ? 'complete' : dimmed ? 'on request' : 'ready'}
        </div>
        {statusDot}
        <Handle id="bs" type="source" position={Position.Bottom} className="!h-2 !w-2 !border !border-card !bg-muted-foreground/50" />
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
      style={{ width: W_SPINE }}
    >
      <Handle id="tt" type="target" position={Position.Top} className="!h-2 !w-2 !border !border-card !bg-muted-foreground/50" />
      <Handle id="lt" type="target" position={Position.Left} className="!h-1.5 !w-1.5 !border-0 !bg-transparent" />
      <Handle id="ls" type="source" position={Position.Left} className="!h-1.5 !w-1.5 !border-0 !bg-transparent" />
      <Handle id="rt" type="target" position={Position.Right} className="!h-1.5 !w-1.5 !border-0 !bg-transparent" />
      <Handle id="rs" type="source" position={Position.Right} className="!h-1.5 !w-1.5 !border-0 !bg-transparent" />
      <div className={cn('flex size-7 shrink-0 items-center justify-center rounded-lg transition-colors duration-300', iconWrap)}>
        <Icon className="size-4" strokeWidth={2.25} />
      </div>
      <div className="min-w-0 flex-1">
        <div className={cn('truncate text-[13px] font-semibold', data.status === 'pending' && !data.synthetic ? 'text-muted-foreground' : 'text-foreground')}>
          {data.label}
        </div>
        <div className="truncate text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
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
      <Handle id="bs" type="source" position={Position.Bottom} className="!h-2 !w-2 !border !border-card !bg-muted-foreground/50" />
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
const edgeTypes = { ortho: OrthoEdge }

/** Draws an orthogonal polyline with rounded corners: the source point, the
 *  route's channel waypoints, then an L onto the target.
 *
 *  `tail` is the straight run the path must keep before the target. An
 *  arrowhead is ~9px long and is oriented by the LAST segment, so a corner
 *  rounded to within a few pixels of the endpoint leaves the head sitting on
 *  the curve — it reads as bent or tilted even when its angle is right. The
 *  last corner therefore gives up radius rather than tail. */
function roundedPath(points: { x: number; y: number }[], r = 11, tail = 10) {
  const p = points.filter((pt, i) => i === 0 || Math.abs(pt.x - points[i - 1].x) > 0.5 || Math.abs(pt.y - points[i - 1].y) > 0.5)
  if (p.length < 2) return ''
  let d = `M ${p[0].x} ${p[0].y}`
  for (let i = 1; i < p.length - 1; i++) {
    const prev = p[i - 1]
    const cur = p[i]
    const next = p[i + 1]
    const out = Math.hypot(next.x - cur.x, next.y - cur.y)
    const last = i === p.length - 2
    const rr = Math.min(r, Math.hypot(cur.x - prev.x, cur.y - prev.y) / 2, last ? Math.max(0, out - tail) : out / 2)
    const a = { x: cur.x - Math.sign(cur.x - prev.x) * rr, y: cur.y - Math.sign(cur.y - prev.y) * rr }
    const b = { x: cur.x + Math.sign(next.x - cur.x) * rr, y: cur.y + Math.sign(next.y - cur.y) * rr }
    d += ` L ${a.x} ${a.y} Q ${cur.x} ${cur.y} ${b.x} ${b.y}`
  }
  d += ` L ${p[p.length - 1].x} ${p[p.length - 1].y}`
  return d
}

/** A direction chevron placed on an edge's longest straight run. A single
 *  arrowhead at the far end of a trunk that crosses the whole map does not
 *  tell you which way the work is flowing; this does, at the point the eye
 *  actually lands on. */
function DirectionMark({ points, color }: { points: { x: number; y: number }[]; color: string }) {
  let best = 0
  let len = 0
  for (let i = 1; i < points.length; i++) {
    const d = Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y)
    if (d > len) { len = d; best = i }
  }
  if (len < 46) return null
  const a = points[best - 1]
  const b = points[best]
  const cx = (a.x + b.x) / 2
  const cy = (a.y + b.y) / 2
  const angle = (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI
  return (
    <path
      d="M -4 -4.5 L 4.5 0 L -4 4.5 Z"
      fill={color}
      transform={`translate(${cx} ${cy}) rotate(${angle})`}
      style={{ pointerEvents: 'none' }}
    />
  )
}

function OrthoEdge({ sourceX, sourceY, targetX, targetY, targetPosition, style, markerEnd, data }: EdgeProps) {
  const steps = ((data as { steps?: Step[] } | undefined)?.steps) ?? []
  const pts = [{ x: sourceX, y: sourceY }]
  let cur = { x: sourceX, y: sourceY }
  for (const s of steps) {
    cur = s.axis === 'x' ? { x: s.v, y: cur.y } : { x: cur.x, y: s.v }
    pts.push(cur)
  }
  // Close onto the target along the axis its HANDLE faces, not always
  // vertically. Endpoints come from React Flow — the real measured handle —
  // while a route's last step aims at this file's assumed box centre, and the
  // two disagree by a fraction of a pixel. Closing a side-entry edge with the
  // old "across, then down" turned that fraction into a final vertical stub
  // under a pixel long: the arrowhead orients off the last segment, so it
  // pointed up or down into a box the line reached horizontally.
  const sideways = targetPosition === Position.Left || targetPosition === Position.Right
  const lastAxis = steps.length ? steps[steps.length - 1].axis : undefined
  if (sideways) {
    // Land the trunk exactly on the handle's row, then run in flat.
    if (lastAxis === 'y') pts[pts.length - 1] = { x: cur.x, y: targetY }
    else if (Math.abs(cur.y - targetY) > 0.5) pts.push({ x: cur.x, y: targetY })
  } else if (Math.abs(cur.x - targetX) > 0.5) {
    pts.push({ x: targetX, y: cur.y })
  }
  pts.push({ x: targetX, y: targetY })
  // Belt and braces for any route whose own steps already land on the target:
  // a final leg too short to orient an arrowhead is dropped, so the head takes
  // its angle from the run the eye actually sees.
  const n = pts.length
  if (n >= 3 && Math.hypot(pts[n - 1].x - pts[n - 2].x, pts[n - 1].y - pts[n - 2].y) < 2) pts.splice(n - 2, 1)
  const lit = (data as { lit?: boolean } | undefined)?.lit
  return (
    <>
      <BaseEdge path={roundedPath(pts)} style={style} markerEnd={markerEnd} />
      {lit && <DirectionMark points={pts} color={String(style?.stroke ?? 'currentColor')} />}
    </>
  )
}

const EDGE_STYLE: Record<MapEdgeKind, { dash?: string; opacity: number; width?: number }> = {
  main: { opacity: 1 },
  route: { dash: '6 4', opacity: 0.95, width: 2 },
  loop: { dash: '3 4', opacity: 0.8 },
  return: { dash: '4 4', opacity: 0.9, width: 2 },
}

/** React Flow's `fitView` prop only runs at init, so the map stayed fitted to
 *  whatever size the container had on mount — opening it in a dialog, or
 *  resizing the rail, left it cropped and off-centre. Refit whenever the
 *  container's box actually changes; panning and zooming don't trigger this. */
function AutoFit() {
  const { fitBounds, getNodesBounds, getNodes } = useReactFlow()
  // Wait for measurement. Fitting before React Flow has measured anything
  // hands it a degenerate bounds and leaves the flow wedged with
  // nodesInitialized false — nodes stay hidden and, since edges need handle
  // bounds at both ends, not one edge renders.
  const initialized = useNodesInitialized()
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const host = ref.current?.closest('.react-flow')
    if (!host || !initialized) return
    let raf = 0
    const fit = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        const ns = getNodes()
        if (ns.length) fitBounds(getNodesBounds(ns), { padding: 0.05 })
      })
    }
    const ro = new ResizeObserver(fit)
    ro.observe(host)
    return () => { ro.disconnect(); cancelAnimationFrame(raf) }
  }, [initialized, fitBounds, getNodes, getNodesBounds])
  return <div ref={ref} className="hidden" />
}

function MapControls() {
  const { zoomIn, zoomOut, fitBounds, getNodesBounds, getNodes } = useReactFlow()
  // fitView() only QUEUES on a fully-static graph — fitBounds sets the
  // viewport directly (the React Flow v12 trap found in phase 10).
  const fit = () => fitBounds(getNodesBounds(getNodes()), { padding: 0.05, duration: 200 })
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
  const geo = useMemo(() => buildGeometry(map), [map])
  useEffect(() => {
    const { positions } = geo
    setNodes(map.nodes.map((n) => ({
      id: n.id,
      type: 'mapNode',
      position: positions[n.id],
      data: { nodeId: n.id, label: n.label, status: latestStatus.current[n.id] ?? 'pending', synthetic: n.synthetic, worker: n.role === 'peer' || n.role === 'on_request' },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    })))
  }, [map, geo, setNodes])
  useEffect(() => {
    // Return the SAME array when no status moved. `current.map()` always
    // allocates, so handing React Flow a fresh array on every render restarted
    // its node measurement each time — nodes stayed `measured: {}` with null
    // handleBounds, which React Flow renders as visibility:hidden boxes and,
    // because edges need handle bounds at both ends, as no edges at all.
    setNodes((current) => {
      let changed = false
      const next = current.map((n) => {
        const status = nodeStatus[n.id] ?? 'pending'
        if (n.data.status === status) return n
        changed = true
        return { ...n, data: { ...n.data, status } }
      })
      return changed ? next : current
    })
  }, [nodeStatus, setNodes])

  const edges = useMemo<Edge[]>(
    () =>
      map.edges.map((e) => {
        const style = EDGE_STYLE[e.kind]
        // The supervisor is synthetic and never emits a step, but it is where
        // every run starts — seq 0 — so the officer's own hand-off to the
        // orchestrator can light like any other traversal.
        const seqOf = (id: string) => (id === 'supervisor' ? 0 : nodeStartSeq[id])
        const sourceStart = seqOf(e.source)
        const targetStart = seqOf(e.target)
        const traversed = sourceStart !== undefined && targetStart !== undefined && targetStart > sourceStart
        const target = nodeStatus[e.target]
        // An edge takes the colour of the box it ENTERS, from the same tokens
        // that box's ring uses — a red-ringed node can never be fed by a green
        // line again. Untraversed edges stay at the idle border colour.
        // Only a path the run WALKED lights. Lighting every edge that enters an
        // active node lit the join's short-circuit and the synthesizer's return
        // the moment the orchestrator picked up a question — three arms wrapped
        // round an idle bench, none of them being used. The gate is the one
        // exception: it holds without emitting a step, so the edge that reached
        // it lights from a source that did run.
        const lit = traversed || (target === 'awaiting' && sourceStart !== undefined)
        const tone = !lit
          ? 'var(--map-idle)'
          : target === 'active'
            ? 'var(--map-live)'
            : target === 'awaiting'
              ? 'var(--map-await)'
              : target === 'findings'
                ? 'var(--map-findings)'
                : target === 'unresolved'
                  ? 'var(--map-unresolved)'
                  : ['done', 'clean'].includes(target)
                    ? 'var(--map-clean)'
                    : 'var(--map-idle)'
        // A path being walked right now reads heaviest, one already walked
        // stays solid-ish, everything untaken recedes to the border colour.
        const moving = target === 'active' || target === 'awaiting'
        const weight = moving ? 2.6 : traversed ? 2.2 : (style.width ?? 1.5)
        const routing = geo.routes[`${e.source}-${e.target}`]
        // The join's conditional escape (taken only when the pass dispatched no
        // peer at all) is real, so it stays on the map — but on any normal run
        // it is a road not travelled, and it should read as one.
        const faint = `${e.source}-${e.target}` === 'specialists_done-orchestrator' && !lit
        return {
          id: `${e.source}-${e.target}-${e.kind}`,
          source: e.source,
          target: e.target,
          // Every edge is orthogonal and channel-routed; dash styles carry the
          // kind (main / route / loop / return), so no labels are needed.
          type: 'ortho',
          sourceHandle: routing?.sourceHandle,
          targetHandle: routing?.targetHandle,
          data: { steps: routing?.steps ?? [], lit },
          animated: moving,
          style: {
            stroke: tone,
            strokeWidth: faint ? 1 : weight,
            strokeDasharray: style.dash,
            opacity: faint ? 0.22 : lit ? 1 : style.opacity,
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: faint ? 9 : lit ? 20 : 16,
            height: faint ? 9 : lit ? 20 : 16,
            color: lit ? tone : 'var(--map-arrow-idle)',
          },
        }
      }),
    [map.edges, nodeStatus, nodeStartSeq, geo],
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
        fitViewOptions={{ padding: 0.05 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        zoomOnScroll={true}
        panOnDrag={true}
        minZoom={0.25}
        maxZoom={2}
      >
        <Background gap={20} size={1} className="opacity-60" />
        <AutoFit />
        <MapControls />
      </ReactFlow>
    </div>
  )
}
