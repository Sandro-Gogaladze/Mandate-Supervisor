// The drafted supervisory report, as a document rather than another card in
// a feed. It is the one artefact a person outside this console reads, so it
// gets a title, a lede, real section headings and room to breathe — and its
// citations stay visible, because "every claim cites a real finding" is the
// guarantee that makes it publishable at all.
//
// On the Findings tab it sits above the evidence it cites, so its state has
// to be readable in one glance from across a desk: a draft is not a report,
// and a card that looks like every other card cannot say so. The status band
// and the dashed edge carry that; the body stays calm.
//
// Two states, and no third: grounding is advisory (pipeline/graph.py), so a
// draft the validator complained about is a draft like any other and reaches
// the officer the same way. Nothing here is ever withheld.
import { useState } from 'react'
import { CheckCircle2, FileSignature } from 'lucide-react'
import { RunCitation } from '@/components/AgentTurn'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { DraftReport, Finding } from '@/lib/types'

function runRefs(finding: Finding): string[] {
  const value = finding.details.run_refs
  return Array.isArray(value) ? value.filter((run): run is string => typeof run === 'string') : []
}

/** How many run ids a section shows before the rest fold away. A section can
 *  cite twenty executions; printed in full they outweigh the sentence they
 *  are evidence for. */
const RUNS_SHOWN = 8

/** Two columns, not a wrapping row: finding ids run to 50 characters, and a
 *  plain flex-wrap sent the overflow back under the label so the receipt lost
 *  its left edge after the first line. */
function TrailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[3.5rem_1fr] items-baseline gap-x-2 text-[11px]">
      <span className="font-medium text-muted-foreground">{label}</span>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">{children}</div>
    </div>
  )
}

/** The report's prose is intentionally concise. This is the adjacent,
 * structured receipt: every cited claim resolves to the findings behind it,
 * their rules, and any affected execution — one block, not three, so the
 * document reads as prose with a receipt rather than as a ledger export. */
function EvidenceTrail({ findingIds, findings, caseId, onOpenRun }: {
  findingIds: string[]
  findings: Finding[]
  /** Stripped off the ids on screen — every finding in this document belongs
   *  to this case, so the prefix is 20 characters of noise repeated on every
   *  chip. The full id stays in the tooltip. */
  caseId: string
  onOpenRun: (run: string) => void
}) {
  const [allRuns, setAllRuns] = useState(false)
  const cited = findingIds.map((id) => findings.find((finding) => finding.finding_id === id)).filter(Boolean) as Finding[]
  const rules = [...new Set(cited.map((finding) => finding.rule_id).filter((rule): rule is string => Boolean(rule)))]
  const runs = [...new Set(cited.flatMap(runRefs))]
  const shownRuns = allRuns ? runs : runs.slice(0, RUNS_SHOWN)

  if (!findingIds.length) return null
  return (
    <div className="mt-3 rounded-lg border bg-muted/25 px-3 py-2.5">
      <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Evidence trail</div>
      <div className="mt-2 flex flex-col gap-1.5">
        <TrailRow label="Findings">
          {findingIds.map((id) => (
            <span key={id} title={id} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {id.startsWith(`${caseId}:`) ? id.slice(caseId.length + 1) : id}
            </span>
          ))}
        </TrailRow>
        <TrailRow label="Rules">
          {rules.length > 0 ? rules.map((rule) => (
            <span key={rule} className="rounded border bg-background px-1.5 py-0.5 font-mono text-[10px]">{rule}</span>
          )) : <span className="text-muted-foreground">No rule ID recorded</span>}
        </TrailRow>
        <TrailRow label="Runs">
          {shownRuns.length > 0 ? shownRuns.map((run) => <RunCitation key={run} run={run} onOpenRun={onOpenRun} />)
            : <span className="text-muted-foreground">Case-wide finding</span>}
          {runs.length > RUNS_SHOWN && (
            <button
              type="button"
              onClick={() => setAllRuns(!allRuns)}
              className="font-medium text-muted-foreground underline-offset-2 hover:underline"
            >
              {allRuns ? 'show fewer' : `+${runs.length - RUNS_SHOWN} more`}
            </button>
          )}
        </TrailRow>
      </div>
    </div>
  )
}

type ReportState = 'draft' | 'issued'

/** The two states a presentable report can be in, stated in the band across
 *  the top of the document. The wording is the guarantee itself: a draft says
 *  out loud that nothing has left the console. */
