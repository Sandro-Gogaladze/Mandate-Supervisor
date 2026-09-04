import type {
  CaseDetail,
  FullMap,
  CaseRecord,
  CaseSummary,
  GraphStructure,
  LedgerEvent,
  PromptSpec,
} from './types'

const API_BASE = import.meta.env.VITE_SUPERVISOR_API_URL ?? 'http://127.0.0.1:8123'

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) {
    const error = await res.json().catch(() => null)
    throw new Error(typeof error?.detail === 'string' ? error.detail : `${path} → ${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const error = await res.json().catch(() => null)
    throw new Error(typeof error?.detail === 'string' ? error.detail : `${path} → ${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export function listCases(): Promise<CaseSummary[]> {
  return getJSON('/cases')
}

export function getCase(caseId: string): Promise<CaseDetail> {
  return getJSON(`/cases/${caseId}`)
}

export function getGraphStructure(): Promise<GraphStructure> {
  return getJSON('/graph')
}

export function getFullMap(): Promise<FullMap> {
  return getJSON('/graph/full')
}

/** The case's events as the console reads them: a reset hides the review
 * that preceded it. Pass `includeCleared` for the whole audit trail — the
 * timeline does, because nothing is ever actually deleted. */
export function getLedgerEvents(caseId: string, includeCleared = false): Promise<LedgerEvent[]> {
  return getJSON(`/ledger/${caseId}${includeCleared ? '?include_cleared=true' : ''}`)
}

export function verifyLedger(): Promise<{ intact: boolean; event_count: number; problems: string[] }> {
  return getJSON('/ledger/verify')
}

export function getPrompts(): Promise<Record<string, PromptSpec>> {
  return getJSON('/prompts')
}

export function closeCase(caseId: string, officer: string, reason?: string): Promise<CaseRecord> {
  return postJSON(`/cases/${caseId}/close`, { officer, reason: reason ?? null })
}

export class CaseUploadError extends Error {}

export async function uploadCase(file: File, token: string): Promise<CaseSummary> {
  const body = new FormData()
  body.append('file', file)
  const res = await fetch(`${API_BASE}/dossiers`, { method: 'POST', body, headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) {
    const payload = await res.json().catch(() => null)
    throw new CaseUploadError(payload?.detail ?? `Upload failed (${res.status})`)
  }
  const result = await res.json() as { dossier_id: string }
  return getCase(result.dossier_id)
}

import type { DossierDetail, ExecutionDetail, ExecutionSummary, SignedDecision, PortfolioSweep } from './supervision-types'
const dossierPath = (id: string) => `/dossiers/${encodeURIComponent(id)}`
export const getDossier = (id: string) => getJSON<DossierDetail>(dossierPath(id))
export const getExecutions = (id: string) => getJSON<ExecutionSummary[]>(`${dossierPath(id)}/runs`)
export const getExecution = (id: string, run: string) => getJSON<ExecutionDetail>(`${dossierPath(id)}/runs/${encodeURIComponent(run)}`)
export const signAuthorisation = (id: string, decision: SignedDecision) => postJSON<SignedDecision>(`${dossierPath(id)}/decision`, decision)
/** Set the review history aside so the next run starts from the submission
 * alone. Appends a marker; the ledger keeps every earlier event. */
export const resetReviewHistory = (id: string) => postJSON<DossierDetail>(`${dossierPath(id)}/reset`, {})
export const dossierExportURL = (id: string) => `${API_BASE}${dossierPath(id)}/export`
export const getPortfolio = () => getJSON<PortfolioSweep>('/portfolio')
export const sweepPortfolio = () => postJSON<PortfolioSweep>('/portfolio/sweep', {})
