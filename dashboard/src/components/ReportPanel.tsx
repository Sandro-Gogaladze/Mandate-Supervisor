import { CheckCheck, Eye, FileText, RotateCw, ShieldAlert, XCircle } from 'lucide-react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Separator } from '@/components/ui/separator'
import type { SupervisionAgentState } from '@/lib/agent-state'

export function reportStatus(state: SupervisionAgentState, gateOpen = false): string | undefined {
  if (state.report_status === 'issued') return 'issued ✓'
  if (state.report_status === 'rejected') return 'rejected'
  if (state.report_blocked) return 'blocked — findings remain authoritative'
  if (state.draft_report && !(state.grounding_problems?.length)) {
    return gateOpen ? 'grounded ✓ · awaiting reviewer' : 'grounded ✓'
  }
  if (state.grounding_problems?.length) return `regenerating · attempt ${state.draft_attempts ?? 1}`
  return undefined
}

const DECISION_ICON = { approve: CheckCheck, reject: XCircle, rerun: RotateCw } as const
const DECISION_TEXT = {
  approve: 'approved & issued the report',
  reject: 'rejected the report',
  rerun: 'sent the case back for re-analysis',
} as const

function DecisionTrail({ state }: { state: SupervisionAgentState }) {
  const decisions = state.reviewer_decisions ?? []
  if (decisions.length === 0) return null
  return (
    <div className="rounded-lg border bg-muted/30 p-3.5">
      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Decision record</div>
      <div className="mt-2 flex flex-col gap-1.5">
        {decisions.map((d, i) => {
          const Icon = DECISION_ICON[d.action]
          return (
            <div key={i} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-[13px]">
              <Icon className="size-3.5 translate-y-0.5 text-muted-foreground" />
              <span className="font-medium">{d.reviewer}</span>
              <span className="text-muted-foreground">{DECISION_TEXT[d.action]}</span>
              {d.action === 'rerun' && d.directive && (
                <span className="text-muted-foreground">
                  → {d.directive.target_agents.join(', ')}: “{d.directive.instructions}”
                </span>
              )}
              {d.comment && <span className="italic text-muted-foreground">“{d.comment}”</span>}
              <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                {new Date(d.decided_at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function ReportPanel({ state }: { state: SupervisionAgentState }) {
  const report = state.draft_report

  if (!report) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-sm text-muted-foreground">
        <FileText className="size-6 text-muted-foreground/40" />
        <p>The drafting agent writes its report once the specialists finish.</p>
      </div>
    )
  }

  // CLAUDE.md's block rule: prose that failed grounding twice is never
  // presented as a report. The officer sees why, and the findings panel
  // stays the authoritative record. The decision record still renders —
  // reviewer directives that led here must not vanish with the prose.
  if (state.report_blocked) {
    return (
      <div className="flex flex-col gap-4 p-4">
        <Alert variant="destructive">
          <ShieldAlert />
          <AlertTitle>Draft blocked — failed grounding validation</AlertTitle>
          <AlertDescription>
            <p>
              The drafting agent could not produce a report where every claim cites a real finding, after the maximum
              number of regenerations. Its prose is withheld; the findings below remain the authoritative record.
            </p>
            <ul className="mt-2 ml-4 flex list-disc flex-col gap-1 font-mono text-xs">
              {(state.grounding_problems ?? []).map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
        <DecisionTrail state={state} />
      </div>
    )
  }

  // The receipt that persists after the toast: who signed, when, what
  // happened — the end state of the officer's gravest act, stated plainly.
  const lastDecision = (state.reviewer_decisions ?? []).filter((d) => d.action !== 'rerun').at(-1)

  return (
    <ScrollArea className="h-full">
      <div className="flex flex-col gap-4 p-5">
        {state.report_status === 'issued' && (
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-3.5 py-2.5 text-sm">
            <CheckCheck className="size-4 text-emerald-600 dark:text-emerald-400" />
            <span className="font-semibold text-emerald-800 dark:text-emerald-300">Report issued</span>
            {lastDecision && (
              <span className="text-emerald-800/80 dark:text-emerald-400/80">
                signed by {lastDecision.reviewer} ·{' '}
                {new Date(lastDecision.decided_at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
          </div>
        )}
        {state.report_status === 'rejected' && (
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border bg-muted/40 px-3.5 py-2.5 text-sm">
            <XCircle className="size-4 text-muted-foreground" />
            <span className="font-semibold">Report rejected — not issued</span>
            {lastDecision && (
              <span className="text-muted-foreground">
                by {lastDecision.reviewer} · the findings remain on record
              </span>
            )}
          </div>
        )}

        <p className="font-heading text-[15px] font-medium leading-relaxed">{report.overall_assessment}</p>

        {report.sections.map((section, i) => (
          <div key={i}>
            <Separator className="mb-4" />
            <h3 className="text-sm font-semibold">{section.title}</h3>
            <p className="mt-1.5 text-sm leading-relaxed text-foreground/90">{section.body}</p>
            {section.cited_finding_ids.length > 0 && (
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">cites</span>
                {section.cited_finding_ids.map((fid) => (
                  <Badge key={fid} variant="outline" className="h-5 px-1.5 font-mono text-[10px] font-normal">
                    {fid}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        ))}

        {report.open_observations_note && (
          <div className="rounded-lg border border-dashed bg-muted/30 p-3.5">
            <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              <Eye className="size-3.5" />
              Unverified observations — for officer judgment, not findings
            </div>
            <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{report.open_observations_note}</p>
          </div>
        )}

        <DecisionTrail state={state} />
      </div>
    </ScrollArea>
  )
}
