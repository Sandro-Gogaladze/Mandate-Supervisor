// schemas/sandbox.py, as the console sees it.

/** schemas/ruleset.py::Rule — only the fields the sandbox reads or edits. */
export interface Rule {
  rule_id: string
  type: string
  status: 'active' | 'draft' | 'retired'
  evaluation: 'computable' | 'judged'
  severity_weight: number
  description: string
  failures: string[]
  params: Record<string, unknown>
}

export interface SandboxDomain {
  domain: string
  label: string
  version: string
  rules: number
  judged: number
  tunable: number
}

/** How a sweep was taken. `mechanical` runs no model: ~24s, reproducible to
 *  the byte, and silent on every model-judged rule. `live` runs the whole
 *  pipeline: ~6 min and real spend, scores the judged rules too, and does NOT
 *  reproduce — three live sweeps of one unchanged rulebook scored 33, 35 and
 *  40 true positives. The two never compare with each other. */
export type SweepMode = 'mechanical' | 'live'

export interface Metrics { tp: number; fp: number; fn: number }

export interface RuleScore {
  rule_id: string
  domain: string
  status: string
  evaluation: string
  severity_weight: number
  failures: string[]
  fired: number
  metrics: Metrics
  clean_run_hits: string[]
}

export interface DossierOutcome {
  dossier_id: string
  expected: string
  actual: string
  correct: boolean
  planted_defects: number
  clean_runs: number
  /** What severity actually moves. The disposition is a step function over
   * this, so a severity edit that does not cross a tier boundary shows up
   * here and nowhere else. */
  weight_per_run: number | null
  hard_gates: number
  /** Adequacy gaps the authorisation policy raised. A mechanical sweep never
   * runs a judged rule, so coverage falls below the policy floor on every
   * submission and the disposition is `incomplete-submission` whatever the
   * rulebook caught — which the corpus's coarse label counts as correct.
   * This is what lets the scorecard say so. */
  adequacy_gaps: number
}

export interface SweepResult {
  overall: Metrics
  dossiers: DossierOutcome[]
  per_rule: Record<string, RuleScore>
  per_failure: Record<string, Metrics>
  per_domain: Record<string, Metrics>
  clean_runs: number
  clean_run_false_positives: string[]
  missed: { dossier_id: string; run_ref: string | null; failure: string; what: string }[]
  unexpected: { dossier_id: string; run_ref: string | null; failure: string; rule_id: string | null }[]
  dead_rules: string[]
  unevaluated_domains: string[]
  /** Failures only a model-judged rule can establish. On a live sweep these
   * are scored, and they do not reproduce: three live sweeps of one unchanged
   * rulebook returned 33, 35 and 40 true positives. Flips on these failures
   * are shown but never counted in the verdict. */
  model_judged_failures: string[]
}

export interface Sweep {
  sweep_id: string
  domain: string
  ruleset_ref: string
  ruleset_digest: string
  label: string
  pins: {
    corpus_digest: string
    /** Provenance only — it no longer gates comparability. See SweepPins. */
    code_revision: string
    mode: SweepMode
    /** Empty on a sweep taken before these were recorded; such a sweep
     * refuses to be compared rather than assuming nothing moved. */
    policy_digest: string
    engine_digest: string
  }
  started_at: string
  finished_at: string | null
  result: SweepResult | null
  error: string | null
}

export interface RulesetDraft {
  draft_id: string
  domain: string
  base_version: string
  label: string
  digest: string
  created_by: string
  created_at: string
  notes: string | null
  edits: string[]
}

/** `current` is whether that scorecard still describes this version — the
 *  same rules, over the same corpus, policy and pipeline. `stale_reason` says
 *  which of those moved when it does not. A draft edited since its sweep, a
 *  book promoted past the version its sweep measured, and a sweep taken
 *  before a specialist was edited are all `swept` and none is `current`. */
export interface VersionGraph {
  domain: string
  active: {
    version: string; as_of: string; rules: number
    sweep_id: string | null; current?: boolean; stale_reason?: string | null
    mode?: string | null
  }
  superseded: string[]
  drafts: {
    draft: RulesetDraft; sweep_id: string | null; swept: boolean
    current?: boolean; stale_reason?: string | null; mode?: string | null
  }[]
}

export interface RulebookView {
  ref: string
  domain: string
  label: string
  editable: boolean
  edits: string[]
  /** What a sweep pins. A stored scorecard whose digest differs measured
   * different rules than the ones on screen. */
  ruleset_digest: string
  ruleset: { ruleset_id: string; version: string; as_of: string; rules: Rule[] }
}

export interface Flip {
  dossier_id: string
  run_ref: string | null
  failure: string
  direction: 'caught' | 'lost' | 'new_false_positive' | 'fixed_false_positive'
  /** Established only by a model-judged rule, so it moves between two runs of
   * the SAME rulebook. Shown, never counted as this draft's doing. */
  judged: boolean
}

export interface SweepComparison {
  base: Sweep
  candidate: Sweep
  comparable: boolean
  incomparable_reason: string | null
  flips: Flip[]
  rule_deltas: { rule_id: string; before: RuleScore | null; after: RuleScore | null }[]
  dossier_changes: { dossier_id: string; before: string; after: string; expected: string; now_correct: boolean }[]
}

/** Below this many labelled examples a rate is noise wearing a number —
 * schemas/sandbox.py::MIN_EVIDENCE. */
export const MIN_EVIDENCE = 5

/** The flips a rulebook edit can be held responsible for. */
export const decisive = (flips: Flip[]) => flips.filter((f) => !f.judged)

export const labelled = (s: RuleScore) => s.metrics.tp + s.metrics.fn
export const trustworthy = (s: RuleScore) => labelled(s) >= MIN_EVIDENCE
export const recall = (m: Metrics) => (m.tp + m.fn ? m.tp / (m.tp + m.fn) : null)
export const precision = (m: Metrics) => (m.tp + m.fp ? m.tp / (m.tp + m.fp) : null)
