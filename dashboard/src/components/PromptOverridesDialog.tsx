// Per-run prompt overrides (architecture-v2 §6). The default lives in the
// registry and is shown read-only around an editable BODY; an edit applies
// to the NEXT run only, is recorded in full on that run's ledger entry, and
// nothing persists — the next run starts from the default again. The fixed
// preamble and tool contract cannot be edited here or anywhere else at
// runtime, and the mandatory dispatch floor is enforced in code regardless
// of what this text says.
import { useEffect, useMemo, useState } from 'react'
import { FileSliders, RotateCcw } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
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
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { getPrompts } from '@/lib/api'
import type { PromptSpec } from '@/lib/types'
import { cn } from '@/lib/utils'

const EDITABLE: { id: string; label: string }[] = [
  { id: 'ORCH-DISPATCH', label: 'Dispatch' },
  { id: 'SPECIALIST-MANDATE', label: 'Mandate' },
  { id: 'SPECIALIST-KYA', label: 'KYA' },
  { id: 'SPECIALIST-LOG', label: 'Log' },
  { id: 'SPECIALIST-DRIFT', label: 'Drift' },
]

export function PromptOverridesDialog({
  overrides,
  onChange,
}: {
  overrides: Record<string, string>
  onChange: (next: Record<string, string>) => void
}) {
  const [open, setOpen] = useState(false)
  const [specs, setSpecs] = useState<Record<string, PromptSpec> | null>(null)
  const [drafts, setDrafts] = useState<Record<string, string>>({})

  useEffect(() => {
    if (open && specs === null) {
      getPrompts().then(setSpecs).catch(() => setSpecs({}))
    }
  }, [open, specs])

  useEffect(() => {
    if (open) setDrafts({ ...overrides })
  }, [open, overrides])

  const overrideCount = useMemo(() => Object.keys(overrides).length, [overrides])

  const apply = () => {
    const cleaned: Record<string, string> = {}
    for (const { id } of EDITABLE) {
      const text = (drafts[id] ?? '').trim()
      const defaultBody = specs?.[id]?.body?.trim() ?? ''
      if (text && text !== defaultBody) cleaned[id] = drafts[id]
    }
    onChange(cleaned)
    setOpen(false)
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <FileSliders data-icon="inline-start" />
          Instructions
          {overrideCount > 0 && (
            <Badge variant="secondary" className="ml-1 h-4 px-1 text-[10px]">
              {overrideCount} edited
            </Badge>
          )}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Supervision instructions</DialogTitle>
          <DialogDescription>
            Edits apply to the <span className="font-medium text-foreground">next run only</span> and are
            recorded in full on the ledger. The role preamble and tool contract are fixed, and Mandate + KYA
            run regardless of what any instruction says — the floor is code, not prose.
          </DialogDescription>
        </DialogHeader>
        {specs === null ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Loading defaults…</p>
        ) : (
          <Tabs defaultValue={EDITABLE[0].id}>
            <TabsList className="h-8">
              {EDITABLE.map(({ id, label }) => (
                <TabsTrigger key={id} value={id} className="gap-1 px-2.5 text-xs">
                  {label}
                  {(drafts[id] ?? '').trim() && (drafts[id] ?? '').trim() !== (specs[id]?.body ?? '').trim() && (
                    <span className="size-1.5 rounded-full bg-primary" />
                  )}
                </TabsTrigger>
              ))}
            </TabsList>
            {EDITABLE.map(({ id }) => {
              const spec = specs[id]
              if (!spec) return null
              const value = drafts[id] ?? spec.body
              const edited = value.trim() !== spec.body.trim()
              return (
                <TabsContent key={id} value={id} className="mt-3 flex flex-col gap-2">
                  <ScrollArea className="max-h-16 rounded-md border bg-muted/30 px-3 py-2">
                    <p className="text-[11px] leading-relaxed text-muted-foreground">{spec.preamble}</p>
                  </ScrollArea>
                  <textarea
                    value={value}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [id]: e.target.value }))}
                    rows={9}
                    spellCheck={false}
                    className={cn(
                      'w-full resize-y rounded-md border bg-transparent px-3 py-2 font-mono text-[12px] leading-relaxed shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50',
                      edited ? 'border-primary/50' : 'border-input',
                    )}
                  />
                  <div className="flex items-center justify-between">
                    <p className="text-[11px] text-muted-foreground">
                      …{spec.contract.slice(0, 96)} <span className="font-mono">(fixed)</span> · default v
                      {spec.version}
                    </p>
                    {edited && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setDrafts((prev) => ({ ...prev, [id]: spec.body }))}
                      >
                        <RotateCcw data-icon="inline-start" />
                        Reset to default
                      </Button>
                    )}
                  </div>
                </TabsContent>
              )
            })}
          </Tabs>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={apply} disabled={specs === null}>
            Use for next run
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
