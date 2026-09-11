export type NodeKind = 'agent' | 'deterministic' | 'gate'

export interface GraphNodeSpec {
  id: string
  label: string
  kind: NodeKind
  phase: string
  detail: string
}

export interface GraphEdgeSpec {
  source: string
  target: string
  label?: string
}

export interface Patient {
  patient_id: string
  name: string
  blood_group: string
  condition: string
  city: string | null
  hospital: string | null
  policy_id: string
  lat: number | null
  lon: number | null
}

export interface Donor {
  donor_id: string
  name: string
  blood_group: string
  city: string | null
  lat: number | null
  lon: number | null
  channel: string
  language: string
  consent: boolean
  last_donation: string | null
  contacts_this_month: number
}

export interface Draft {
  language: string
  channel: string
  subject: string | null
  body: string
}

export interface Contact {
  rank: number
  donor_id: string
  channel: string | null
  status: string
  contacted_at: string | null
  note: string | null
  body: string | null
}

export interface RequestDetail {
  request_id: string
  patient_id: string
  status: string
  units_needed: number
  needed_by: string
  source: string
  component: string
  rejection_reason: string | null
  created_at: string
  contacts: Contact[]
  drafts: Draft[]
  approval: { by: string; at: string; note: string | null } | null
}

export type RunState = 'idle' | 'running' | 'done' | 'failed'

export interface NodeRun {
  status: 'pending' | 'running' | 'done'
  ms?: number
  output?: string
}

export interface Actor {
  actor_id: string
  name: string
  email: string | null
  authenticated: boolean
  namespace: string
}

export interface MemoryRecord {
  text: string
  kind: 'preference' | 'finding'
  namespace: string
  score: number | null
}

export interface Stats {
  requests: number
  by_status?: Record<string, number>
  awaiting_approval: number
  donors: number
}

export interface Verdict {
  gate: 'auto' | 'escalated' | 'approved'
  checks_passed?: string[]
  reasons?: string[]
}
