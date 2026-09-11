import type { Donor, GraphNodeSpec, NodeRun, RequestDetail } from '../types'
import { Badge, Empty, Status } from './ui'

/* ── pretty-print node output ──────────────────────────────── */

function pretty(raw?: string): string {
  if (!raw) return ''
  const start = raw.indexOf('{')
  const end = raw.lastIndexOf('}')
  if (start === -1 || end === -1) return raw
  try {
    return JSON.stringify(JSON.parse(raw.slice(start, end + 1)), null, 2)
  } catch {
    return raw
  }
}

/* ── Node output inspector ─────────────────────────────────── */

export function NodeOutput({ node, run }: { node: GraphNodeSpec | null; run?: NodeRun }) {
  if (!node) return <Empty>Select a node to inspect what it produced.</Empty>
  if (!run || run.status === 'pending') {
    return <Empty>{node.label} has not run yet.</Empty>
  }
  return (
    <pre className="whitespace-pre-wrap break-words px-5 py-4 font-mono text-[13px] leading-relaxed text-text">
      {pretty(run.output) || 'running...'}
    </pre>
  )
}

/* ── Cohort table ──────────────────────────────────────────── */

export function Cohort({ detail, donors }: { detail: RequestDetail | null; donors: Donor[] }) {
  if (!detail || detail.contacts.length === 0) {
    return <Empty>No cohort selected yet.</Empty>
  }
  const byId = new Map(donors.map((d) => [d.donor_id, d]))
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-border text-left text-[12px] font-medium text-muted">
          <th className="px-5 py-3 font-medium">#</th>
          <th className="py-3 font-medium">Donor</th>
          <th className="py-3 font-medium">Group</th>
          <th className="py-3 font-medium">City</th>
          <th className="py-3 pr-5 font-medium">Via</th>
        </tr>
      </thead>
      <tbody>
        {detail.contacts.map((contact) => {
          const donor = byId.get(contact.donor_id)
          return (
            <tr key={contact.donor_id} className="border-b border-border-dim last:border-0 hover:bg-raised/50 transition-colors">
              <td className="px-5 py-3 font-mono text-muted">{contact.rank}</td>
              <td className="py-3 text-text">{donor?.name ?? contact.donor_id}</td>
              <td className="py-3"><Badge tone="logic">{donor?.blood_group ?? '-'}</Badge></td>
              <td className="py-3 text-muted">{donor?.city ?? '-'}</td>
              <td className="py-3 pr-5 font-mono text-[13px] text-muted">{contact.channel}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

/* ── Drafts viewer ─────────────────────────────────────────── */

export function Drafts({ detail }: { detail: RequestDetail | null }) {
  if (!detail) return <Empty>Run a request to see its drafts.</Empty>
  if (detail.drafts.length === 0) return <Empty>Nothing drafted for this request.</Empty>

  return (
    <div className="space-y-3 px-5 py-4">
      {detail.drafts.map((draft, index) => (
        <article key={index} className="rounded-lg border border-border bg-raised p-4">
          <div className="mb-2 flex items-center gap-1.5">
            <Badge>{draft.language}</Badge>
            <Badge tone="agent">{draft.channel}</Badge>
          </div>
          {draft.subject && (
            <p className="mb-2 text-[15px] font-medium text-text">{draft.subject}</p>
          )}
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted">{draft.body}</p>
        </article>
      ))}
    </div>
  )
}

/* ── Request list row ──────────────────────────────────────── */

export function RequestRow({ detail, active, onClick }: {
  detail: RequestDetail; active: boolean; onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center justify-between gap-2 border-b border-border-dim px-5 py-3 text-left transition-colors last:border-0 hover:bg-raised ${
        active ? 'bg-raised border-l-2 border-l-primary' : ''
      }`}
    >
      <div className="min-w-0">
        <p className="truncate font-mono text-[13px] text-muted">{detail.request_id.slice(0, 12)}...</p>
        <p className="text-sm text-text">
          {detail.units_needed} units · by {detail.needed_by}
        </p>
      </div>
      <Status value={detail.status} />
    </button>
  )
}
