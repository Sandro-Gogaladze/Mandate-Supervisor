// Mirrors pipeline/state.py's SupervisionState — the shape streamed back by
// the LangGraph agents over AG-UI/CopilotKit. Cases are addressed by
// case_id; the bundle lives in the ledger, never in a client-supplied path.
import type {
  Correlation,
  DispatchPlan,
  DraftReport,
  Finding,
  Observation,
  ReportStatus,
  ReviewerDecision,
  ReviewerDirective,
  RiskScore,
} from './types'

export interface SupervisionAgentState {
  case_id: string
  run_id?: string
  prompt_overrides?: Record<string, string>
  findings?: Finding[]
  observations?: Observation[]
  correlations?: Correlation[]
  dispatch_plan?: DispatchPlan
  escalation_round?: number
  draft_report?: DraftReport
  draft_attempts?: number
  grounding_problems?: string[]
  report_blocked?: boolean
  risk_score?: RiskScore
  reviewer_decisions?: ReviewerDecision[]
  reviewer_directive?: ReviewerDirective | null
  reviewer_rounds?: number
  report_status?: ReportStatus
  // investigation-run keys
  officer_message?: string
  officer?: string
  question_id?: string
  orchestrator_decision?: {
    intent: 'dispatch' | 'reply' | 'run_triage' | 'draft_report'
    targets: string[]
    instruction: string
    context_blocks: string[]
    message_to_officer: string
  }
  orchestrator_reply?: string
}

export const EMPTY_AGENT_STATE: SupervisionAgentState = {
  case_id: '',
  findings: [],
  observations: [],
}
