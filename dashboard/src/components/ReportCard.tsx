// The drafted supervisory report, as a document rather than another card in
// a feed. It is the one artefact a person outside this console reads, so it
// gets a title, a lede, real section headings and room to breathe — and its
// citations stay visible, because "every claim cites a real finding" is the
// guarantee that makes it publishable at all.
import { FileText, ShieldAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { DraftReport } from '@/lib/types'

export function ReportCard({ report, firm, blocked, groundingProblems, signed, onSign }: {
  report: DraftReport
  firm: string
  blocked?: boolean
  groundingProblems?: string[]
  /** A decision is already on the record — no need to ask for one. */
  signed?: boolean
  onSign: () => void
}) {
  return (
    <article className="rounded-xl border bg-card">
      <header className="border-b px-6 py-5">
        <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          <FileText className="size-3.5" />
          Supervisory report · draft
        </p>
        <h2 className="mt-1.5 font-heading text-xl font-semibold leading-tight">{firm}</h2>
        <p className="mt-3 text-[15px] leading-7">{report.overall_assessment}</p>
      </header>

      <div className="flex flex-col gap-6 px-6 py-5">
        {report.sections.map((section, i) => (
          <section key={i}>
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
            {section.cited_finding_ids?.length > 0 && (
              <p className="mt-2 flex flex-wrap gap-1">
                {section.cited_finding_ids.map((id) => (
                  <span key={id} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">{id}</span>
                ))}
              </p>
            )}
          </section>
        ))}

        {report.open_observations_note && (
          <p className="rounded-lg border border-dashed bg-muted/30 px-3.5 py-2.5 text-[13px] leading-6 text-muted-foreground">
            <strong className="font-medium">Unverified observations, not findings.</strong> {report.open_observations_note}
          </p>
        )}
      </div>

      {/* Boolean, not a count: `blocked || problems?.length` is `0` when the
          array is empty, and React renders that 0 on the page. */}
      {(blocked || (groundingProblems?.length ?? 0) > 0) && (
        <div className="border-t border-amber-500/30 bg-amber-500/[0.05] px-6 py-3.5">
          <p className="flex items-center gap-1.5 text-[13px] font-medium text-amber-700 dark:text-amber-400">
            <ShieldAlert className="size-3.5" />
            {blocked ? 'Blocked — the findings remain authoritative' : 'Grounding problems on the last attempt'}
          </p>
          {groundingProblems?.map((p, i) => (
            <p key={i} className="mt-1 text-[12px] leading-5 text-amber-700 dark:text-amber-400">{p}</p>
          ))}
        </div>
      )}

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
