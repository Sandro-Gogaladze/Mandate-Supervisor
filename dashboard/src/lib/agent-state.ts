// Mirrors pipeline/state.py's SupervisionState — the shape streamed back by
// the LangGraph agents over AG-UI/CopilotKit. Cases are addressed by
// case_id; the bundle lives in the ledger, never in a client-supplied path.
import type {
  Correlation,
  DispatchPlan,
  DraftReport,
  Finding,
  FailureOccurrence,
  Observation,
  ReportStatus,
  ReviewerDecision,
  ReviewerDirective,
  RiskScore,
} from './types'

export interface SupervisionAgentState {
  case_id: string
  run_id?: string
  deterministic_only?: boolean
  // True on the "run the review" turn: the orchestrator briefs every review skill.
  first_pass?: boolean
  prompt_overrides?: Record<string, string>
  findings?: Finding[]
  failure_occurrences?: FailureOccurrence[]
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
    reasoning?: string
    intent: 'dispatch' | 'reply' | 'draft_report'
    message_to_officer: string
    dispatches: { skill: string; instruction: string; run_scope: string[]; context_blocks: string[] }[]
  }
  orchestrator_reply?: string
}

export const EMPTY_AGENT_STATE: SupervisionAgentState = {
  case_id: '',
  findings: [],
  failure_occurrences: [],
  observations: [],
}
