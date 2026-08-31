// Single source of truth for how each pipeline node/agent is presented —
// icon, label, and color — so PipelineGraph, StepFeed, and ResultsPanel
// can't drift into three different sets of labels for the same node.
import {
  Inbox,
  SearchCheck,
  Waypoints,
  ShieldCheck,
  Fingerprint,
  ScrollText,
  TrendingUp,
  GitMerge,
  RotateCcw,
  FileText,
  FileCheck2,
  Gauge,
  UserRoundCheck,
  type LucideIcon,
} from 'lucide-react'

export interface NodeMeta {
  label: string
  icon: LucideIcon
  /** Tailwind color word used to derive text/bg/border/ring utility classes. */
  color: 'slate' | 'blue' | 'violet' | 'teal' | 'orange' | 'indigo'
  /** One-line, plain-English job description — shown on the Overview page
   * and the sidebar's specialist roster. Only the four specialists carry
   * one; plumbing nodes (ingest/dispatch/…) don't need a sales pitch. */
  blurb?: string
}

export const NODE_META: Record<string, NodeMeta> = {
  ingest: { label: 'Ingest', icon: Inbox, color: 'slate' },
  dispatch: { label: 'Dispatch', icon: Waypoints, color: 'slate' },
  mandate: {
    label: 'Mandate',
    icon: ShieldCheck,
    color: 'blue',
    blurb: 'Checks every Cart and Payment against the human-signed Intent — caps, scope, approved counterparties, chain integrity.',
  },
  kya: {
    label: 'KYA',
    icon: Fingerprint,
    color: 'violet',
    blurb: 'Verifies the agent’s identity credential — Ed25519 signatures, issuer trust, and a delegation chain that ends at a real human.',
  },
  log: {
    label: 'Log',
    icon: ScrollText,
    color: 'teal',
    blurb: 'Reads the full transaction history for structuring, counterparty concentration, and velocity anomalies.',
  },
  drift: {
    label: 'Drift',
    icon: TrendingUp,
    color: 'orange',
    blurb: 'Compares recent behaviour against the agent’s own established baseline — amounts, cadence, counterparty mix.',
  },
  escalate_check: { label: 'Escalate check', icon: GitMerge, color: 'slate' },
  bump_round: { label: 'Bump round', icon: RotateCcw, color: 'slate' },
  critic: {
    label: 'Critic',
    icon: FileCheck2,
    color: 'slate',
    blurb: 'Deterministic check that every model-judged claim quotes numbers that exist in the evidence it was given.',
  },
  synthesizer: {
    label: 'Synthesizer',
    icon: GitMerge,
    color: 'indigo',
    blurb: 'Finds relationships between findings — three detectors seeing one event — without touching the findings or the score.',
  },
  investigator: {
    label: 'Investigator',
    icon: SearchCheck,
    color: 'teal',
    blurb: 'Answers open questions with read-only lookups — transactions, counterparties, issuers, rules. Observations only, never a verdict.',
  },
  load_context: { label: 'Load record', icon: Inbox, color: 'slate' },
  orchestrate: { label: 'Orchestrate', icon: Waypoints, color: 'slate' },
  record: { label: 'Record', icon: ScrollText, color: 'slate' },
  load_record: { label: 'Load record', icon: Inbox, color: 'slate' },
  draft_report: {
    label: 'Draft report',
    icon: FileText,
    color: 'indigo',
    blurb: 'Writes the supervisory report from the structured findings — every claim must cite a real finding.',
  },
  grounding_check: { label: 'Grounding check', icon: FileCheck2, color: 'slate' },
  risk_score: { label: 'Risk score', icon: Gauge, color: 'slate' },
  human_gate: { label: 'Human gate', icon: UserRoundCheck, color: 'slate' },
}

/** The four review agents, in display order. */
export const SPECIALISTS = ['mandate', 'kya', 'log', 'drift'] as const

export function nodeMeta(id: string): NodeMeta {
  return NODE_META[id] ?? { label: id, icon: Waypoints, color: 'slate' }
}

/** Text/bg/border classes for an agent's "identity" color — used at rest,
 * independent of live run status (pending/active/done, handled separately
 * in PipelineGraph). */
export const AGENT_TONE: Record<NodeMeta['color'], string> = {
  slate: 'text-slate-600 bg-slate-500/10 border-slate-500/20 dark:text-slate-300',
  blue: 'text-blue-600 bg-blue-500/10 border-blue-500/20 dark:text-blue-400',
  violet: 'text-violet-600 bg-violet-500/10 border-violet-500/20 dark:text-violet-400',
  teal: 'text-teal-600 bg-teal-500/10 border-teal-500/20 dark:text-teal-400',
  orange: 'text-orange-600 bg-orange-500/10 border-orange-500/20 dark:text-orange-400',
  indigo: 'text-indigo-600 bg-indigo-500/10 border-indigo-500/20 dark:text-indigo-400',
}

/** A stronger version of AGENT_TONE for larger surfaces (the pipeline
 * graph's icon roundel at rest) — same hue family, more present than a
 * small badge needs. */
export const AGENT_ICON: Record<NodeMeta['color'], { bg: string; text: string; ring: string }> = {
  slate: { bg: 'bg-slate-500/15', text: 'text-slate-600 dark:text-slate-300', ring: 'ring-slate-500/20' },
  blue: { bg: 'bg-blue-500/15', text: 'text-blue-600 dark:text-blue-400', ring: 'ring-blue-500/20' },
  violet: { bg: 'bg-violet-500/15', text: 'text-violet-600 dark:text-violet-400', ring: 'ring-violet-500/20' },
  teal: { bg: 'bg-teal-500/15', text: 'text-teal-600 dark:text-teal-400', ring: 'ring-teal-500/20' },
  orange: { bg: 'bg-orange-500/15', text: 'text-orange-600 dark:text-orange-400', ring: 'ring-orange-500/20' },
  indigo: { bg: 'bg-indigo-500/15', text: 'text-indigo-600 dark:text-indigo-400', ring: 'ring-indigo-500/20' },
}
