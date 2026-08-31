import { useRef, useState } from 'react'
import { FileJson, Loader2, TriangleAlert, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { CaseUploadError, uploadCase } from '@/lib/api'
import type { CaseSummary } from '@/lib/types'

export function UploadCaseDialog({ onUploaded }: { onUploaded: (c: CaseSummary) => void }) {
  const [open, setOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const reset = () => {
    setFile(null)
    setError(null)
    setSubmitting(false)
    if (inputRef.current) inputRef.current.value = ''
  }

  const handleSubmit = async () => {
    if (!file) return
    setSubmitting(true)
    setError(null)
    try {
      const summary = await uploadCase(file)
      toast.success('Case submitted', { description: `${summary.firm} — ${summary.case_id}` })
      setOpen(false)
      reset()
      onUploaded(summary)
    } catch (err) {
      setError(err instanceof CaseUploadError ? err.message : `Couldn't submit this file: ${String(err)}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) reset()
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline">
          <Upload data-icon="inline-start" />
          Submit a case
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Submit a case for review</DialogTitle>
          <DialogDescription>
            Upload the mandate chain and transaction history a firm submitted — the same JSON bundle shape as the
            cases already in the queue (Intent, Cart, and Payment mandates, the KYA credential, and the transaction
            log).
          </DialogDescription>
        </DialogHeader>

        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="case-file">Case bundle (.json)</FieldLabel>
            <input
              ref={inputRef}
              id="case-file"
              type="file"
              accept=".json,application/json"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null)
                setError(null)
              }}
              className="flex h-9 w-full min-w-0 rounded-md border border-input bg-transparent px-3 py-1.5 text-sm shadow-xs outline-none file:mr-3 file:h-full file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground selection:bg-primary selection:text-primary-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
            />
            <FieldDescription>Never seen a bundle before? Open any case in the queue and use its data as a template.</FieldDescription>
          </Field>

          {file && !error && (
            <div className="flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-2 text-sm">
              <FileJson className="size-4 shrink-0 text-muted-foreground" />
              <span className="truncate">{file.name}</span>
              <span className="ml-auto shrink-0 text-xs text-muted-foreground">{Math.round(file.size / 1024)} KB</span>
            </div>
          )}

          {error && (
            <Alert variant="destructive">
              <TriangleAlert />
              <AlertDescription>
                <pre className="whitespace-pre-wrap font-mono text-xs">{error}</pre>
              </AlertDescription>
            </Alert>
          )}
        </FieldGroup>

        <DialogFooter>
          <Button onClick={handleSubmit} disabled={!file || submitting}>
            {submitting ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <Upload data-icon="inline-start" />}
            {submitting ? 'Submitting…' : 'Submit for review'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
