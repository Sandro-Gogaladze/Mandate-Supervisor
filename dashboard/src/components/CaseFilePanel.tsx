import {
  ArrowDown,
  Banknote,
  Building2,
  Fingerprint,
  Landmark,
  Quote,
  ReceiptText,
  ScrollText,
  ShieldCheck,
  UserRound,
} from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { RawCaseBundle, ScenarioLabel } from '@/lib/types'
import { LabelBadge } from '@/lib/scenario-meta'
import { cn } from '@/lib/utils'

function fmtMoney(amount: number, currency: string): string {
  const symbol = currency === 'GEL' ? '₾' : currency === 'EUR' ? '€' : currency === 'USD' ? '$' : `${currency} `
  return `${symbol}${amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

function SectionCard({
  icon: Icon,
  title,
  children,
  className,
}: {
  icon: typeof Building2
  title: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <Card className={cn('gap-0 overflow-hidden p-0', className)}>
      <div className="flex items-center gap-2 border-b bg-muted/40 px-4 py-2.5">
        <Icon className="size-4 text-muted-foreground" />
        <span className="text-sm font-semibold">{title}</span>
      </div>
      <div className="p-4">{children}</div>
    </Card>
  )
}

function KV({ label, children, mono }: { label: string; children: React.ReactNode; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={cn('mt-0.5 text-sm text-foreground', mono && 'font-mono text-[13px]')}>{children}</div>
    </div>
  )
}

export function CaseFilePanel({ raw, label = null }: { raw: RawCaseBundle; label?: ScenarioLabel | null }) {
  const { kya_credential: cred, mandate_chain: chain, transaction_history: txs } = raw
  const intent = chain.intent
  const scope = intent.authorization_scope
  const totalVolume = txs.reduce((sum, t) => sum + t.amount, 0)
  const currency = scope.currency

  return (
    <ScrollArea className="h-full">
      <div className="mx-auto flex max-w-5xl flex-col gap-4 p-4">
        {/* The seeded ground truth lives here and only here, as corpus
            metadata — never on the queue or the review header, where it
            would announce the verdict before the run. */}
        {label && (
          <div className="-mb-1 flex items-center justify-end gap-2">
            <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              corpus ground truth
            </span>
            <LabelBadge label={label} />
          </div>
        )}
        {/* What the human actually authorised — the whole case pivots on
            this sentence, so it leads the dossier. */}
        <Card className="gap-2 bg-primary/[0.04] p-5">
          <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            <Quote className="size-3.5" />
            What the human authorised
          </div>
          <blockquote className="font-heading text-lg font-medium leading-snug">
            “{intent.natural_language_intent}”
          </blockquote>
          <div className="mt-1 text-[13px] text-muted-foreground">
            — {intent.principal.name}, {intent.principal.role} · consent via {intent.consent.method.replace(/_/g, ' ')} ·{' '}
            {fmtDate(intent.consent.timestamp)}
          </div>
        </Card>

        <div className="grid gap-4 lg:grid-cols-2">
          <SectionCard icon={Landmark} title="Authorization scope">
            <div className="grid grid-cols-2 gap-x-4 gap-y-3">
              <KV label="Purpose">{scope.purpose_category.replace(/_/g, ' ')}</KV>
              <KV label="Valid">
                {fmtDate(scope.valid_from)} → {fmtDate(scope.valid_until)}
              </KV>
              <KV label="Per-transaction cap" mono>
                {fmtMoney(scope.max_transaction_amount, currency)}
              </KV>
              <KV label="Cumulative cap" mono>
                {scope.max_cumulative_amount != null ? fmtMoney(scope.max_cumulative_amount, currency) : '—'}
              </KV>
            </div>
            <Separator className="my-3.5" />
            <KV label="Approved counterparties">
              <div className="mt-1 flex flex-wrap gap-1.5">
                {(scope.allowed_counterparties ?? []).map((cp) => (
                  <Badge key={cp.counterparty_id} variant="secondary" className="font-normal">
                    {cp.name}
                  </Badge>
                ))}
                {(scope.allowed_counterparties ?? []).length === 0 && (
                  <span className="text-sm text-muted-foreground">none listed</span>
                )}
              </div>
            </KV>
            <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3">
              <KV label="Merchant categories" mono>
                {(scope.allowed_merchant_categories ?? []).join(', ') || '—'}
              </KV>
              <KV label="Geographic scope" mono>
                {scope.geographic_scope ?? '—'}
              </KV>
            </div>
          </SectionCard>

          <SectionCard icon={Fingerprint} title="Agent credential">
            <div className="grid grid-cols-2 gap-x-4 gap-y-3">
              <KV label="Agent">{cred.agent_name}</KV>
              <KV label="Operator">{cred.operator_firm}</KV>
              <KV label="Issuer">{cred.issuer.issuer_name}</KV>
              <KV label="Validity">
                {fmtDate(cred.issued_at)} → {fmtDate(cred.expires_at)}
              </KV>
            </div>
            <Separator className="my-3.5" />
            <KV label="Delegation chain">
              <div className="mt-1.5 flex flex-col gap-1">
                {[...cred.delegation_chain]
                  .sort((a, b) => a.level - b.level)
                  .map((entry, i, arr) => (
                    <div key={entry.level} className="flex flex-col gap-1">
                      <div className="flex items-center gap-2 text-[13px]">
                        <span
                          className={cn(
                            'inline-flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold',
                            entry.holder_type === 'human'
                              ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400'
                              : 'bg-violet-500/15 text-violet-700 dark:text-violet-400',
                          )}
                        >
                          {entry.level}
                        </span>
                        <span className="font-medium">{entry.name}</span>
                        <Badge variant="outline" className="h-5 px-1.5 text-[10px] font-normal">
                          {entry.holder_type === 'human' ? (
                            <UserRound className="size-2.5" />
                          ) : (
                            <ShieldCheck className="size-2.5" />
                          )}
                          {entry.holder_type}
                        </Badge>
                      </div>
                      {i < arr.length - 1 && <ArrowDown className="ml-[7px] size-3 text-muted-foreground/50" />}
                    </div>
                  ))}
              </div>
            </KV>
            <Separator className="my-3.5" />
            <KV label="Capabilities">
              <div className="mt-1 flex flex-wrap gap-1.5">
                {cred.capabilities.map((cap) => (
                  <Badge key={cap} variant="outline" className="font-mono text-[10px] font-normal">
                    {cap}
                  </Badge>
                ))}
              </div>
            </KV>
          </SectionCard>
        </div>

        <SectionCard icon={ReceiptText} title="Mandate chain — the transaction under review">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-lg border bg-muted/30 p-3.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Intent</span>
                <span className="font-mono text-[10px] text-muted-foreground">{intent.intent_mandate_id}</span>
              </div>
              <div className="mt-2 text-sm">
                Signed by <span className="font-medium">{intent.principal.name}</span>
              </div>
              <div className="text-[13px] text-muted-foreground">{fmtDate(intent.issued_at)}</div>
            </div>
            <div className="rounded-lg border bg-muted/30 p-3.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Cart</span>
                <span className="font-mono text-[10px] text-muted-foreground">{chain.cart.cart_mandate_id}</span>
              </div>
              <div className="mt-2 text-sm">
                {chain.cart.line_items.length} item{chain.cart.line_items.length === 1 ? '' : 's'} ·{' '}
                <span className="font-medium">{chain.cart.merchant.name}</span>
              </div>
              <div className="font-mono text-[13px] text-muted-foreground">
                {fmtMoney(chain.cart.cart_total, chain.cart.currency)} · MCC {chain.cart.merchant.mcc}
              </div>
            </div>
            <div className="rounded-lg border bg-muted/30 p-3.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Payment</span>
                <span className="font-mono text-[10px] text-muted-foreground">{chain.payment.payment_mandate_id}</span>
              </div>
              <div className="mt-2 flex items-center gap-1.5 text-sm">
                <Banknote className="size-3.5 text-muted-foreground" />
                <span className="font-medium">{fmtMoney(chain.payment.amount, chain.payment.currency)}</span>
                <Badge
                  variant="outline"
                  className={cn(
                    'h-5 px-1.5 text-[10px] font-normal',
                    chain.payment.settlement_status === 'settled' &&
                      'border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
                  )}
                >
                  {chain.payment.settlement_status}
                </Badge>
              </div>
              <div className="text-[13px] text-muted-foreground">
                {chain.payment.payment_method.instrument_id_masked} · {chain.payment.payment_method.issuer}
              </div>
            </div>
          </div>
        </SectionCard>

        <SectionCard icon={ScrollText} title={`Transaction history — ${txs.length} on record`}>
          <div className="mb-3 flex flex-wrap gap-x-6 gap-y-1 text-[13px] text-muted-foreground">
            <span>
              Total volume: <span className="font-mono text-foreground">{fmtMoney(totalVolume, currency)}</span>
            </span>
            <span>
              Distinct counterparties:{' '}
              <span className="font-mono text-foreground">{new Set(txs.map((t) => t.counterparty_id)).size}</span>
            </span>
          </div>
          <div className="max-h-80 overflow-auto rounded-lg border">
            <Table>
              <TableHeader className="sticky top-0 bg-card">
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Counterparty</TableHead>
                  <TableHead className="text-right">MCC</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead className="text-right">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {txs.map((t) => (
                  <TableRow key={t.transaction_id}>
                    <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">
                      {fmtDateTime(t.timestamp)}
                    </TableCell>
                    <TableCell className="max-w-52 truncate">{t.counterparty_name}</TableCell>
                    <TableCell className="text-right font-mono text-xs">{t.mcc}</TableCell>
                    <TableCell className="text-right font-mono text-[13px]">{fmtMoney(t.amount, t.currency)}</TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground">{t.status}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </SectionCard>
      </div>
    </ScrollArea>
  )
}
