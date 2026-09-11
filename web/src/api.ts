import { headers } from './session'
import type { Actor, Donor, MemoryRecord, GraphEdgeSpec, GraphNodeSpec, Patient, RequestDetail } from './types'

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: headers() })
  if (!response.ok) throw new Error(`${path} returned ${response.status}`)
  return response.json() as Promise<T>
}

export const api = {
  health: () => get<{ ok: boolean; region: string; model: string; storage: string }>('/api/health'),
  graph: () => get<{ nodes: GraphNodeSpec[]; edges: GraphEdgeSpec[] }>('/api/graph'),
  patients: () => get<Patient[]>('/api/patients'),
  donors: () => get<Donor[]>('/api/donors'),
  requests: () => get<RequestDetail[]>('/api/requests'),
  detail: (id: string) => get<RequestDetail>(`/api/requests/${id}`),
  stats: () => get<{ requests: number; awaiting_approval: number; donors: number }>('/api/stats'),
  me: () => get<Actor>('/api/me'),
  memory: () => get<MemoryRecord[]>('/api/memory'),

  resetSandbox: async () => {
    const response = await fetch('/api/sandbox/reset', { method: 'POST', headers: headers() })
    if (!response.ok) throw new Error(await response.text())
    return (await response.json()) as { cleared: number }
  },

  approve: async (id: string, by: string, note?: string) => {
    const response = await fetch(`/api/requests/${id}/approve`, {
      method: 'POST',
      headers: headers({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ by, note: note ?? null }),
    })
    if (!response.ok) throw new Error(await response.text())
    return (await response.json()) as RequestDetail
  },
}

export interface StreamHandlers {
  onStarted?: (data: { request_id: string }) => void
  onNodeStart?: (nodeId: string) => void
  onNodeStop?: (data: { node_id: string; ms: number; output: string }) => void
  onHandoff?: (data: { from: string[]; to: string[] }) => void
  onDone?: (data: Record<string, any>) => void
  onFailed?: (message: string) => void
}

/**
 * EventSource cannot POST, so the run is streamed over fetch and the SSE frames
 * are parsed by hand. Frames are separated by a blank line and may split across
 * chunk boundaries, so the tail is carried over between reads.
 */
export async function runRequest(
  body: { patient_id: string; needed_by: string; units_needed?: number },
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch('/api/requests/stream', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok || !response.body) throw new Error(`stream failed: ${response.status}`)

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''

    for (const frame of frames) {
      let event = 'message'
      let payload = ''
      for (const line of frame.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7).trim()
        else if (line.startsWith('data: ')) payload += line.slice(6)
      }
      if (!payload) continue
      const data = JSON.parse(payload)
      if (event === 'started') handlers.onStarted?.(data)
      else if (event === 'node_start') handlers.onNodeStart?.(data.node_id)
      else if (event === 'node_stop') handlers.onNodeStop?.(data)
      else if (event === 'handoff') handlers.onHandoff?.(data)
      else if (event === 'done') handlers.onDone?.(data)
      else if (event === 'failed') handlers.onFailed?.(data.error)
    }
  }
}
