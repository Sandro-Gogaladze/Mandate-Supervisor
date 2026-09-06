// Plain language for everything the transcript shows. A supervisor reads
// "Judging whether each cart answers the shopper's request", never
// `record_intent_fidelity`; the machine names stay on the ledger.
import type { Assessment, SpecialistProgress } from './supervision-types'

/** What a specialist is doing while a given tool call streams. */
export const TOOL_LABELS: Record<string, string> = {
  route_supervisor_request: 'Working out what to run',
  record_intent_fidelity: 'Judging whether each cart answers the shopper’s own words',
  record_observations: 'Looking for anything the fixed rules would not catch',
  write_narration: 'Writing up the credential review',
  record_log_analysis: 'Judging the transaction pattern',
  record_drift_analysis: 'Judging whether behaviour has shifted, and since when',
  record_injection_analysis: 'Judging whether the agent acted on something it read',
  record_counterparty_analysis: 'Judging who really received the money',
  record_consent_analysis: 'Judging value for money against the alternatives',
  record_provenance_reconciliation: 'Reconciling the card, credential, register and observed calls',
  record_correlations: 'Connecting the findings to each other',
  draft_case_report: 'Drafting the supervisory report',
  record_investigation_answer: 'Writing the answer',
  get_transactions: 'Pulled the transaction history',
  get_counterparty_profile: 'Looked up a counterparty',
  get_issuer_record: 'Looked up a credential issuer',
  get_rule: 'Read a rule',
  recompute_stats: 'Recomputed the statistics',
  get_case_findings: 'Read the findings on record',
  get_run: 'Opened an execution run',
}

/** The agent a tool call belongs to. Eight specialists stream on one
 * channel and their step markers do not reliably precede their chunks, so a
 * call is attributed by the tool's name — unique per agent — not by the
 * step the stream happened to be in. */
export const TOOL_AGENT: Record<string, string> = {
  route_supervisor_request: 'orchestrator',
  record_intent_fidelity: 'mandate',
  record_observations: 'kya',
  write_narration: 'kya',
  record_log_analysis: 'log',
  record_drift_analysis: 'drift',
  record_injection_analysis: 'injection',
  record_counterparty_analysis: 'counterparty',
  record_consent_analysis: 'consent',
  record_provenance_reconciliation: 'provenance',
  record_correlations: 'synthesizer',
  draft_case_report: 'draft_report',
  record_investigation_answer: 'investigator',
  get_transactions: 'investigator',
  get_counterparty_profile: 'investigator',
  get_issuer_record: 'investigator',
  get_rule: 'investigator',
  recompute_stats: 'investigator',
  get_case_findings: 'investigator',
  get_run: 'investigator',
}

export function toolLabel(name: string): string {
  return TOOL_LABELS[name] ?? name.replaceAll('_', ' ').replace(/^\w/, (c) => c.toUpperCase())
}

/** Step names from the graph that are the orchestrator's own work. */
export const ORCHESTRATOR_STEPS = new Set(['ingest', 'bump_round', 'orchestrate', 'record', 'load_record', 'orchestrator'])

export const VERDICT_LABEL: Record<Assessment['verdict'], string> = {
  breach: 'Breach',
  concern: 'Concern',
  explained: 'Explained',
  clear: 'Clear',
  inconclusive: 'Inconclusive',
}

export const VERDICT_TONE: Record<Assessment['verdict'], string> = {
  breach: 'border-red-500/30 bg-red-500/[0.04] text-red-700 dark:text-red-400',
  concern: 'border-amber-500/30 bg-amber-500/[0.05] text-amber-700 dark:text-amber-400',
  explained: 'border-sky-500/30 bg-sky-500/[0.04] text-sky-700 dark:text-sky-400',
  clear: 'border-emerald-500/30 bg-emerald-500/[0.04] text-emerald-700 dark:text-emerald-400',
  inconclusive: 'border-dashed text-muted-foreground',
}

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

/** One sentence under a specialist's name: what it returned.
 *
 * `verdictCounts: false` drops the breach/concern tally and keeps only the
 * coverage tail. The caller passes it when a failure summary already leads
 * the line — "8 failures on 6 runs · 8 breaches on 6 runs" says one thing
 * twice, and the catalogue half is the one a reviewer acts on. */
export function specialistSummary(counts: SpecialistProgress['fact_counts'] | null, assessments: Assessment[], status: 'working' | 'done' | 'failed' | 'queued', { verdictCounts = true } = {}): string {
  if (status === 'queued') return 'Waiting for the briefing'
  if (!verdictCounts) {
    const tail: string[] = []
    if (counts?.satisfied) tail.push(`${counts.satisfied} rules satisfied`)
    if (counts?.absent) tail.push(`${counts.absent} could not be evaluated`)
    return tail.join(' · ')
  }
  const breaches = assessments.filter((a) => a.verdict === 'breach').length
  const concerns = assessments.filter((a) => a.verdict === 'concern').length
  const inconclusive = assessments.filter((a) => a.verdict === 'inconclusive').length
  const runs = new Set(assessments.filter((a) => a.verdict === 'breach').flatMap((a) => a.run_refs)).size
  const parts: string[] = []
  if (breaches) parts.push(`${plural(breaches, 'breach', 'breaches')}${runs ? ` on ${plural(runs, 'run')}` : ''}`)
  if (concerns) parts.push(plural(concerns, 'concern'))
  if (inconclusive) parts.push(`${inconclusive} not decided`)
  if (counts) {
    if (counts.satisfied) parts.push(`${counts.satisfied} rules satisfied`)
    if (counts.absent) parts.push(`${counts.absent} could not be evaluated`)
  }
  if (status === 'working') return parts.length ? `${parts.join(' · ')} so far` : 'Rules checked, now reasoning over the evidence'
  if (status === 'failed') return 'Judgement unavailable; the rule results are kept'
  if (!parts.length) return assessments.length ? `${plural(assessments.length, 'verdict')}, nothing adverse` : 'Nothing to report'
  return parts.join(' · ')
}

export function durationLabel(ms: number): string {
  if (ms < 1000) return 'under a second'
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`
  const m = Math.floor(ms / 60_000)
  const s = Math.round((ms % 60_000) / 1000)
  return `${m}m ${s}s`
}

export function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

/** A run's kind, in words. */
export const RUN_TITLE: Record<string, string> = {
  triage: 'Full review',
  investigation: 'Question',
  drafting: 'Report',
}

/** Skill ids → the agent they belong to. */
export const skillAgent = (skill: string) => skill.split('.')[0]
