import type { CaseDetail, CaseSummary, GraphStructure } from './types'

const API_BASE = import.meta.env.VITE_SUPERVISOR_API_URL ?? 'http://127.0.0.1:8123'

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) {
    throw new Error(`${path} -> ${res.status} ${res.statusText}`)
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

export class CaseUploadError extends Error {}

export async function uploadCase(file: File): Promise<CaseSummary> {
  const body = new FormData()
  body.append('file', file)
  const res = await fetch(`${API_BASE}/cases/upload`, { method: 'POST', body })
  if (!res.ok) {
    const payload = await res.json().catch(() => null)
    throw new CaseUploadError(payload?.detail ?? `Upload failed (${res.status})`)
  }
  return res.json() as Promise<CaseSummary>
}
