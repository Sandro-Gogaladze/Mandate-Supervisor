// Who is acting. One value for the whole console, because it is recorded on
// everything the person does — every question, every signed decision — and a
// name that could be edited in two places is a name that can disagree with
// itself between a review and the signature on it.
import { useCallback, useSyncExternalStore } from 'react'

const KEY = 'mandate-supervisor:officer'
export const DEFAULT_OFFICER = 'Case officer'

const listeners = new Set<() => void>()
let value: string = read()

function read(): string {
  try {
    return localStorage.getItem(KEY) || DEFAULT_OFFICER
  } catch {
    return DEFAULT_OFFICER // private mode, or storage disabled
  }
}

function subscribe(fn: () => void) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export function setOfficer(next: string) {
  value = next
  try { localStorage.setItem(KEY, next) } catch { /* nothing to persist to */ }
  listeners.forEach((fn) => fn())
}

/** `[officer, setOfficer]`, shared across every component that asks. */
export function useOfficer(): [string, (next: string) => void] {
  const officer = useSyncExternalStore(subscribe, () => value, () => DEFAULT_OFFICER)
  return [officer, useCallback(setOfficer, [])]
}
