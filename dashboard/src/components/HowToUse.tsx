import { useState } from 'react'
import {
  BadgeCheck,
  BookOpen,
  FileText,
  FlaskConical,
  HelpCircle,
  MessageSquareText,
  Play,
  Upload,
  UserRound,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

/** One step of the review loop. `where` names the control by the label
 * actually printed on it, so a first-time reader can find it without
 * guessing which of two similar buttons is meant. `optional` marks the two
 * steps a reader can skip entirely — worth saying, because a numbered list
 * otherwise reads as five things you must do before a case can be signed. */
const REVIEW: { icon: typeof Upload; title: string; where: string; body: string; optional?: boolean }[] = [
  {
    icon: Upload,
    title: 'File the evidence',
    where: 'Overview → New submission',
    optional: true,
    body: 'Only if you are bringing new evidence. The Cases queue already holds filed submissions — to review one of those, skip straight to step 2. To file: one agent’s evidence as a single ZIP — the dossier, one file per run, and the wider transaction ledger. “What goes in the ZIP” inside that window has the exact structure. Every signature and hash chain is checked before a case opens; a broken archive is rejected with the reason, never reviewed half-verified.',
  },
  {
    icon: Play,
    title: 'Run the review',
    where: 'Cases → open one → Run',
    body: 'Ten specialists go over the whole dossier against the rulebook in force. Watch the lanes light up on the supervision map, or just wait for the findings. Facts are established in code first; judgement only sits on top of them.',
  },
  {
    icon: MessageSquareText,
    title: 'Ask about what came back',
    where: 'The composer in the case room',
    optional: true,
    body: 'Only if something needs pressing on — you can go straight to the report. Type a follow-up in the same box; answers cite the runs behind them, and clicking a run reference opens the filed evidence for it. The Findings tab is the same material as a list.',
  },
  {
    icon: FileText,
    title: 'Draft the report',
    where: 'Draft report',
    body: 'Turns the findings into a supervisory report. It can only cite findings that exist — never the firm’s own text — and the pipeline then pauses at a human gate. Nothing issues on its own.',
  },
  {
    icon: BadgeCheck,
    title: 'Sign the decision',
    where: 'Decision tab',
    body: 'Yours to make: pick a disposition, write the rationale, add conditions if you are monitoring, and sign. Signing records the authorisation and releases the report it rests on. A clean case with nothing to answer is closed the same way — “Close — no action” — so every case ends in a named decision.',
  },
]

/** Fork → edit → sweep → compare → promote, in the words the sandbox uses. */
const SANDBOX: [string, string][] = [
  ['Fork', 'Copies the book in force. Nothing you are looking at can change under you.'],
  ['Edit', 'Set a rule active, draft or retired; change its severity weight; change its parameters — the KYA delegation depth, an accreditation list, a structuring threshold.'],
  ['Sweep', 'Runs the draft over every labelled submission through the real pipeline. Deterministic — the default — takes about 25 seconds and spends nothing; Full takes about six minutes of real model calls.'],
  ['Compare', 'Against the book in force: which cases flip, what appears, what stops firing. Both sides come from stored sweeps, so this is instant.'],
  ['Promote', 'Puts it in force under your name, with a reason and the sweep behind it on the record.'],
]

/**
 * The console explained in one window: the review loop end to end, and how
 * the rules behind it are changed. Deliberately short — it names the control
 * to press at each step and what pressing it commits you to, and leaves the
 * substance to the Rulebook and the specialist pages it points at.
 */
export function HowToUseDialog({ onOpenRulebook }: { onOpenRulebook?: () => void }) {
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" className="h-7 gap-1.5 px-2 text-xs text-muted-foreground">
          <HelpCircle data-icon="inline-start" />
          How to use
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>How to use this console</DialogTitle>
          <DialogDescription>
            A submission arrives, ten specialists review it against published rules, and a named supervisor signs the
            outcome. Five steps, and one place to change the rules themselves.
          </DialogDescription>
        </DialogHeader>

        <div className="text-[13px] leading-relaxed">
          {/* First, because it is recorded on every run and every signature
              below, and it is the one field a new reader walks past. */}
          <div className="flex gap-2.5 rounded-lg border bg-muted/30 px-3 py-2.5">
            <UserRound className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <p className="text-muted-foreground">
              <span className="font-medium text-foreground">Put your name in first.</span> Top right of this bar —
              click it and type. Everything you run, promote and sign is recorded under it, permanently, so set it
              before you start rather than at the signature.
            </p>
          </div>

          <div className="mt-5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Reviewing a submission
          </div>
          <ol className="mt-2 overflow-hidden rounded-lg border bg-card">
            {REVIEW.map((s, i) => {
              const Icon = s.icon
              return (
                <li key={s.title} className={cn('flex gap-3 px-4 py-3', i > 0 && 'border-t')}>
                  <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md border bg-muted/40">
                    <Icon className="size-3.5 text-muted-foreground" />
                  </span>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-baseline gap-x-2">
                      <span className="font-heading text-[13.5px] font-semibold">
                        {i + 1}. {s.title}
                      </span>
                      <span className="font-mono text-[11px] text-brand-blue">{s.where}</span>
                      {s.optional && (
                        <span className="rounded bg-muted px-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                          optional
                        </span>
                      )}
                    </div>
                    <p className="mt-0.5 text-muted-foreground">{s.body}</p>
                  </div>
                </li>
              )
            })}
          </ol>

          <div className="mt-5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Changing the rules
          </div>
          <div className="mt-2 rounded-lg border bg-card px-4 py-3">
            <div className="flex items-center gap-2">
              <FlaskConical className="size-4 text-muted-foreground" />
              <span className="font-heading text-[13.5px] font-semibold">Policy sandbox</span>
            </div>
            <p className="mt-1 text-muted-foreground">
              Every rule the specialists apply — KYA accreditation and delegation, mandate scope, consent, drift, the
              rest — is versioned data, not code. You change it here, never by editing a file, and never against the
              book that live cases are being judged under.
            </p>
            {/* Said before the steps, because the expensive mode is one click
                from the cheap one. The warning, not the reasoning — the modes
                carry their own tooltips in the sandbox. */}
            <p className="mt-2 rounded-md border-l-2 border-amber-500/45 bg-muted/40 px-3 py-2 text-muted-foreground">
              <span className="font-medium text-foreground">A full sweep is slow and costly</span> — around six minutes
              of real model calls. Use <span className="font-medium text-foreground">Deterministic</span>, the default.
            </p>
            <dl className="mt-2.5 space-y-1.5">
              {SANDBOX.map(([step, what]) => (
                <div key={step} className="sm:flex sm:gap-3">
                  <dt className="w-20 shrink-0 font-heading text-[13px] font-semibold">{step}</dt>
                  <dd className="text-muted-foreground">{what}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="mt-4 flex gap-2.5 rounded-lg border bg-muted/30 px-3 py-2.5">
            <BookOpen className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <p className="text-muted-foreground">
              <span className="font-medium text-foreground">If you want the substance,</span> the Documentation group in
              the sidebar has the Rulebook — what a rule is made of and how one becomes policy — the Failure catalogue
              of named harms, and one page per specialist explaining what it can and cannot establish.
              {onOpenRulebook && (
                <>
                  {' '}
                  <button
                    type="button"
                    onClick={() => {
                      setOpen(false)
                      onOpenRulebook()
                    }}
                    className="font-medium text-brand-blue underline-offset-2 outline-none hover:underline"
                  >
                    Open the Rulebook
                  </button>
                  .
                </>
              )}
            </p>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
