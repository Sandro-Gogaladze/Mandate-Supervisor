// Mirrors pipeline/state.py's SupervisionState — the shape streamed back by
// the LangGraph agent over AG-UI/CopilotKit. `messages` exists only because
// AG-UI requires it even for a state-driven (non-chat) UI; nothing here
// reads it.
import type { DispatchPlan, DraftReport, Finding, Observation, ReportStatus, ReviewerDecision, RiskScore } from './types'

export interface SupervisionAgentState {
  case_path: string
  case?: { case: Record<string, unknown> } | Record<string, unknown>
  ingestion_findings?: Finding[]
  findings?: Finding[]
  observations?: Observation[]
  dispatch_plan?: DispatchPlan
  escalation_round?: number
  draft_report?: DraftReport
  draft_attempts?: number
  grounding_problems?: string[]
  report_blocked?: boolean
  risk_score?: RiskScore
  reviewer_decisions?: ReviewerDecision[]
  reviewer_rounds?: number
  report_status?: ReportStatus
}

export const EMPTY_AGENT_STATE: SupervisionAgentState = {
  case_path: '',
  findings: [],
  observations: [],
}
