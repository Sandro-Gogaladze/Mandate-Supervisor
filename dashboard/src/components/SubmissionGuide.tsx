import { useState } from 'react'
import { BadgeCheck, FolderTree, HelpCircle, Landmark } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'

/** One row of the "what each file carries" list. */
const FILES: { name: string; required: boolean; what: string }[] = [
  {
    name: 'dossier.json',
    required: true,
    what: 'Who is submitting and about which agent: the operator, the agent’s identity credential and its delegation chain, the published agent card, the controls the institution declares it runs, the change log, and an index attesting to every run file.',
  },
  {
    name: 'runs/RUN-*.json',
    required: true,
    what: 'One file per run, each a complete decision: the customer’s own words, the signed Intent, how the agent built the cart (every tool call and what it chose between), the consent screen and the values actually shown on it, the signed cart, the payment and who was really paid, and the firm’s own control outcomes.',
  },
  {
    name: 'transactions.json',
    required: true,
    what: 'The agent’s wider transaction ledger — deliberately broader than the submitted runs, so patterns no single payment reveals (structuring, concentration, velocity) are visible.',
  },
  {
    name: 'ground_truth.json',
    required: false,
    what: 'Labels, for evaluation only. A review never opens it.',
  },
]

const CHECKS = [
  'Every signature verifies against an accredited issuer’s public key.',
  'Every hash link holds: Intent → Cart → Payment, unbroken.',
  'The run index matches the run files present, by hash — nothing added, removed or edited after filing.',
  'Your institution token matches the institution named in the submission.',
  'Institution, operator and agent all resolve in the regulator’s own registers.',
]

/**
 * The submission instructions, in their own dialog rather than a disclosure
 * inside the upload form. Expanded inline they pushed the token field and
 * file picker off the bottom of the sheet, so the reader had to collapse
 * the thing they were reading to act on it. As a separate window the form
 * behind it stays whole.
 */
export function SubmissionGuideDialog() {
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="h-7 text-xs">
          <HelpCircle data-icon="inline-start" />
          What goes in the ZIP?
        </Button>
      </DialogTrigger>
      <DialogContent className="z-[60] max-h-[85vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>What goes in the ZIP</DialogTitle>
          <DialogDescription>
            One agent&rsquo;s evidence, filed as a single archive. Everything below is checked on upload.
          </DialogDescription>
        </DialogHeader>

        <div className="text-[13px] leading-relaxed">
          {/* Who files, and to whom — the part a file list can't tell you,
              and the part an operator gets wrong first. */}
          <div className="flex gap-2.5 rounded-lg border bg-muted/30 px-3 py-2.5">
            <Landmark className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <p className="text-muted-foreground">
              <span className="font-medium text-foreground">Who files this.</span> The supervised institution that
              sponsors the agent — a bank, PSP or e-money institution — submits it to the regulator through this
              channel. The operator running the agent prepares the evidence; the institution files it and vouches for
              it with its own submission token.
            </p>
          </div>

          <div className="mt-5 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <FolderTree className="size-3.5" />
            Structure
          </div>
          <pre className="mt-2 overflow-x-auto rounded-md border bg-muted/30 px-3 py-2.5 font-mono text-[11.5px] leading-[1.7] text-muted-foreground">
{`submission.zip
├── dossier.json
├── runs/
│   ├── RUN-0001.json
│   └── RUN-0002.json  …one per run
├── transactions.json
└── ground_truth.json   optional`}
          </pre>

          <dl className="mt-5 space-y-3">
            {FILES.map((f) => (
              <div key={f.name}>
                <dt className="flex items-baseline gap-2">
                  <code className="font-mono text-[12px] font-medium text-foreground">{f.name}</code>
                  {!f.required && <span className="text-[11px] text-muted-foreground">optional</span>}
                </dt>
                <dd className="mt-0.5 text-muted-foreground">{f.what}</dd>
              </div>
            ))}
          </dl>

          <div className="mt-5 rounded-lg border bg-muted/30 px-3 py-2.5">
            <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              <BadgeCheck className="size-3.5" />
              Checked before a case opens
            </div>
            <ul className="mt-2 space-y-1.5 text-muted-foreground">
              {CHECKS.map((c) => (
                <li key={c} className="flex gap-2">
                  <span aria-hidden className="mt-[0.55em] size-1 shrink-0 rounded-full bg-muted-foreground/50" />
                  {c}
                </li>
              ))}
            </ul>
            <p className="mt-2.5 text-muted-foreground">
              A submission that fails any of these is rejected with the exact reason — it is never reviewed on partial
              evidence.
            </p>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