const STATE_BAND: Record<ReportState, { icon: typeof CheckCircle2; label: string; note: string; tone: string }> = {
  draft: {
    icon: FileSignature,
    label: 'Draft — not issued',
    note: 'Written by the drafting agent from the findings below, and nothing else. It issues only when an officer signs.',
    tone: 'border-amber-500/35 bg-amber-500/[0.08] text-amber-800 dark:text-amber-300',
  },
  issued: {
    icon: CheckCircle2,
    label: 'Issued',
    note: 'A named supervisory decision is on the record for this case.',
    tone: 'border-emerald-500/35 bg-emerald-500/[0.08] text-emerald-800 dark:text-emerald-300',
  },
}

export function ReportCard({ report, firm, findings, signed, disposition, onSign, onOpenRun }: {
  report: DraftReport
  firm: string
  findings: Finding[]
  /** A decision is already on the record — no need to ask for one. */
  signed?: boolean
  /** The disposition that was signed, when one was. Named in the header so
   *  the document says what it is: a report that has issued is not a draft. */
  disposition?: string
  onSign: () => void
  onOpenRun: (run: string) => void
}) {
  // A signed decision ends the draft.
  const state: ReportState = signed ? 'issued' : 'draft'
  const band = STATE_BAND[state]
  const BandIcon = band.icon
  const citedFindings = new Set(report.sections.flatMap((section) => section.cited_finding_ids ?? [])).size

  return (
    <article
      className={cn(
        // Elevated and, while it is a draft, drawn with a broken edge: the
        // page below it is flat and hairlined, so the document reads as the
        // one thing on this tab that is still waiting on a person.
        'overflow-hidden rounded-xl border bg-card shadow-sm',
        state === 'draft' && 'border-dashed border-amber-500/45',
      )}
    >
      <div className={cn('flex flex-wrap items-baseline gap-x-2.5 gap-y-1 border-b px-6 py-2.5', band.tone)}>
        <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.1em]">
          <BandIcon className="size-3.5 translate-y-0.5" />
          {band.label}
          {state === 'issued' && disposition && <span className="font-mono normal-case tracking-normal">· {disposition}</span>}
        </span>
        <span className="text-[12px] leading-5 opacity-80">{band.note}</span>
      </div>

      <header className="border-b px-6 py-5">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <h2 className="font-heading text-2xl font-semibold tracking-tight">{firm}</h2>
          <span className="font-mono text-[10px] text-muted-foreground">{report.case_id}</span>
        </div>
        {/* Metadata under the title, never a kicker above it — and it counts
            the citations, because the count is the grounding guarantee made
            visible before a single section is read. */}
        <p className="mt-1 text-[12px] text-muted-foreground">
          Supervisory report · {report.sections.length} section{report.sections.length === 1 ? '' : 's'} ·{' '}
          {citedFindings} finding{citedFindings === 1 ? '' : 's'} cited
        </p>
        <p className="mt-3.5 text-[15px] leading-7">{report.overall_assessment}</p>
      </header>

      <div className="flex flex-col gap-6 px-6 py-6">
        {report.sections.map((section, i) => (
          <section key={i} className="grid grid-cols-[1.75rem_1fr] gap-x-1">
            <span className="pt-0.5 font-mono text-[11px] text-muted-foreground/70">
              {String(i + 1).padStart(2, '0')}
            </span>
            <div>
              <h3 className="flex flex-wrap items-center gap-2 font-heading text-[15px] font-semibold">
                {section.title}
                {/* Not decoration: the drafter declares this and the grounding
                    validator checks it against the cited findings' severities,
                    so the badge is a verified claim, not a restatement of the
                    heading. Absent on reports drafted before the field. */}
                {section.character && (
                  <span className={cn(
                    'rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide',
                    section.character === 'adverse' ? 'border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-400'
                      : section.character === 'clear' ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400'
                        : 'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400',
                  )}>
                    {section.character}
                  </span>
                )}
              </h3>
              <p className="mt-1.5 text-[14px] leading-7 text-foreground">{section.body}</p>
              <EvidenceTrail
                findingIds={section.cited_finding_ids ?? []}
                findings={findings}
                caseId={report.case_id}
                onOpenRun={onOpenRun}
              />
            </div>
          </section>
        ))}

        {report.open_observations_note && (
          <p className="rounded-lg border border-dashed bg-muted/30 px-3.5 py-2.5 text-[13px] leading-6 text-muted-foreground">
            <strong className="font-medium">Unverified observations, not findings.</strong> {report.open_observations_note}
          </p>
        )}
      </div>

      <footer className={cn('flex flex-wrap items-center gap-3 border-t px-6 py-3.5',
        signed ? 'text-muted-foreground' : 'bg-muted/30')}>
        {signed ? (
          <p className="text-[13px]">A named decision is on the record for this case.</p>
        ) : (
          <>
            <p className="text-[13px] text-muted-foreground">
              A report cannot issue without a named supervisory decision.
            </p>
            <Button size="sm" className="ml-auto" onClick={onSign}>Sign the decision</Button>
          </>
        )}
      </footer>
    </article>
  )
}
