// The policy sandbox — docs/phases/14-policy-sandbox.md.
//
// Three panes because the work has three phases: choose a version, edit it,
// see what it did. The version graph on the left is the point of the page:
// nothing you are looking at can change under you, because every edit forks.
import { useCallback, useEffect, useState } from 'react'
import { ChevronRight, FlaskConical, GitBranch, Loader2, Play, ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { DISPOSITION_LABEL, type Disposition } from '@/lib/supervision-types'
import {
  compareSweeps, createDraft, deleteDraft, editDraftRule, getRulebook,
  getSandboxDomains, getSweep, getVersionGraph, promoteDraft, runSweep,
} from '@/lib/api'
import { useOfficer } from '@/lib/officer'
import {
  labelled, trustworthy,
  type DossierOutcome, type RulebookView, type Rule, type RuleScore, type SandboxDomain,
  type Sweep, type SweepComparison, type VersionGraph,
} from '@/lib/sandbox-types'
import { BlueprintGrid } from '@/components/BlueprintGrid'
import { cn } from '@/lib/utils'


/** Tab labels. The API's full names ("Identity & Authority", "Decision
 * Provenance") are right in prose but too long to seat nine outlined tabs on
 * one row; these are the same names the specialist roster uses, so the two
 * surfaces agree. The full label still shows on hover. */
const TAB_LABEL: Record<string, string> = {
  kya: 'Identity',
  mandate: 'Mandate',
  consent: 'Consent',
  provenance: 'Provenance',
  injection: 'Manipulation',
  counterparty: 'Counterparty',
  log: 'Patterns',
  drift: 'Drift',
  control_assurance: 'Controls',
}

// ---------------------------------------------------------------------------

export function PolicySandbox() {
  const [officer] = useOfficer()
  const [domains, setDomains] = useState<SandboxDomain[]>([])
  const [domain, setDomain] = useState('kya')
  const [graph, setGraph] = useState<VersionGraph | null>(null)
  const [selected, setSelected] = useState<string>('kya')   // ruleset_ref being edited
  const [book, setBook] = useState<RulebookView | null>(null)
  const [sweep, setSweep] = useState<Sweep | null>(null)
  const [compare, setCompare] = useState<SweepComparison | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  useEffect(() => { getSandboxDomains().then(setDomains).catch(() => setDomains([])) }, [])

  const refresh = useCallback(async (ref?: string) => {
    const target = ref ?? selected
    const [g, b] = await Promise.all([getVersionGraph(domain), getRulebook(target)])
    setGraph(g); setBook(b)
    // Every sweep is stored, and a live one costs six minutes — so selecting a
    // version shows the scorecard it already has rather than an empty panel
    // inviting you to pay for the same answer twice. Only a version that has
    // never been swept comes up blank.
    const stored = target === g.domain
      ? g.active.sweep_id
      : g.drafts.find((d) => d.draft.draft_id === target)?.sweep_id ?? null
    if (stored) {
      try { setSweep(await getSweep(stored)) } catch { setSweep(null) }
    } else {
      setSweep(null)
    }
  }, [domain, selected])

  useEffect(() => { setSelected(domain); setCompare(null) }, [domain])
  useEffect(() => { refresh().catch((e) => toast(String(e))) }, [refresh])

  const sweepFor = async (ref: string) => {
    setBusy(`Sweeping ${ref} over every labelled submission — the full pipeline, so this takes minutes…`)
    setCompare(null)
    try {
      const result = await runSweep({ ruleset_ref: ref })
      setSweep(result)
      if (result.error) toast(`Sweep failed: ${result.error}`)
      await refresh(ref)
    } catch (e) { toast(String(e)) } finally { setBusy(null) }
  }

  const compareWithBase = async () => {
    if (!sweep || !graph?.active.sweep_id) return
    setBusy('Comparing…')
    try { setCompare(await compareSweeps(graph.active.sweep_id, sweep.sweep_id)) }
    catch (e) { toast(String(e)) } finally { setBusy(null) }
  }

  const fork = async () => {
    const label = window.prompt('Name this draft — what are you trying?')
    if (!label?.trim()) return
    try {
      const draft = await createDraft({ domain, label: label.trim(), created_by: officer })
      setSelected(draft.draft_id); setSweep(null); setCompare(null)
      await refresh(draft.draft_id)
    } catch (e) { toast(String(e)) }
  }

  const edit = async (rule: Rule, patch: { status?: string; severity_weight?: number; params?: Record<string, unknown> }) => {
    if (!book?.editable) return
    try {
      await editDraftRule(book.ref, { ...patch, rule_id: rule.rule_id })
      // The scorecard belonged to the rulebook as it was a moment ago.
      setSweep(null); setCompare(null)
      await refresh()
    } catch (e) { toast(String(e)) }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <Header domains={domains} domain={domain} onDomain={setDomain} />
      {busy && (
        <p className="flex items-center gap-2 border-b bg-blue-500/[0.06] px-4 py-1.5 text-[13px] text-blue-700 dark:text-blue-400">
          <Loader2 className="size-3.5 animate-spin" />{busy}
        </p>
      )}
      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[204px_minmax(0,1fr)_296px]">
        <VersionPane graph={graph} selected={selected}
          onSelect={(ref) => { setSelected(ref); setCompare(null); refresh(ref).catch((e) => toast(String(e))) }}
          onFork={fork} onSweep={sweepFor} onDelete={async (id) => {
            await deleteDraft(id); setSelected(domain); await refresh(domain)
          }} busy={!!busy} />
        <RulebookPane book={book} sweep={sweep} onEdit={edit} />
        <ScorecardPane sweep={sweep} compare={compare} book={book} graph={graph}
          onCompare={compareWithBase}
          onPromoted={async () => { setSweep(null); setCompare(null); setSelected(domain); await refresh(domain) }}
          busy={!!busy} officer={officer} />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------

function Header({ domains, domain, onDomain }: {
  domains: SandboxDomain[]; domain: string; onDomain: (d: string) => void
}) {
  return (
    <header className="relative border-b">
      <BlueprintGrid strength={4} size={24} />
      <div className="relative px-5 pt-4">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 className="flex items-center gap-2 font-heading text-lg font-semibold tracking-tight">
            <FlaskConical className="size-4 text-muted-foreground" />
            Agent Supervision Rulebook
          </h2>
          <span className="text-xs text-muted-foreground">industry term: Know Your Agent (KYA)</span>
        </div>
        <p className="mt-1.5 max-w-3xl text-[13px] leading-relaxed text-muted-foreground">
          There is no international rulebook for supervising payment agents. Change one here, run it against every
          labelled submission on record, and see exactly what changed before any of it becomes policy.
        </p>
      </div>

      {/* Domains as outlined tabs, all nine on one row and none hidden
          behind a scroll edge — a reader needs the whole rulebook's shape
          to know what the sandbox covers. Short labels are what make the
          row fit; it still wraps rather than clips on a narrow window. */}
      <div className="relative mt-3 flex flex-wrap gap-1 px-5 pb-4">
        {domains.map((d) => {
          const on = d.domain === domain
          return (
            <button
              key={d.domain}
              type="button"
              onClick={() => onDomain(d.domain)}
              title={d.label}
              className={cn(
                'rounded-md border px-2.5 py-1 text-[12.5px] font-medium outline-none transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50',
                on
                  ? 'border-brand-blue/55 bg-brand-blue/10 text-brand-blue'
                  : 'border-border bg-card text-muted-foreground hover:border-foreground/25 hover:text-foreground',
              )}
            >
              {TAB_LABEL[d.domain] ?? d.label}
              <span className={cn('ml-1.5 font-mono text-[11px]', on ? 'opacity-80' : 'opacity-55')}>{d.rules}</span>
            </button>
          )
        })}
      </div>
    </header>
  )
}

// ---------------------------------------------------------------------------

function VersionPane({ graph, selected, onSelect, onFork, onSweep, onDelete, busy }: {
  graph: VersionGraph | null; selected: string; onSelect: (ref: string) => void
  onFork: () => void; onSweep: (ref: string) => void; onDelete: (id: string) => void; busy: boolean
}) {
  if (!graph) return <div className="border-r p-4"><Skeleton className="h-40" /></div>
  return (
    <div className="flex min-h-0 flex-col border-r">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          <GitBranch className="size-3.5" />Versions
        </span>
        <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={onFork} disabled={busy}>Fork</Button>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col gap-1 p-2">
          <VersionNode active label={`v${graph.active.version}`} sub={`in force · ${graph.active.rules} rules`}
            selected={selected === graph.domain} onClick={() => onSelect(graph.domain)}
            onSweep={() => onSweep(graph.domain)} busy={busy} swept={!!graph.active.sweep_id}
            stale={!!graph.active.sweep_id && graph.active.mode === 'mechanical'} />
          {graph.drafts.map(({ draft, swept, mode }) => (
            <VersionNode key={draft.draft_id} label={draft.label}
              sub={draft.edits.length ? draft.edits[0] : 'no edits yet'}
              extra={draft.edits.length > 1 ? `+${draft.edits.length - 1} more` : undefined}
              selected={selected === draft.draft_id} onClick={() => onSelect(draft.draft_id)}
              onSweep={() => onSweep(draft.draft_id)} onDelete={() => onDelete(draft.draft_id)}
              busy={busy} swept={swept} stale={swept && mode === 'mechanical'} />
          ))}
          {graph.superseded.map((v) => (
            <div key={v} className="px-2 py-1.5 text-[12px] text-muted-foreground">
              <span className="font-mono">v{v}</span> · superseded
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}

function VersionNode({ label, sub, extra, active, selected, swept, stale, busy, onClick, onSweep, onDelete }: {
  label: string; sub: string; extra?: string; active?: boolean; selected: boolean; swept: boolean
  stale?: boolean; busy: boolean; onClick: () => void; onSweep: () => void; onDelete?: () => void
}) {
  return (
    <div className={cn('rounded-lg border px-2.5 py-2', selected ? 'border-primary bg-primary/[0.06]' : 'bg-card')}>
      <button type="button" onClick={onClick} className="w-full text-left">
        <div className="flex items-center gap-1.5">
          <span className={cn('size-2 rounded-full', active ? 'bg-emerald-500' : 'bg-muted-foreground/40')} />
          <span className="text-[13px] font-medium">{label}</span>
          {!swept ? (
            <span className="ml-auto text-[10px] uppercase text-muted-foreground">never swept</span>
          ) : stale ? (
            /* Its scorecard was taken a different way, and comparing across
               modes is refused — say so here rather than at the moment someone
               presses Compare and gets a refusal they cannot act on. */
            <span className="ml-auto text-[10px] uppercase text-amber-700 dark:text-amber-400" title="Swept before model judgement was included — re-sweep to compare against it">re-sweep</span>
          ) : null}
        </div>
        <p className="mt-0.5 truncate pl-3.5 font-mono text-[10px] text-muted-foreground">{sub}</p>
        {extra && <p className="pl-3.5 text-[10px] text-muted-foreground">{extra}</p>}
      </button>
      <div className="mt-1.5 flex gap-1 pl-3.5">
        <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px]" onClick={onSweep} disabled={busy}>
          <Play data-icon="inline-start" />Sweep
        </Button>
        {onDelete && (
          <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px] text-muted-foreground" onClick={onDelete} disabled={busy}>
            Delete
          </Button>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------

function RulebookPane({ book, sweep, onEdit }: {
  book: RulebookView | null; sweep: Sweep | null
  onEdit: (rule: Rule, patch: { status?: string; severity_weight?: number; params?: Record<string, unknown> }) => void
}) {
  const [filter, setFilter] = useState('')
  if (!book) return <div className="p-4"><Skeleton className="h-64" /></div>
  const scores = sweep?.result?.per_rule ?? {}
  const rules = book.ruleset.rules.filter((r) =>
    !filter || `${r.rule_id} ${r.description}`.toLowerCase().includes(filter.toLowerCase()))

  return (
    <div className="flex min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
        <span className="text-[13px] font-medium">{book.label}</span>
        {book.editable
          ? <Badge variant="secondary" className="text-[10px]">editable draft</Badge>
          : <Badge variant="outline" className="text-[10px]">read-only — fork to edit</Badge>}
        <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter rules"
          className="ml-auto h-7 w-56 text-xs" aria-label="Filter rules" />
      </div>
      <ScrollArea className="min-h-0 flex-1">
        {/* Without explicit widths the browser starves the rule column — the
            only one holding prose — to pad six numeric ones. */}
        <table className="w-full table-fixed text-[12.5px]">
          {/* Five columns, not six. Parameters moved into the rule cell:
              they belong to the rule they configure, and as their own
              column they starved the one holding prose. */}
          <colgroup>
            <col />
            <col className="w-[84px]" />
            <col className="w-[74px]" />
            <col className="w-[58px]" />
            <col className="w-[76px]" />
          </colgroup>
          <thead className="sticky top-0 bg-background">
            <tr className="border-b text-left text-[10px] uppercase tracking-wide text-muted-foreground">
              <th className="px-3 py-2">Rule</th>
              <th className="px-2 py-2">Status</th>
              <th className="px-2 py-2">Severity</th>
              <th className="px-2 py-2 text-right">Fires</th>
              <th className="px-3 py-2 text-right">Catches</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((rule) => (
              <RuleRow key={rule.rule_id} rule={rule} score={scores[rule.rule_id]}
                editable={book.editable} swept={!!sweep?.result} onEdit={onEdit} />
            ))}
          </tbody>
        </table>
      </ScrollArea>
    </div>
  )
}

function RuleRow({ rule, score, editable, swept, onEdit }: {
  rule: Rule; score?: RuleScore; editable: boolean; swept: boolean
  onEdit: (rule: Rule, patch: { status?: string; severity_weight?: number; params?: Record<string, unknown> }) => void
}) {
  const dead = swept && score && score.fired === 0 && rule.status === 'active'
  const n = score ? labelled(score) : 0
  return (
    <tr className={cn('border-b border-border/50 align-top', dead && 'opacity-55')}>
      <td className="px-3 py-2">
        <div className="font-mono text-[11px] font-semibold">{rule.rule_id}</div>
        <p className="mt-0.5 text-[11.5px] leading-4 text-muted-foreground">{rule.description}</p>
        {Object.keys(rule.params).length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5">
            {Object.entries(rule.params).map(([key, value]) => (
              <ParamField key={key} name={key} value={value} editable={editable}
                onChange={(next) => onEdit(rule, { params: { [key]: next } })} />
            ))}
          </div>
        )}
        {rule.evaluation === 'judged' && (
          <span className="mt-1.5 inline-block rounded bg-muted px-1.5 text-[10px] text-muted-foreground">judged</span>
        )}
      </td>
      <td className="px-2 py-2">
        {editable ? (
          <select value={rule.status} onChange={(e) => onEdit(rule, { status: e.target.value })}
            aria-label={`${rule.rule_id} status`}
            className="h-7 rounded border bg-background px-1 text-[11px]">
            {['active', 'draft', 'retired'].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        ) : <span className="text-[11px] text-muted-foreground">{rule.status}</span>}
      </td>
      <td className="px-2 py-2">
        {editable ? (
          <Input type="number" min={0} max={1} step={0.05} defaultValue={rule.severity_weight}
            aria-label={`${rule.rule_id} severity`} className="h-7 w-20 text-[11px]"
            onBlur={(e) => {
              const v = Number(e.target.value)
              if (!Number.isNaN(v) && v !== rule.severity_weight) onEdit(rule, { severity_weight: v })
            }} />
        ) : <span className="font-mono text-[11px]">{rule.severity_weight.toFixed(2)}</span>}
      </td>
      <td className="px-2 py-2 text-right font-mono text-[11px]">
        {!swept ? '—' : dead ? <span className="text-amber-700 dark:text-amber-400">never</span> : score?.fired}
      </td>
      <td className="px-3 py-2 text-right">
        {!swept || !score || n === 0 ? <span className="text-[11px] text-muted-foreground">—</span> : (
          <>
            <div className="font-mono text-[11px]">{score.metrics.tp}/{n}</div>
            {!trustworthy(score) && (
              <div className="text-[10px] leading-3 text-muted-foreground">n={n}, too few</div>
            )}
          </>
        )}
      </td>
    </tr>
  )
}

/** Typed to the value already there: a number stays a number, a list stays a
 * list. The server re-validates through `typed_params()` regardless. */
function ParamField({ name, value, editable, onChange }: {
  name: string; value: unknown; editable: boolean; onChange: (next: unknown) => void
}) {
  const isNumber = typeof value === 'number'
  const isList = Array.isArray(value)
  const shown = isList ? (value as unknown[]).join(', ') : String(value)
  if (!editable) {
    return <div className="font-mono text-[10.5px] text-muted-foreground"><span className="opacity-70">{name}</span> {shown}</div>
  }
  return (
    <label className="mb-1 flex items-center gap-1.5">
      <span className="font-mono text-[10px] text-muted-foreground">{name}</span>
      <Input
        defaultValue={shown}
        type={isNumber ? 'number' : 'text'}
        aria-label={name}
        className="h-6 w-28 text-[11px]"
        onBlur={(e) => {
          const raw = e.target.value
          const next = isNumber ? Number(raw) : isList ? raw.split(',').map((s) => s.trim()).filter(Boolean) : raw
          if (JSON.stringify(next) !== JSON.stringify(value)) onChange(next)
        }}
      />
    </label>
  )
}

// ---------------------------------------------------------------------------

function ScorecardPane({ sweep, compare, book, graph, onCompare, onPromoted, busy, officer }: {
  sweep: Sweep | null; compare: SweepComparison | null; book: RulebookView | null
  graph: VersionGraph | null; onCompare: () => void
  onPromoted: () => void; busy: boolean; officer: string
}) {
  const result = sweep?.result
  return (
    <div className="flex min-h-0 flex-col border-l">
      <div className="flex items-center gap-2 border-b px-3 py-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Scorecard</span>
        {/* When this was measured. A stored scorecard is the normal case —
            a live sweep costs minutes, so the page shows the one a version
            already has — and a reader must never mistake it for a result
            taken just now against the rules currently on screen. */}
        {sweep && (
          <span className="font-mono text-[10px] text-muted-foreground" title={sweep.started_at}>
            {sweep.label} · swept {new Date(sweep.started_at).toLocaleString('en-GB', {
              day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
          </span>
        )}
        {/* No Sweep button here: it called the same sweepFor() as the
            selected version's own control, so the page offered one action
            twice. Compare is genuinely scorecard-scoped and stays. */}
        {result && graph?.active.sweep_id && sweep?.ruleset_ref !== graph.domain && (
          <Button size="sm" variant="ghost" className="ml-auto h-7 text-xs" onClick={onCompare} disabled={busy}>Compare</Button>
        )}
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col gap-4 p-3">
          {result && book?.editable && sweep?.ruleset_digest !== book.ruleset_digest && (
            <p className="rounded-lg border border-amber-500/40 bg-amber-500/[0.06] px-3 py-2 text-[12px] leading-5 text-amber-700 dark:text-amber-400">
              This scorecard measured an earlier version of this draft — it has been edited since.
              Sweep again before reading anything from it, and before promoting: a promotion is
              refused on a sweep that did not measure the draft as it now stands.
            </p>
          )}
          {!result && (
            <p className="text-[13px] leading-6 text-muted-foreground">
              Run <span className="font-medium text-foreground">Sweep</span> on a version to see what it catches. A
              sweep replays the whole review over every labelled submission — the same pipeline a real case goes
              through, judged rules included — and a draft cannot be promoted without one. It takes a few minutes.
            </p>
          )}
          {sweep?.error && (
            <p className="rounded-lg border border-red-500/30 bg-red-500/[0.05] p-2.5 text-[12.5px] text-red-700 dark:text-red-400">{sweep.error}</p>
          )}
          {result && <Scorecard result={result} compare={compare} edits={book?.edits ?? []} />}
          {result && book?.editable && sweep && (
            <Promote draftId={book.ref} sweepId={sweep.sweep_id} officer={officer}
              onDone={onPromoted} busy={busy} />
          )}
        </div>
      </ScrollArea>
    </div>
  )
}

/** What an edit can actually move. The two kinds have different effects and
 * the scorecard used to present them identically, which is why a severity
 * change read as "nothing happened": it does not change what fires. */
type EditKind = 'severity' | 'firing' | 'both' | 'none'

function classifyEdits(edits: string[]): EditKind {
  const severity = edits.some((e) => e.includes(' severity '))
  const firing = edits.some((e) => !e.includes(' severity '))
  return severity && firing ? 'both' : severity ? 'severity' : firing ? 'firing' : 'none'
}

const EDIT_EXPLAINER: Record<Exclude<EditKind, 'none'>, string> = {
  severity:
    'A severity edit moves the weight, not what fires — so catches and false positives are expected to be identical. Read the weight line and the per-case weights: a decision only moves when the weight crosses a tier boundary, and a change that does not cross one is still a real change to how the case is priced.',
  firing:
    'A threshold or status edit moves which rules fire at all. Read catches and false positives: a tighter dial that catches nothing new and costs false positives is the finding this page exists to produce.',
  both:
    'This draft moves both. Catches and false positives answer what now fires; the weight and the per-case decisions answer how heavily it is priced.',
}

/** The headline: did this edit help, hurt, or do nothing? Everything below it
 * is the evidence for this one sentence. */
function Verdict({ compare }: { compare: SweepComparison }) {
  if (!compare.comparable) {
    return (
      <p className="rounded-lg border border-amber-500/30 bg-amber-500/[0.05] p-2.5 text-[12.5px] text-amber-700 dark:text-amber-400">
        These two sweeps cannot be compared — {compare.incomparable_reason}. Re-sweep the version in
        force so both scorecards measure the same evidence.
      </p>
    )
  }
  const gained = compare.flips.filter((f) => f.direction === 'caught').length
  const lost = compare.flips.filter((f) => f.direction === 'lost').length
  const newFp = compare.flips.filter((f) => f.direction === 'new_false_positive').length
  const fixedFp = compare.flips.filter((f) => f.direction === 'fixed_false_positive').length
  const decisions = compare.dossier_changes.length

  const parts: string[] = []
  if (gained) parts.push(`catches ${gained} more defect${gained === 1 ? '' : 's'}`)
  if (lost) parts.push(`stops catching ${lost}`)
  if (fixedFp) parts.push(`clears ${fixedFp} false positive${fixedFp === 1 ? '' : 's'}`)
  if (newFp) parts.push(`costs ${newFp} new false positive${newFp === 1 ? '' : 's'}`)
  if (decisions) parts.push(`changes ${decisions} case decision${decisions === 1 ? '' : 's'}`)

  const better = gained + fixedFp
  const worse = lost + newFp
  const tone = worse > better ? 'worse' : better > worse ? 'better' : 'neutral'
  const label = decisions && !better && !worse ? 'Decisions changed'
    : tone === 'better' ? 'Better' : tone === 'worse' ? 'Worse' : 'No change'

  return (
    <div className={cn('rounded-lg border p-2.5',
      tone === 'better' && 'border-emerald-500/40 bg-emerald-500/[0.06]',
      tone === 'worse' && 'border-red-500/40 bg-red-500/[0.06]',
      tone === 'neutral' && 'bg-muted/40')}>
      <p className={cn('text-[13px] font-semibold',
        tone === 'better' && 'text-emerald-700 dark:text-emerald-400',
        tone === 'worse' && 'text-red-700 dark:text-red-400')}>
        {label}
      </p>
      <p className="mt-0.5 text-[12.5px] leading-5 text-muted-foreground">
        {parts.length
          ? `Against the version in force, this draft ${parts.join(', ')}.`
          : 'Against the version in force, this draft changes no outcome on the labelled evidence.'}
      </p>
    </div>
  )
}

/** One question, one number, and the before-value beside it when there is
 * something to compare against. */
function Measure({ question, now, before, invert, detail, children, count }: {
  question: string; now: string; before?: string | null; invert?: boolean; detail?: string
  /** The cases behind the number. A count with no way to see what it is made
   * of tells an officer that something changed and not what. */
  children?: React.ReactNode; count?: number
}) {
  const moved = before != null && before !== now
  const head = (
    <>
      <div className="flex items-baseline gap-2">
        <span className="min-w-0 flex-1 text-[12.5px] text-muted-foreground">{question}</span>
        {moved && <span className="font-mono text-[11px] text-muted-foreground line-through">{before}</span>}
        <span className={cn('font-mono text-[12.5px] font-medium',
          moved && (invert ? 'text-amber-700 dark:text-amber-400' : 'text-foreground'))}>{now}</span>
      </div>
      {detail && <p className="mt-0.5 pr-6 text-[11px] leading-4 text-muted-foreground">{detail}</p>}
    </>
  )
  if (!children || !count) {
    return <div className="border-t py-2 first:border-t-0 first:pt-0">{head}</div>
  }
  return (
    <details className="group/m border-t py-2 first:border-t-0 first:pt-0 [&_summary::-webkit-details-marker]:hidden">
      <summary className="relative cursor-pointer list-none">
        {head}
        <ChevronRight className="absolute right-0 top-0.5 size-3.5 text-muted-foreground transition-transform group-open/m:rotate-90" />
      </summary>
      <div className="mt-2 rounded-md border bg-muted/30 p-2">{children}</div>
    </details>
  )
}

/** Which rules changed behaviour between the two sweeps. `per_rule` carries
 * how often each rule fired and its true/false counts, so the diff is a join
 * on rule id — and it answers the question a flip cannot: not "what moved" but
 * "which rule did I actually change the behaviour of". */
function RuleDiff({ compare }: { compare: SweepComparison }) {
  const before = compare.base.result?.per_rule ?? {}
  const after = compare.candidate.result?.per_rule ?? {}
  const rows = Object.keys({ ...before, ...after })
    .map((rid) => ({ rid, b: before[rid], a: after[rid] }))
    .filter(({ b, a }) => (b?.fired ?? 0) !== (a?.fired ?? 0)
      || (b?.metrics.tp ?? 0) !== (a?.metrics.tp ?? 0)
      || (b?.metrics.fp ?? 0) !== (a?.metrics.fp ?? 0))
    .sort((x, y) => x.rid.localeCompare(y.rid))
  if (!rows.length) return null
  return (
    <details className="group/r mt-2 rounded-md border bg-muted/30 [&_summary::-webkit-details-marker]:hidden">
      <summary className="relative cursor-pointer list-none px-2.5 py-1.5 text-[11.5px] text-muted-foreground">
        Rule by rule · {rows.length} changed behaviour
        <ChevronRight className="absolute right-2 top-2 size-3.5 transition-transform group-open/r:rotate-90" />
      </summary>
      <div className="flex flex-col gap-1 border-t px-2.5 py-2">
        {rows.map(({ rid, b, a }) => (
          <div key={rid} className="flex items-baseline gap-2 text-[11.5px]">
            <code className="font-mono text-[10.5px] font-medium">{rid}</code>
            <span className="ml-auto font-mono text-[10.5px] text-muted-foreground">
              fired {b?.fired ?? 0} → {a?.fired ?? 0}
            </span>
            <span className="w-32 shrink-0 text-right font-mono text-[10.5px]">
              <span className="text-emerald-700 dark:text-emerald-400">{a?.metrics.tp ?? 0} right</span>
              {' · '}
              <span className={cn((a?.metrics.fp ?? 0) > (b?.metrics.fp ?? 0) && 'text-red-700 dark:text-red-400')}>
                {a?.metrics.fp ?? 0} wrong
              </span>
            </span>
          </div>
        ))}
      </div>
    </details>
  )
}

/** The rules that fired on a run the corpus labelled clean. The sweep records
 * the run ids and, separately, each rule's own clean-run hits; joining them
 * here is what turns "3 false positives" into "which rule, on which run". */
function blamedFor(r: NonNullable<Sweep['result']>, run: string): string[] {
  return Object.values(r.per_rule)
    .filter((s) => s.clean_run_hits.includes(run))
    .map((s) => s.rule_id)
    .sort()
}

/** Total severity weight across the corpus — the quantity a severity edit
 * moves, summed so one number answers "did my edit weigh anything". */
function totalWeight(r: NonNullable<Sweep['result']>): string {
  const weights = r.dossiers.map((d) => d.weight_per_run).filter((w): w is number => w != null)
  if (!weights.length) return '—'
  return weights.reduce((a, b) => a + b, 0).toFixed(2)
}

/** One dossier's weight, with its previous value when there is one to show. */
function weightLabel(now: DossierOutcome, before?: DossierOutcome): string {
  if (now.weight_per_run == null) return ''
  const w = now.weight_per_run.toFixed(3)
  const b = before?.weight_per_run
  return b != null && b !== now.weight_per_run ? `${b.toFixed(3)} → ${w}` : w
}

function Scorecard({ result, compare, edits }: {
  result: NonNullable<Sweep['result']>; compare: SweepComparison | null; edits: string[]
}) {
  const base = compare?.comparable ? compare.base.result : null
  const m = result.overall
  const b = base?.overall
  const correct = result.dossiers.filter((d) => d.correct).length
  const baseCorrect = base?.dossiers.filter((d) => d.correct).length
  const kind = classifyEdits(edits)

  return (
    <>
      {compare && <Verdict compare={compare} />}

      {kind !== 'none' && (
        <p className="rounded-lg border-l-2 border-brand-blue/50 bg-muted/40 px-3 py-2 text-[12px] leading-5 text-muted-foreground">
          {EDIT_EXPLAINER[kind]}
        </p>
      )}

      <section>
        <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          What this rulebook does to the evidence
        </h4>
        <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
          Tuning trades one error against the other: a tighter dial catches more and flags more clean
          runs, a looser one does the reverse. These two numbers are that trade, measured.
        </p>
        <div className="mt-1.5 rounded-lg border px-3 py-1">
          <Measure
            question="False negatives — planted defects it did not catch"
            now={`${m.fn} of ${m.tp + m.fn}`}
            before={b && `${b.fn} of ${b.tp + b.fn}`}
            invert
            count={result.missed.length}
            detail="Each one is a real defect the corpus labelled and this rulebook let through. Loosening a dial usually adds to this number."
          >
            <div className="flex flex-col gap-1.5">
              {result.missed.map((x, i) => (
                <div key={i} className="text-[12px]">
                  <div className="flex items-baseline gap-2">
                    <span className="font-mono text-[10.5px] font-semibold">{x.failure}</span>
                    <span className="font-mono text-[10.5px] text-muted-foreground">
                      {x.run_ref ?? x.dossier_id}
                    </span>
                  </div>
                  {x.what && <p className="mt-0.5 leading-4 text-muted-foreground">{x.what}</p>}
                </div>
              ))}
            </div>
          </Measure>
          <Measure
            question="False positives — clean runs it flagged anyway"
            now={`${result.clean_run_false_positives.length} of ${result.clean_runs}`}
            before={base && `${base.clean_run_false_positives.length} of ${base.clean_runs}`}
            invert
            count={result.clean_run_false_positives.length}
            detail="Runs the corpus labelled clean where a rule fired — counted once per run however many rules fired on it. This is the reviewer-time cost: each one is a case someone opens and finds nothing in."
          >
            <div className="flex flex-col gap-1.5">
              {result.clean_run_false_positives.map((run) => (
                <div key={run} className="text-[12px]">
                  <span className="font-mono text-[10.5px] text-muted-foreground">{run}</span>
                  <div className="mt-0.5 flex flex-wrap gap-1">
                    {blamedFor(result, run).map((rid) => (
                      <code key={rid} className="rounded bg-background px-1.5 py-0.5 font-mono text-[10px]">
                        {rid}
                      </code>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </Measure>
          <Measure
            question="Claims the corpus does not support"
            now={String(result.unexpected.length)}
            before={base && String(base.unexpected.length)}
            invert
            count={result.unexpected.length}
            detail="A rule asserted a failure on a run the corpus never labelled with it. Either the rulebook is over-claiming, or the label is missing — the sandbox cannot tell you which, only that the claim stands on nothing. This is the number the per-rule 'wrong' counts are made of."
          >
            <div className="flex flex-col gap-1">
              {result.unexpected.map((u, i) => (
                <div key={i} className="flex items-baseline gap-2 text-[12px]">
                  <span className="font-mono text-[10.5px] font-semibold">{u.failure}</span>
                  <span className="font-mono text-[10.5px] text-muted-foreground">
                    {u.run_ref ?? u.dossier_id}
                  </span>
                  <span className="ml-auto font-mono text-[10px] text-muted-foreground">{u.rule_id}</span>
                </div>
              ))}
            </div>
          </Measure>
          <Measure
            question="Cases decided correctly"
            now={`${correct} of ${result.dossiers.length}`}
            before={baseCorrect !== undefined ? `${baseCorrect} of ${base!.dossiers.length}` : undefined}
            detail="The question a regulator actually asks — the disposition each submission comes out with"
          />
          <Measure
            question="Weight the evidence carries"
            now={totalWeight(result)}
            before={base && totalWeight(base)}
            detail="What severity moves. A case's decision is a step over this, so a severity edit can change the weight without changing the decision — and that is still a change."
          />
        </div>
      </section>

      <section>
        <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          The decision on each submission
        </h4>
        <p className="mt-1 text-[11px] text-muted-foreground">
          The corpus only says whether a submission should have been authorised, not which
          adverse outcome it deserved — so refuse, authorise with conditions and inconclusive
          all count as caught here.
        </p>
        <div className="mt-1.5 flex flex-col gap-1">
          {result.dossiers.map((d) => {
            const was = compare?.dossier_changes.find((c) => c.dossier_id === d.dossier_id)
            return (
              <div key={d.dossier_id} className={cn('flex items-center gap-2 rounded border px-2 py-1.5 text-[12px]',
                d.correct ? 'border-emerald-500/30 bg-emerald-500/[0.04]' : 'border-red-500/30 bg-red-500/[0.05]')}>
                <span className="font-mono text-[10.5px]">{d.dossier_id}</span>
                <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                  {weightLabel(d, base?.dossiers.find((x) => x.dossier_id === d.dossier_id))}
                </span>
                {was && <span className="font-mono text-[10.5px] text-muted-foreground line-through">{disp(was.before)}</span>}
                <span>{disp(d.actual)}</span>
                {/* A bare ✗ says a case is wrong without saying what it should
                    have been, which is the only part that tells you what to
                    tune. */}
                {!d.correct && <span className="text-[11px] text-muted-foreground">should be {disp(d.expected)}</span>}
                <span className={d.correct ? 'text-emerald-700 dark:text-emerald-400' : 'text-red-700 dark:text-red-400'}>
                  {d.correct ? '✓' : '✗'}
                </span>
              </div>
            )
          })}
        </div>
      </section>

      {compare?.comparable && compare.flips.length > 0 && <Flips compare={compare} />}

      <details className="rounded-lg border bg-muted/20 [&_summary::-webkit-details-marker]:hidden">
        <summary className="cursor-pointer list-none px-3 py-2 text-[12px] font-medium text-muted-foreground">
          How far to trust these numbers
        </summary>
        <div className="flex flex-col gap-4 border-t px-3 py-3">
          {result.unevaluated_domains.length > 0 && (
            <p className="rounded border border-amber-500/30 bg-amber-500/[0.05] px-2 py-1.5 text-[11.5px] text-amber-700 dark:text-amber-400">
              Not evaluated by this mechanical sweep: {result.unevaluated_domains.join(', ')} — every
              active rule there is model-judged. These numbers say nothing about them.
            </p>
          )}
          <p className="text-[11px] leading-4 text-muted-foreground">
            Labels say “this run had F42”, not “this rule should fire here”. Per-rule numbers inherit
            the labels of the failures a rule declares — diagnostic, not independent validation. And a
            detection with no label may be a false positive or a missing label; the sandbox cannot
            tell you which.
          </p>
        </div>
      </details>
    </>
  )
}

function Flips({ compare }: { compare: SweepComparison }) {
  const LABEL: Record<string, { text: string; tone: string }> = {
    caught: { text: 'Newly caught', tone: 'text-emerald-700 dark:text-emerald-400' },
    fixed_false_positive: { text: 'False positive cleared', tone: 'text-emerald-700 dark:text-emerald-400' },
    lost: { text: 'No longer caught', tone: 'text-red-700 dark:text-red-400' },
    new_false_positive: { text: 'New false positive', tone: 'text-red-700 dark:text-red-400' },
  }
  return (
    <section>
      <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        Every outcome this edit moved · {compare.flips.length}
      </h4>
      <div className="mt-1.5 flex flex-col gap-1">
        {compare.flips.map((f, i) => (
          <div key={i} className="flex items-baseline gap-2 text-[12px]">
            <span className={cn('w-44 shrink-0', LABEL[f.direction]?.tone)}>
              {LABEL[f.direction]?.text ?? f.direction.replaceAll('_', ' ')}
            </span>
            <span className="font-mono text-[10.5px] text-muted-foreground">{f.run_ref ?? f.dossier_id}</span>
            <span className="ml-auto font-mono text-[10.5px]">{f.failure}</span>
          </div>
        ))}
      </div>
      {/* The rule-by-rule view of the same change. A flip says which failure
          moved on which run; this says which rule's behaviour did it, which is
          the thing you can actually edit. */}
      <RuleDiff compare={compare} />
    </section>
  )
}

/** Sweep results carry the disposition's wire value, and the corpus's own
 *  coarser ground truth ('authorise' / 'not-authorise') alongside it. Render
 *  both the way the rest of the console reads them. */
function disp(value: string): string {
  if (value === 'not-authorise') return 'anything but authorise'
  if (value === 'unavailable') return 'no decision reached'
  return DISPOSITION_LABEL[value as Disposition] ?? value
}

function Promote({ draftId, sweepId, officer, onDone, busy }: {
  draftId: string; sweepId: string; officer: string; onDone: () => void; busy: boolean
}) {
  const [rationale, setRationale] = useState('')
  const [saving, setSaving] = useState(false)
  const submit = async () => {
    setSaving(true)
    try {
      const out = await promoteDraft({ draft_id: draftId, sweep_id: sweepId, promoted_by: officer, rationale })
      toast.success(`Promoted — ${out.domain} v${out.from_version} → v${out.to_version}`)
      onDone()
    } catch (e) { toast(String(e)) } finally { setSaving(false) }
  }
  return (
    <section className="rounded-lg border bg-muted/30 p-3">
      <h4 className="flex items-center gap-1.5 text-[12.5px] font-semibold">
        <ShieldCheck className="size-3.5" />Promote to policy
      </h4>
      <p className="mt-1 text-[11.5px] leading-4 text-muted-foreground">
        A named act on the ledger, carrying the sweep it rested on — so “what did you know when you
        changed this?” has an answer.
      </p>
      <textarea rows={2} value={rationale} onChange={(e) => setRationale(e.target.value)}
        placeholder="Why this rulebook should be in force." aria-label="Promotion rationale"
        className="mt-2 w-full rounded border bg-background p-2 text-[12.5px]" />
      <Button size="sm" className="mt-2" onClick={submit}
        disabled={busy || saving || rationale.trim().length < 10}>
        {saving ? 'Promoting…' : `Promote as ${officer}`}
      </Button>
    </section>
  )
}
