import { useEffect, useState } from 'react'
import { Network, RotateCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { getPortfolio, sweepPortfolio } from '@/lib/api'
import type { PortfolioSweep } from '@/lib/supervision-types'

export function PortfolioPanel({ onOpenDossier }: { onOpenDossier: (id: string) => void }) {
  const [sweep, setSweep] = useState<PortfolioSweep | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { getPortfolio().then(setSweep).catch(e => setError(String(e))) }, [])
  async function run() { setBusy(true); setError(''); try { setSweep(await sweepPortfolio()) } catch (e) { setError(String(e)) } finally { setBusy(false) } }
  return <div className="mx-auto max-w-5xl space-y-5 p-6"><div className="flex items-center justify-between gap-4"><div><h1 className="font-heading text-2xl font-semibold">Portfolio</h1><p className="mt-1 text-sm text-muted-foreground">Shared counterparties, model concentration and repeated payloads across submitted agents.</p></div><Button onClick={run} disabled={busy}><RotateCw className={busy ? 'animate-spin' : ''} />{busy ? 'Sweeping…' : 'Run sweep'}</Button></div>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    {sweep?.sweep_id ? <p className="text-xs text-muted-foreground">{sweep.sweep_id} · {sweep.completed_at}</p> : <p className="rounded-lg border bg-card p-5 text-sm text-muted-foreground">No portfolio sweep recorded yet.</p>}
    {sweep?.findings.map(f => <div key={f.finding_id} className="rounded-xl border bg-card p-4"><div className="flex items-center gap-2"><Network className="size-4 text-muted-foreground" /><Badge variant="outline">{f.failure}</Badge><span className="font-mono text-[10px] text-muted-foreground">{f.finding_id}</span></div><p className="mt-3 text-sm leading-relaxed">{f.summary}</p><div className="mt-3 flex flex-wrap gap-2">{f.subject_refs.map(id => <Button key={id} variant="outline" size="sm" onClick={() => onOpenDossier(id)}>{id}</Button>)}</div></div>)}
    {sweep?.sweep_id && !sweep.findings.length && <p className="text-sm text-muted-foreground">No cross-dossier findings in this sweep.</p>}
  </div>
}
