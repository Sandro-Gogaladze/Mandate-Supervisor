// The officer's line to the orchestrator (architecture-v2 §14.2). One
// message per send: the orchestrator routes it — a reply from the record, a
// lookup by the investigator, or a specialist re-examined with the concern
// as its briefing. Everything lands in the ledger; this surface just shows
// the conversation.
import { useState } from 'react'
import { CornerDownLeft, Loader2, MessageCircleQuestion, Waypoints } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'

export interface SessionExchange {
  question: string
  reply: string | null // null while in flight
}

export function QuestionBox({
  exchanges,
  running,
  onAsk,
}: {
  exchanges: SessionExchange[]
  running: boolean
  onAsk: (question: string) => void
}) {
  const [draft, setDraft] = useState('')

  const send = () => {
    const question = draft.trim()
    if (!question || running) return
    setDraft('')
    onAsk(question)
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {exchanges.length === 0 ? (
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 p-6 text-center text-sm text-muted-foreground">
          <MessageCircleQuestion className="size-6 text-muted-foreground/40" />
          <p className="max-w-sm">
            Ask the orchestrator about this case — it answers from the record, sends the investigator to
            look something up, or re-briefs a specialist. Every dispatch is written to the ledger.
          </p>
        </div>
      ) : (
        <ScrollArea className="min-h-0 flex-1">
          <div className="flex flex-col gap-3 p-4">
            {exchanges.map((exchange, i) => (
              <div key={i} className="flex flex-col gap-1.5">
                <div className="self-end rounded-lg rounded-br-sm bg-primary/10 px-3 py-2 text-sm text-foreground">
                  {exchange.question}
                </div>
                <div
                  className={cn(
                    'flex items-start gap-2 self-start rounded-lg rounded-bl-sm border px-3 py-2 text-sm',
                    exchange.reply === null && 'text-muted-foreground',
                  )}
                >
                  <Waypoints className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
                  {exchange.reply === null ? (
                    <span className="flex items-center gap-1.5">
                      <Loader2 className="size-3 animate-spin" />
                      routing…
                    </span>
                  ) : (
                    <span className="leading-relaxed">{exchange.reply}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>
      )}
      <div className="flex items-end gap-2 border-t p-3">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send()
            }
          }}
          placeholder="e.g. Has this counterparty appeared in any other firm's history?"
          rows={2}
          className="min-h-9 flex-1 resize-none rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
        />
        <Button size="sm" onClick={send} disabled={running || !draft.trim()}>
          {running ? <Loader2 className="animate-spin" /> : <CornerDownLeft />}
          Ask
        </Button>
      </div>
    </div>
  )
}
