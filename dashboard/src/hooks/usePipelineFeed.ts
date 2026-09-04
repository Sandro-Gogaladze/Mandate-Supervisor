import { useCallback, useRef, useState } from 'react'
import type { NodeStatus } from '@/components/SupervisionMap'
import { TOOL_AGENT } from '@/lib/humanize'

/** A graph step starting or finishing, folded onto the node the map shows. */
export interface NodeEvent {
  kind: 'node'
  key: string
  node: string
  status: 'inProgress' | 'complete'
  seq: number
  at: number
}

/** One tool call — a specialist or the orchestrator recording its decision.
 * Its arguments are known only once the call ends; nothing is shown before. */
export interface ToolCallEvent {
  kind: 'tool'
  key: string
  node: string
  name: string
  status: 'inProgress' | 'complete'
  args: Record<string, unknown>
  seq: number
  at: number
  endedAt?: number
}

/** The model's own reasoning for one message, when the model returns any. */
export interface ReasoningEvent {
  kind: 'reasoning'
  key: string
  node: string
  messageId: string
  text: string
  done: boolean
  seq: number
  at: number
  endedAt?: number
}

/** Plain text the model wrote outside a tool call (rare here; kept so nothing is lost). */
export interface TextEvent {
  kind: 'text'
  key: string
  node: string
  messageId: string
  text: string
  done: boolean
  seq: number
  at: number
}

export type FeedEvent = NodeEvent | ToolCallEvent | ReasoningEvent | TextEvent

/** Live pipeline state built from the AG-UI agent's step, reasoning, text
 * and tool-call events (CaseReview subscribes via agent.subscribe()). One
 * place because it feeds two views: the map's node lighting and the
 * transcript's live turn. */
export function usePipelineFeed() {
  const [nodeStatus, setNodeStatus] = useState<Record<string, NodeStatus>>({})
  // Last STARTED sequence number per node — the edge-traversal signal:
  // an edge source→target was actually walked only if target started
  // *after* source did. Tracked here (not derived from `events`) because
  // the feed's node rows dedup repeats, so a second start of the same node
  // (escalation round, reviewer rerun) only survives in this map.
  const [nodeStartSeq, setNodeStartSeq] = useState<Record<string, number>>({})
  const [events, setEvents] = useState<FeedEvent[]>([])
  const seqRef = useRef(0)
  const currentNode = useRef<string>('orchestrator')
  // Open tool calls by the stream's own id, with the argument JSON collected
  // so far. The same tool can run twice in one run (an escalation round) and
  // two specialists can be mid-call at once, so a name is not an identity.
  const openTools = useRef<Map<string, { key: string; name: string; json: string }>>(new Map())

  const reset = useCallback(() => {
    setNodeStatus({})
    setNodeStartSeq({})
    setEvents([])
    openTools.current.clear()
    currentNode.current = 'orchestrator'
  }, [])

  /** The step the stream is currently inside, for attribution. */
  const markStep = useCallback((node: string) => {
    currentNode.current = node
  }, [])

  const recordNodeEvent = useCallback((node: string, status: 'inProgress' | 'complete') => {
    seqRef.current += 1
    const seq = seqRef.current
    if (status === 'inProgress') {
      currentNode.current = node
      setNodeStartSeq((prev) => ({ ...prev, [node]: seq }))
    }
    setNodeStatus((prev) => {
      if (prev[node] === (status === 'inProgress' ? 'active' : 'done')) return prev
      return { ...prev, [node]: status === 'inProgress' ? 'active' : 'done' }
    })
    setEvents((prev) => {
      const key = `node:${node}:${status}:${prev.filter((e) => e.kind === 'node' && e.node === node && e.status === status).length}`
      return [...prev, { kind: 'node', key, node, status, seq, at: Date.now() }]
    })
  }, [])

  /** TOOL_CALL_START: one row, attributed by the tool's name (unique per agent). */
  const startTool = useCallback((id: string, name: string) => {
    if (openTools.current.has(id)) return
    seqRef.current += 1
    const key = `tool:${id}`
    openTools.current.set(id, { key, name, json: '' })
    const node = TOOL_AGENT[name] ?? currentNode.current
    setEvents((prev) => [...prev, { kind: 'tool', key, node, name, status: 'inProgress', args: {}, seq: seqRef.current, at: Date.now() }])
  }, [])

  /** TOOL_CALL_ARGS: collected, not rendered — the row shows its arguments once the call ends. */
  const toolArgs = useCallback((id: string, delta: string) => {
    const open = openTools.current.get(id)
    if (open) open.json += delta
  }, [])

  /** TOOL_CALL_END: parse the collected arguments once and close the row. */
  const endTool = useCallback((id: string) => {
    const open = openTools.current.get(id)
    if (!open) return
    openTools.current.delete(id)
    let args: Record<string, unknown> = {}
    try {
      const parsed = JSON.parse(open.json)
      if (parsed && typeof parsed === 'object') args = parsed
    } catch { /* the model's call was cut off; the ledger has what was recorded */ }
    setEvents((prev) => prev.map((e) => (e.kind === 'tool' && e.key === open.key ? { ...e, status: 'complete', args, endedAt: Date.now() } : e)))
  }, [])

  const recordReasoning = useCallback((messageId: string, phase: 'start' | 'delta' | 'end', delta = '') => {
    const node = currentNode.current
    setEvents((prev) => {
      const key = `reasoning:${messageId}`
      const idx = prev.findIndex((e) => e.kind === 'reasoning' && e.key === key)
      if (idx === -1) {
        seqRef.current += 1
        return [...prev, { kind: 'reasoning', key, node, messageId, text: delta, done: phase === 'end', seq: seqRef.current, at: Date.now() }]
      }
      const next = [...prev]
      const current = next[idx] as ReasoningEvent
      next[idx] = { ...current, text: current.text + delta, done: current.done || phase === 'end', ...(phase === 'end' ? { endedAt: Date.now() } : {}) }
      return next
    })
  }, [])

  const recordText = useCallback((messageId: string, phase: 'start' | 'delta' | 'end', delta = '') => {
    const node = currentNode.current
    setEvents((prev) => {
      const key = `text:${messageId}`
      const idx = prev.findIndex((e) => e.kind === 'text' && e.key === key)
      if (idx === -1) {
        seqRef.current += 1
        return [...prev, { kind: 'text', key, node, messageId, text: delta, done: phase === 'end', seq: seqRef.current, at: Date.now() }]
      }
      const next = [...prev]
      const current = next[idx] as TextEvent
      next[idx] = { ...current, text: current.text + delta, done: current.done || phase === 'end' }
      return next
    })
  }, [])

  return { nodeStatus, nodeStartSeq, events, markStep, recordNodeEvent, startTool, toolArgs, endTool, recordReasoning, recordText, reset }
}
