// Per-scenario-label icon + severity, shared between the case queue cards
// and the case review header badge.
import {
  CircleCheckBig,
  ShieldAlert,
  Link2Off,
  UserSearch,
  SplitSquareHorizontal,
  ActivitySquare,
  Syringe,
  FileClock,
  type LucideIcon,
} from 'lucide-react'
import type { ScenarioLabel } from './types'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

export type Severity = 'clean' | 'flag' | 'unreviewed'

export interface ScenarioMeta {
  icon: LucideIcon
  severity: Severity
  text: string
}

export const SCENARIO_META: Record<ScenarioLabel, ScenarioMeta> = {
  compliant: { icon: CircleCheckBig, severity: 'clean', text: 'compliant' },
  mandate_breaching: { icon: ShieldAlert, severity: 'flag', text: 'mandate breaching' },
  broken_chain: { icon: Link2Off, severity: 'flag', text: 'broken chain' },
  synthetic_identity: { icon: UserSearch, severity: 'flag', text: 'synthetic identity' },
  structuring: { icon: SplitSquareHorizontal, severity: 'flag', text: 'structuring' },
  drift: { icon: ActivitySquare, severity: 'flag', text: 'drift' },
  prompt_injection: { icon: Syringe, severity: 'flag', text: 'prompt injection' },
}

// A real submission has no ground-truth label — that's the point of
// reviewing it. Shown instead of a scenario badge for anything that isn't
// one of the seven demo corpus cases.
export const UNREVIEWED_META: ScenarioMeta = { icon: FileClock, severity: 'unreviewed', text: 'awaiting review' }

export function scenarioMeta(label: ScenarioLabel | null): ScenarioMeta {
  return label ? SCENARIO_META[label] : UNREVIEWED_META
}

export const SEVERITY_BADGE: Record<Severity, string> = {
  clean: 'bg-emerald-500/10 text-emerald-700 border-emerald-500/25 dark:text-emerald-400',
  flag: 'bg-amber-500/10 text-amber-700 border-amber-500/25 dark:text-amber-400',
  unreviewed: 'bg-muted text-muted-foreground border-transparent',
}

// The seeded ground-truth label. Deliberately shown ONLY inside the Case
// file tab, as corpus metadata — queue cards and the review header stay
// verdict-free so the live run is a discovery, not a confirmation of a
// badge the officer already read.
export function LabelBadge({ label }: { label: ScenarioLabel | null }) {
  const meta = scenarioMeta(label)
  const Icon = meta.icon
  return (
    <Badge variant="outline" className={cn('gap-1 font-normal', SEVERITY_BADGE[meta.severity])}>
      <Icon className="size-3" />
      {meta.text}
    </Badge>
  )
}
