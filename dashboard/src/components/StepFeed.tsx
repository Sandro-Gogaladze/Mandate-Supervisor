import { useEffect, useRef } from 'react'
import { BrainCircuit, CheckCircle2, Cog, Radio } from 'lucide-react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { nodeMeta } from '@/lib/node-meta'
import { cn } from '@/lib/utils'
import type { FeedEvent } from '@/hooks/usePipelineFeed'

function formatArgs(args: unknown): string {
  if (args == null) return ''
  if (typeof args === 'string') return args
  try {
    const s = JSON.stringify(args, null, 2)
    return s === '{}' ? '' : s
  } catch {
    return String(args)
  }
}

const TOOL_STATUS: Record<'inProgress' | 'executing' | 'complete', { label: string; icon: typeof BrainCircuit; tone: string }> = {
  inProgress: { label: 'thinking', icon: BrainCircuit, tone: 'border-amber-500/30 bg-amber-500/5' },
  executing: { label: 'writing', icon: Cog, tone: 'border-amber-500/30 bg-amber-500/5' },
  complete: { label: 'done', icon: CheckCircle2, tone: 'border-emerald-500/30 bg-emerald-500/5' },
}

function ToolRow({ event }: { event: Extract<FeedEvent, { kind: 'tool' }> }) {
  const status = TOOL_STATUS[event.status]
  const StatusIcon = status.icon
  const body = formatArgs(event.args)
  return (
    <div className={cn('rounded-lg border px-3 py-2.5 text-xs transition-colors', status.tone)}>
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 font-mono font-medium text-foreground">
          <StatusIcon className={cn('size-3.5', event.status !== 'complete' && 'animate-pulse text-amber-600')} />
          {event.name}
        </span>
        <Badge variant="outline" className="h-5 gap-1 border-none bg-transparent px-1.5 text-[10px] uppercase text-muted-foreground">
          {status.label}
        </Badge>
      </div>
      {body ? (
        <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md bg-black/[0.03] p-2 font-mono text-[11px] leading-snug text-muted-foreground dark:bg-white/[0.04]">
          {body}
        </pre>
      ) : (
        <div className="mt-1.5 flex gap-1">
          <span className="size-1 animate-pulse rounded-full bg-amber-500 [animation-delay:-0.6s]" />
          <span className="size-1 animate-pulse rounded-full bg-amber-500 [animation-delay:-0.3s]" />
          <span className="size-1 animate-pulse rounded-full bg-amber-500" />
        </div>
      )}
    </div>
  )
}

function NodeRow({ event }: { event: Extract<FeedEvent, { kind: 'node' }> }) {
  const meta = nodeMeta(event.nodeName)
  const Icon = meta.icon
  const finished = event.status === 'complete'
  return (
    <div className="flex items-center gap-2 px-1 py-0.5 text-xs text-muted-foreground">
      <Icon className={cn('size-3.5', finished ? 'text-emerald-600' : 'text-amber-600')} />
      <span className="font-medium text-foreground">{meta.label}</span>
      <span>{finished ? 'finished' : 'started'}</span>
      {finished && <CheckCircle2 className="size-3 text-emerald-500" />}
    </div>
  )
}

export function StepFeed({ events, running }: { events: FeedEvent[]; running: boolean }) {
  const bottomRef = useRef<HTMLDivElement>(null)

  // A "live" feed that doesn't follow new events isn't actually watchable —
  // keeps the newest step in view as it streams in. Scoped to the feed's
  // own ScrollArea viewport: scrollIntoView walks EVERY scrollable
  // ancestor, so during a run each event would also drag the page scroller
  // down here, fighting wherever the officer was actually reading.
  useEffect(() => {
    const viewport = bottomRef.current?.closest('[data-slot="scroll-area-viewport"]')
    if (viewport) viewport.scrollTop = viewport.scrollHeight
    // `events` (not `.length`): a tool call's row updates in place as its
    // arguments stream in — same array length, new content — and should
    // still pull the view down with it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events])

  if (events.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground">
        <Radio className="size-6 text-muted-foreground/40" />
        <p>Run a review to watch the agents work.</p>
      </div>
    )
  }

  return (
    <ScrollArea className="h-full">
      <div className="flex flex-col gap-2 p-3">
        {[...events]
          .sort((a, b) => a.seq - b.seq)
          .map((event) =>
            event.kind === 'tool' ? <ToolRow key={event.key} event={event} /> : <NodeRow key={event.key} event={event} />,
          )}
        {running && (
          <div className="flex items-center gap-1.5 px-1 py-1 text-[11px] text-muted-foreground">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-500 opacity-75" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-amber-500" />
            </span>
            live
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  )
}
