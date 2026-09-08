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

async function sendJSON<T>(path: string, method: 'PATCH' | 'DELETE', body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  })
  if (!res.ok) {
    const error = await res.json().catch(() => null)
    throw new Error(typeof error?.detail === 'string' ? error.detail : `${path} → ${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}
const patchJSON = <T,>(path: string, body: unknown) => sendJSON<T>(path, 'PATCH', body)
const deleteJSON = <T,>(path: string) => sendJSON<T>(path, 'DELETE')

// Three components want the case list — the sidebar's count, the Overview's
// recent rows, and the queue itself — and in development StrictMode invokes
// every effect twice, so one page view asked for the same list four times.
// Callers within this window share one request; anything later gets a fresh
// one, so an upload or a finished review still shows up immediately.
let casesInFlight: { at: number; promise: Promise<CaseSummary[]> } | null = null
const CASES_TTL_MS = 1500

export function listCases(options?: { fresh?: boolean }): Promise<CaseSummary[]> {
  const now = Date.now()
  if (!options?.fresh && casesInFlight && now - casesInFlight.at < CASES_TTL_MS) {
    return casesInFlight.promise
  }
  const promise = getJSON<CaseSummary[]>('/cases').catch((err) => {
    casesInFlight = null   // never cache a failure
    throw err
  })
  casesInFlight = { at: now, promise }
  return promise
}

/** After an upload or a review, the list has genuinely changed. */
export const refreshCases = () => listCases({ fresh: true })

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
  // No header at all when the officer left the field empty: an empty bearer
  // reads as a wrong token, and this deployment may simply not use them.
  const res = await fetch(`${API_BASE}/dossiers`, {
    method: 'POST',
    body,
    headers: token.trim() ? { Authorization: `Bearer ${token.trim()}` } : undefined,
  })
  if (!res.ok) {
    const payload = await res.json().catch(() => null)
    throw new CaseUploadError(payload?.detail ?? `Upload failed (${res.status})`)
  }
  const result = await res.json() as { dossier_id: string }
  return getCase(result.dossier_id)
}

import type { DossierDetail, ExecutionDetail, ExecutionSummary, SignedDecision } from './supervision-types'
const dossierPath = (id: string) => `/dossiers/${encodeURIComponent(id)}`
export const getDossier = (id: string) => getJSON<DossierDetail>(dossierPath(id))
export const getExecutions = (id: string) => getJSON<ExecutionSummary[]>(`${dossierPath(id)}/runs`)
export const getExecution = (id: string, run: string) => getJSON<ExecutionDetail>(`${dossierPath(id)}/runs/${encodeURIComponent(run)}`)
export const signAuthorisation = (id: string, decision: SignedDecision) => postJSON<SignedDecision>(`${dossierPath(id)}/decision`, decision)
/** Set the review history aside so the next run starts from the submission
 * alone. Appends a marker; the ledger keeps every earlier event. */
export const resetReviewHistory = (id: string) => postJSON<DossierDetail>(`${dossierPath(id)}/reset`, {})
export const dossierExportURL = (id: string) => `${API_BASE}${dossierPath(id)}/export`
// --- policy sandbox -------------------------------------------------------
import type {
  RulebookView, RulesetDraft, SandboxDomain, Sweep, SweepComparison, SweepMode, VersionGraph,
} from './sandbox-types'
export const getSandboxDomains = () => getJSON<SandboxDomain[]>('/sandbox/domains')

/** The failure catalogue with the rules that currently implement each entry —
 * what the agent reference pages list as "failures this specialist owns". */
export interface FailureEntry {
  failure_id: string
  name: string
  domain: string
  phase: string
  default_scope: string
  mapped_rules: { rule_id: string; ruleset_id: string; ruleset_version: string; rule_status: string; evaluation: string }[]
  non_rule_detector: string | null
}
export const getFailureCatalogue = () =>
  getJSON<{ version: string; as_of: string; failures: FailureEntry[] }>('/failures')
/** `mode` shows each version the scorecard it has in that mode. The two never
 *  compare with each other, so a live scorecard is of no use to someone about
 *  to sweep mechanically. */
export const getVersionGraph = (domain: string, mode?: SweepMode) =>
  getJSON<VersionGraph>(`/sandbox/graph/${domain}${mode ? `?mode=${mode}` : ''}`)
export const getRulebook = (ref: string) => getJSON<RulebookView>(`/sandbox/rulebook/${encodeURIComponent(ref)}`)
export const createDraft = (body: { domain: string; label: string; created_by: string }) =>
  postJSON<RulesetDraft>('/sandbox/drafts', body)
export const editDraftRule = (draftId: string, body: { rule_id: string; status?: string; severity_weight?: number; params?: Record<string, unknown> }) =>
  patchJSON<RulesetDraft>(`/sandbox/drafts/${encodeURIComponent(draftId)}`, body)
export const deleteDraft = (draftId: string) =>
  deleteJSON<{ deleted: string }>(`/sandbox/drafts/${encodeURIComponent(draftId)}`)
/** `force` measures again even though this exact rulebook already has a
 *  scorecard taken under today's conditions. Without it the API returns the
 *  stored one and says so — `reused` — instead of spending six minutes
 *  reproducing an answer. */
export const runSweep = (body: { ruleset_ref: string; live?: boolean; force?: boolean }) =>
  postJSON<Sweep & { reused: boolean }>('/sandbox/sweeps', body)
export const getSweep = (id: string) => getJSON<Sweep>(`/sandbox/sweeps/${id}`)
export const compareSweeps = (base: string, candidate: string) =>
  getJSON<SweepComparison>(`/sandbox/compare?base=${base}&candidate=${candidate}`)
export const promoteDraft = (body: { draft_id: string; sweep_id: string; promoted_by: string; rationale: string }) =>
  postJSON<{ domain: string; from_version: string; to_version: string }>('/sandbox/promote', body)

