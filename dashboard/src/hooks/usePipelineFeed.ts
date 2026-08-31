import { useCallback, useRef, useState } from 'react'
import type { NodeStatus } from '@/components/PipelineGraph'

export interface ToolCallEvent {
  kind: 'tool'
  key: string
  name: string
  status: 'inProgress' | 'executing' | 'complete'
  args: unknown
  seq: number
}

export interface NodeEvent {
  kind: 'node'
  key: string
  nodeName: string
  status: 'inProgress' | 'complete'
  seq: number
}

export type FeedEvent = ToolCallEvent | NodeEvent

/** Live pipeline state built from the AG-UI agent's step/tool-call events
 * (CaseReview subscribes via agent.subscribe()) — kept in one place since
 * both feed the same two views: the React Flow node highlighting and the
 * step feed list. */
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
  const openToolKeyByName = useRef<Map<string, string>>(new Map())

  const reset = useCallback(() => {
    setNodeStatus({})
    setNodeStartSeq({})
    setEvents([])
    openToolKeyByName.current.clear()
  }, [])

  const recordNodeEvent = useCallback((nodeName: string, status: 'inProgress' | 'complete') => {
    seqRef.current += 1
    const seq = seqRef.current
    if (status === 'inProgress') {
      setNodeStartSeq((prev) => ({ ...prev, [nodeName]: seq }))
    }
    setNodeStatus((prev) => {
      if (prev[nodeName] === (status === 'inProgress' ? 'active' : 'done')) return prev
      return { ...prev, [nodeName]: status === 'inProgress' ? 'active' : 'done' }
    })
    setEvents((prev) => {
      const key = `node:${nodeName}:${status}`
      if (prev.some((e) => e.kind === 'node' && e.key === key)) return prev
      return [...prev, { kind: 'node', key, nodeName, status, seq }]
    })
  }, [])

  const recordToolEvent = useCallback((name: string, status: 'inProgress' | 'executing' | 'complete', args: unknown) => {
    setEvents((prev) => {
      const openKey = openToolKeyByName.current.get(name)
      if (openKey) {
        const idx = prev.findIndex((e) => e.kind === 'tool' && e.key === openKey)
        if (idx !== -1) {
          const next = [...prev]
          next[idx] = { ...(next[idx] as ToolCallEvent), status, args }
          if (status === 'complete') openToolKeyByName.current.delete(name)
          return next
        }
      }
      seqRef.current += 1
      const key = `tool:${name}:${seqRef.current}`
      if (status !== 'complete') openToolKeyByName.current.set(name, key)
      return [...prev, { kind: 'tool', key, name, status, args, seq: seqRef.current }]
    })
  }, [])

  return { nodeStatus, nodeStartSeq, events, recordNodeEvent, recordToolEvent, reset }
}
