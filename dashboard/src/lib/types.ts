// Mirrors schemas/*.py — kept hand-in-sync (no codegen yet) since the
// Python side is the source of truth and changes rarely at this phase.

export type ScenarioLabel =
  | 'compliant'
  | 'mandate_breaching'
  | 'broken_chain'
  | 'synthetic_identity'
  | 'structuring'
  | 'drift'
  | 'prompt_injection'

export interface CaseSummary {
  case_id: string
  firm: string
  // Eval-only ground truth (schemas/case.py) — a demo corpus case has one,
  // a real submitted case doesn't (that's the whole point of running a
  // review: nobody already knows the answer).
  label: ScenarioLabel | null
  summary: string
  case_path: string
}

export interface CaseDetail extends CaseSummary {
  raw: RawCaseBundle
}

// The slice of schemas/case.py's CaseBundle the case-file dossier renders.
// Same hand-in-sync discipline as the rest of this file; optional markers
// mirror the Pydantic schema's own optionality, nothing more defensive.
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

export type FindingAgent = 'mandate' | 'kya' | 'log' | 'drift'

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
  agent: FindingAgent
  note: string
  cited_evidence: string
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

export type DispositionTier = 'clear' | 'review' | 'escalate'

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

export interface DispatchPlan {
  run_mandate: boolean
  run_kya: boolean
  run_log: boolean
  run_drift: boolean
  reasoning: string
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

export const AGENT_LABELS: Record<FindingAgent, string> = {
  mandate: 'Mandate',
  kya: 'KYA',
  log: 'Log',
  drift: 'Drift',
}
