import { useState } from 'react'
import { CheckCheck, Gauge, RotateCw, TriangleAlert, UserRoundCheck, XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { nodeMeta, SPECIALISTS, AGENT_TONE } from '@/lib/node-meta'
import { TIER_TONE } from '@/components/ResultsPanel'
import type { FindingAgent, GateContext, ReviewerDirective, RiskScore } from '@/lib/types'
import { cn } from '@/lib/utils'

export interface GateSubmission {
  action: 'approve' | 'reject' | 'rerun'
  reviewer: string
  comment: string | null
  directive: ReviewerDirective | null
}

export function ReviewGate({
  context,
  onDecide,
  risk,
  findingsCount,
}: {
  context: GateContext
  onDecide: (d: GateSubmission) => void
  /** What this decision issues — restated at the point of sign-off so the
   * officer isn't recalling panels above (recognition over recall). */
  risk?: RiskScore | null
  findingsCount?: number
}) {
  const [reviewer, setReviewer] = useState('')
  const [comment, setComment] = useState('')
  const [instructions, setInstructions] = useState('')
  const [targets, setTargets] = useState<FindingAgent[]>([])

  const named = reviewer.trim().length > 0
  const rerunReady = named && instructions.trim().length > 0 && targets.length > 0

  const decide = (action: GateSubmission['action']) =>
    onDecide({
      action,
      reviewer: reviewer.trim(),
      comment: comment.trim() || null,
      directive:
        action === 'rerun' ? { instructions: instructions.trim(), target_agents: targets } : null,
    })

  const toggleTarget = (agent: FindingAgent) =>
    setTargets((prev) => (prev.includes(agent) ? prev.filter((a) => a !== agent) : [...prev, agent]))

  return (
    <Card className="gap-0 overflow-hidden border-primary/40 p-0 ring-2 ring-primary/15">
      <div className="flex items-center justify-between border-b bg-primary/5 px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <UserRoundCheck className="size-4 text-primary" />
          Reviewer decision required
        </div>
        <span className="text-xs font-medium text-muted-foreground">
          the pipeline is paused — nothing issues without a named sign-off
        </span>
      </div>

      <div className="flex flex-col gap-4 p-4">
        {context.error && (
          <Alert variant="destructive">
            <TriangleAlert />
            <AlertDescription>{context.error}</AlertDescription>
          </Alert>
        )}

        {risk && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border bg-muted/30 px-3.5 py-2.5">
            <span className="flex items-center gap-1.5 text-sm">
              <Gauge className="size-4 text-muted-foreground" />
              <span className="font-mono font-semibold">{risk.total.toFixed(2)}</span>
            </span>
            <Badge variant="outline" className={cn('gap-1 text-xs font-semibold uppercase', TIER_TONE[risk.tier])}>
              {risk.tier_label}
            </Badge>
            <span className="text-sm text-muted-foreground">
              {findingsCount ?? 0} finding{(findingsCount ?? 0) === 1 ? '' : 's'} cited in the report below
            </span>
            <span className="ml-auto font-mono text-[11px] text-muted-foreground">{context.case_id}</span>
          </div>
        )}

        <FieldGroup className="gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field>
              <FieldLabel htmlFor="gate-reviewer">Reviewer</FieldLabel>
              <Input
                id="gate-reviewer"
                placeholder="Your name — recorded with the decision"
                value={reviewer}
                onChange={(e) => setReviewer(e.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="gate-comment">Comment (optional)</FieldLabel>
              <Input id="gate-comment" placeholder="Noted for the record" value={comment} onChange={(e) => setComment(e.target.value)} />
            </Field>
          </div>
        </FieldGroup>

        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => decide('approve')} disabled={!named}>
            <CheckCheck data-icon="inline-start" />
            Approve & issue
          </Button>
          <Button variant="outline" onClick={() => decide('reject')} disabled={!named}>
            <XCircle data-icon="inline-start" />
            Reject
          </Button>
          {!named && <span className="text-xs text-muted-foreground">enter your name to decide</span>}
        </div>

        <div className="rounded-lg border border-dashed p-3.5">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            <RotateCw className="size-3.5" />
            Or send it back with instructions
            <span className="ml-auto font-normal normal-case">
              round {context.reviewer_rounds} of {context.max_reviewer_rounds}
            </span>
          </div>

          {context.rerun_allowed ? (
            <div className="mt-3 flex flex-col gap-3">
              <textarea
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
                placeholder="e.g. Log dismissed structuring — re-check whether the three same-day payments share a beneficiary."
                rows={2}
                className="w-full resize-y rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
              />
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-xs text-muted-foreground">re-examine:</span>
                {SPECIALISTS.map((id) => {
                  const meta = nodeMeta(id)
                  const Icon = meta.icon
                  const active = targets.includes(id)
                  return (
                    <button
                      key={id}
                      type="button"
                      aria-pressed={active}
                      onClick={() => toggleTarget(id)}
                      className={cn(
                        'inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors',
                        active ? AGENT_TONE[meta.color] : 'border-border text-muted-foreground hover:bg-accent/50',
                      )}
                    >
                      <Icon className="size-3" />
                      {meta.label}
                    </button>
                  )
                })}
                <Button size="sm" variant="secondary" className="ml-auto" onClick={() => decide('rerun')} disabled={!rerunReady}>
                  <RotateCw data-icon="inline-start" />
                  Re-analyze
                </Button>
              </div>
              <FieldDescription className="!mt-0">
                The named specialists re-examine the case with your instruction; the score, report, and grounding all
                re-run, then it returns here.
              </FieldDescription>
            </div>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">
              Re-analysis cap reached for this case — approve or reject.
            </p>
          )}
        </div>
      </div>
    </Card>
  )
}
