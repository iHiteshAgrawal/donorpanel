const KEY = 'donorpanel.session'

function makeId(): string {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `s-${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`
}

/**
 * A stable per-browser id so an unauthenticated visitor gets their own sandbox.
 * localStorage throws in some privacy modes, so a fresh id per page load is the
 * fallback: still isolated from other visitors, just not durable across reloads.
 */
function load(): string {
  try {
    const existing = localStorage.getItem(KEY)
    if (existing) return existing
    const created = makeId()
    localStorage.setItem(KEY, created)
    return created
  } catch {
    return makeId()
  }
}

export const sessionId = load()

export function headers(extra: HeadersInit = {}): HeadersInit {
  return { 'X-DonorPanel-Session': sessionId, ...extra }
}
