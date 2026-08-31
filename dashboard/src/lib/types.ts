// Mirrors schemas/*.py + ledger/projection.py — kept hand-in-sync (no
// codegen yet) since the Python side is the source of truth.

export type ScenarioLabel =
  | 'compliant'
  | 'mandate_breaching'
  | 'broken_chain'
  | 'synthetic_identity'
  | 'structuring'
  | 'drift'
  | 'prompt_injection'

export type CaseStatus =
  | 'submitted'
  | 'triaged'
  | 'under_review'
  | 'investigating'
  | 'pending_decision'
  | 'issued'
  | 'closed_rejected'
  | 'closed_no_action'

export type DispositionTier = 'clear' | 'review' | 'escalate'

// What GET /cases returns per row — a projection summary. No case_path:
// cases are addressed by id, the bundle lives in the ledger.
export interface CaseSummary {
  case_id: string
  firm: string
  status: CaseStatus
  label: ScenarioLabel | null
  summary: string
  risk_total: number | null
  risk_tier: DispositionTier | null
  findings_count: number
  observations_count: number
  opened_by: string | null
  last_event_at: string
}

export type FindingAgent = 'mandate' | 'kya' | 'log' | 'drift'
export type ObservationAgent = FindingAgent | 'investigator'

export interface Finding {
  finding_id: string
  case_id: string
  agent: FindingAgent
  type: string
  rule_id: string | null
  severity_weight: number | null
  summary: string
  details: Record<string, unknown>
}

export interface Observation {
  case_id: string
  agent: ObservationAgent
  note: string
  cited_evidence: string
}

export interface Correlation {
  case_id: string
  finding_ids: string[]
  relationship: 'same_event' | 'causal' | 'corroborating' | 'contradictory'
  explanation: string
}

export interface ToolCallRecord {
  tool: string
  arguments: Record<string, unknown>
  result_digest: string
}

export interface InvestigationAnswer {
  case_id: string
  question_id: string
  question: string
  answer: string
  cited_evidence: string[]
  tool_calls: ToolCallRecord[]
}

export interface DispatchRecord {
  case_id: string
  run_id: string
  target: string
  skill: string
  instruction: string
  context_blocks: Record<string, unknown>
  context_digest: string
}

export interface ReportSection {
  title: string
  body: string
  cited_finding_ids: string[]
}

export interface DraftReport {
  case_id: string
  overall_assessment: string
  sections: ReportSection[]
  open_observations_note: string | null
}

export interface RiskFactor {
  agent: FindingAgent
  score: number
  finding_count: number
}

export interface RiskScore {
  case_id: string
  total: number
  tier: DispositionTier
  tier_label: string
  tier_guidance: string
  factors: RiskFactor[]
  config_version: string
}

export type ReportStatus = 'draft' | 'issued' | 'rejected'

export interface ReviewerDirective {
  instructions: string
  target_agents: FindingAgent[]
}

export interface ReviewerDecision {
  action: 'approve' | 'reject' | 'rerun'
  reviewer: string
  comment: string | null
  directive: ReviewerDirective | null
  decided_at: string
}

export interface DispatchPlan {
  run_mandate: boolean
  run_kya: boolean
  run_log: boolean
  run_drift: boolean
  reasoning: string
}

export type RunKind = 'triage' | 'investigation' | 'drafting'

// prompt_id -> the assembled text recorded on run_started
export interface RecordedPrompt {
  effective: string
  override: string | null
  default_version: string
}

export interface RunRecord {
  run_id: string
  kind: RunKind
  prompts: Record<string, RecordedPrompt>
  plan: DispatchPlan | null
  dispatches: DispatchRecord[]
  findings: Finding[]
  observations: Observation[]
  correlations: Correlation[]
  risk_score: RiskScore | null
  started_at: string
  completed_at: string | null
}

// ledger/projection.py::CaseRecord — the durable truth about one case.
export interface CaseRecord {
  case_id: string
  status: CaseStatus
  firm: string
  runs: RunRecord[]
  findings: Finding[]
  observations: Observation[]
  correlations: Correlation[]
  answers: InvestigationAnswer[]
  risk_score: RiskScore | null
  draft_report: DraftReport | null
  report_blocked: boolean
  grounding_problems: string[]
  decisions: ReviewerDecision[]
  open_questions: { question_id: string; question: string }[]
  opened_by: string | null
  submitted_summary: string | null
  escalation_rounds: number
  first_event_at: string
  last_event_at: string
  event_count: number
}

export interface CaseDetail extends CaseSummary {
  record: CaseRecord
  raw: RawCaseBundle
}

export interface LedgerEvent {
  seq: number
  case_id: string
  run_id: string | null
  event_type: string
  payload: Record<string, unknown>
  actor: string
  recorded_at: string
  prev_hash: string
  hash: string
}

export interface PromptSpec {
  prompt_id: string
  version: string
  preamble: string
  body: string
  contract: string
  notes: string | null
  used_by: RunKind[]
}

/** The human gate's interrupt payload (pipeline/graph.py::_human_gate_node). */
export interface GateContext {
  reason: string
  message: string
  case_id: string
  rerun_allowed: boolean
  reviewer_rounds: number
  max_reviewer_rounds: number
  error?: string
}

// The slice of schemas/case.py's CaseBundle the case-file dossier renders.
export interface RawCaseBundle {
  case_id: string
  firm: { firm_id: string; name: string; sector: string; hq: string }
  kya_credential: {
    credential_id: string
    agent_id: string
    agent_name: string
    operator_firm: string
    issuer: { issuer_id: string; issuer_name: string }
    issued_at: string
    expires_at: string
    capabilities: string[]
    delegation_chain: { level: number; holder_id: string; holder_type: string; name: string }[]
  }
  mandate_chain: {
    intent: {
      intent_mandate_id: string
      issued_at: string
      expires_at: string
      principal: { name: string; role: string; principal_id: string; org: string }
      agent: { agent_name: string; model_version?: string }
      natural_language_intent: string
      authorization_scope: {
        purpose_category: string
        max_transaction_amount: number
        max_cumulative_amount?: number | null
        currency: string
        valid_from: string
        valid_until: string
        allowed_merchant_categories?: string[]
        allowed_counterparties?: { counterparty_id: string; name: string }[]
        geographic_scope?: string | null
        human_presence_required?: boolean
      }
      consent: { method: string; timestamp: string }
    }
    cart: {
      cart_mandate_id: string
      merchant: { merchant_id: string; name: string; mcc: string; country: string }
      line_items: { sku: string; description: string; qty: number; unit_price: number }[]
      cart_total: number
      currency: string
    }
    payment: {
      payment_mandate_id: string
      authorized_at: string
      amount: number
      currency: string
      payment_method: { type: string; instrument_id_masked: string; issuer: string }
      settlement_status: string
    }
  }
  transaction_history: {
    transaction_id: string
    timestamp: string
    counterparty_name: string
    counterparty_id: string
    mcc: string
    amount: number
    currency: string
    status: string
    channel: string
  }[]
}

export interface GraphNode {
  id: string
  label: string
}

export interface GraphEdge {
  source: string
  target: string
  conditional: boolean
}

export interface GraphStructure {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export const SPECIALIST_NODES = ['mandate', 'kya', 'log', 'drift'] as const

export const AGENT_LABELS: Record<ObservationAgent, string> = {
  mandate: 'Mandate',
  kya: 'KYA',
  log: 'Log',
  drift: 'Drift',
  investigator: 'Investigator',
}
