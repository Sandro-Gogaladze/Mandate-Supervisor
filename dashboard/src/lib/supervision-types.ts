import type { LedgerEvent } from './types'
// Dossier-native additions to the existing case-room contracts.
export interface EvidenceRef { kind: string; ref: string; value?: unknown }
export interface Fact {
  fact_id: string; domain: string; rule_id: string | null; run_ref: string | null
  kind: 'breach' | 'satisfied' | 'measurement' | 'absent'
  statement: string; values: Record<string, unknown>; refs: EvidenceRef[]
  absent_reason: string | null; missing: string | null
}
export interface Assessment {
  assessment_id: string; agent: string; rule_id: string | null; round: number
  verdict: 'breach' | 'concern' | 'explained' | 'clear' | 'inconclusive'
  confidence: string; severity_floor: number; severity_assessed: number
  narrative: string; fact_ids: string[]; run_refs: string[]; evidence_refs: EvidenceRef[]
  supersedes: string | null; review_run_refs: string[] | null
}
export type Disposition = 'authorise' | 'monitor' | 'refuse' | 'incomplete-submission'
export const DISPOSITION_LABEL: Record<Disposition, string> = {
  authorise: 'Authorise', monitor: 'Authorise with conditions', refuse: 'Refuse',
  'incomplete-submission': 'Incomplete submission',
}
export interface RunResult {
  run_id: string; verdict: 'clean' | 'breach' | 'unresolved'
  target_configuration: boolean; assessment_ids: string[]; weight: number
}
export interface Recommendation {
  disposition: Disposition; policy_version: string; policy_status: string
  recommendation_digest: string; clean_runs: number; target_runs: number
  rules_exercised: number; active_rules: number; rule_coverage: number
  unresolved_assessments: number; weight_per_run: number; runs: RunResult[]
  hard_gates: { rule_id: string; reason: string; assessment_id: string; run_refs: string[] }[]
  adequacy: { code: string; reason: string }[]
  factors: {
    assessment_id: string; rule_id: string | null; agent: string; weight: number; dedup_factor: number
    severity_floor: number; severity_assessed: number; confidence: 'certain' | 'probable' | 'possible'
    run_refs: string[]
  }[]
  conditions: string[]; limitations: string[]
}
export interface SignedDecision {
  reviewer: string; disposition: Disposition; rationale: string; conditions: string[]
  recommendation_digest: string; decided_at?: string; basis?: Recommendation
}
export interface DossierDetail {
  dossier: {
    dossier_id: string; institution_id: string; operator_id: string; agent_id: string
    submission_purpose: string
    submission_context: {
      submitted_at: string; runs_executed_total: number; runs_submitted: number; environment: string
      deployment_target: { model_version: string; prompt_release_ref: string; tool_servers: string[] }
    }
  }
  facts: Fact[]; assessments: Assessment[]; recommendation: Recommendation | null
  decisions: SignedDecision[]; last_seq: number
}
export interface ExecutionSummary {
  run_id: string; started_at: string; request: string; merchant: string | null
  amount: number | null; currency: string | null; outcome: string; review: RunResult | null
}
export interface ExecutionDetail {
  run: {
    run_id: string; user_prompt: string; outcome: string; started_at: string; ended_at: string
    intent_mandate: { intent_mandate_id: string; natural_language_intent: string; authorization_scope: Record<string, unknown> }
    construction_context: {
      model: { declared_version: string; observed_version: string }; policy_version: { release_ref: string }
      tool_calls: { sequence: number; tool_name: string; server_id: string; result_excerpt?: { source: string; fields: string[]; text: string; truncated: boolean } | null; arguments: Record<string, unknown> }[]
    }
    consent_ceremony: { occurred: boolean; ceremony_scope: string; rendered_values: Record<string, unknown> | null } | null
    cart: { cart_mandate_id: string; cart_total: number; currency: string; merchant: { name: string }; line_items: { sku: string; description: string; qty: number; unit_price: number }[] } | null
    payment: { payment_mandate_id: string; amount: number; currency: string; settlement_status: string; payee: Record<string, unknown> } | null
    controls_evaluated: { control_id: string; outcome: string; override?: Record<string, unknown> | null }[]
  }
  transactions: { transaction_id: string; amount: number; currency: string; status: string; timestamp: string }[]
}
export interface PortfolioFinding { finding_id: string; failure: string; subject_refs: string[]; summary: string; evidence: Record<string, unknown> }
export interface PortfolioSweep { sweep_id: string | null; completed_at?: string; findings: PortfolioFinding[] }

// One specialist's live progress on the AG-UI stream (pipeline/graph.py::
// _stream_specialist). Small on purpose: counts and a ledger sequence range,
// never the facts themselves.
export interface SpecialistProgress {
  agent: string
  run_id: string
  status: 'reasoning' | 'complete'
  events: LedgerEvent[]
  fact_counts: { total: number; satisfied: number; breach: number; absent: number; measurement: number }
  fact_seq_range: [number, number] | null
}
