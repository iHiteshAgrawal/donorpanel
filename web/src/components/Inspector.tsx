import { useState } from 'react'
import type { Donor, GraphNodeSpec, NodeRun, RequestDetail } from '../types'
import { Button, Empty, Field, inputClass, Status } from './ui'

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

export function NodeOutput({ node, run }: { node: GraphNodeSpec | null; run?: NodeRun }) {
  if (!node) return <Empty>Select a node to inspect what it produced.</Empty>
  if (!run || run.status === 'pending') {
    return <Empty>{node.label} has not run yet.</Empty>
  }
  return (
    <pre className="whitespace-pre-wrap break-words px-3.5 py-3 font-mono text-[11px] leading-relaxed text-ink-300">
      {pretty(run.output) || 'running…'}
    </pre>
  )
}

export function Cohort({ detail, donors }: { detail: RequestDetail | null; donors: Donor[] }) {
  if (!detail || detail.contacts.length === 0) {
    return <Empty>No cohort selected yet.</Empty>
  }
  const byId = new Map(donors.map((d) => [d.donor_id, d]))
  return (
    <table className="w-full text-[12px]">
      <thead>
        <tr className="border-b border-ink-800 text-left font-mono text-[10px] uppercase tracking-widest text-ink-400">
          <th className="px-3.5 py-2 font-normal">#</th>
          <th className="py-2 font-normal">Donor</th>
          <th className="py-2 font-normal">Group</th>
          <th className="py-2 font-normal">City</th>
          <th className="py-2 pr-3.5 font-normal">Via</th>
        </tr>
      </thead>
      <tbody>
        {detail.contacts.map((contact) => {
          const donor = byId.get(contact.donor_id)
          return (
            <tr key={contact.donor_id} className="border-b border-ink-850/70 last:border-0">
              <td className="px-3.5 py-2 font-mono text-ink-400">{contact.rank}</td>
              <td className="py-2 text-ink-200">{donor?.name ?? contact.donor_id}</td>
              <td className="py-2 font-mono text-logic">{donor?.blood_group ?? '—'}</td>
              <td className="py-2 text-ink-400">{donor?.city ?? '—'}</td>
              <td className="py-2 pr-3.5 font-mono text-[11px] text-ink-400">{contact.channel}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

export function Approval({ detail, onApprove, busy }: {
  detail: RequestDetail | null
  onApprove: (by: string) => void
  busy: boolean
}) {
  const [who, setWho] = useState('')

  if (!detail) return <Empty>Run a request to see its drafts.</Empty>
  if (detail.drafts.length === 0) return <Empty>Nothing drafted for this request.</Empty>

  const approved = Boolean(detail.approval)

  return (
    <div className="space-y-3 px-3.5 py-3">
      {detail.drafts.map((draft, index) => (
        <article key={index} className="rounded-lg border border-ink-800 bg-ink-950/60 p-3">
          <div className="mb-2 flex items-center gap-1.5">
            <span className="rounded bg-ink-800 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide text-ink-300">
              {draft.language}
            </span>
            <span className="rounded bg-agent/15 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide text-agent">
              {draft.channel}
            </span>
          </div>
          {draft.subject && (
            <p className="mb-1.5 text-[12px] font-medium text-ink-200">{draft.subject}</p>
          )}
          <p className="whitespace-pre-wrap text-[12px] leading-relaxed text-ink-300">{draft.body}</p>
        </article>
      ))}

      <div className="rounded-lg border border-gate/30 bg-gate/5 p-3">
        {approved ? (
          <p className="text-[12px] text-good">
            Approved by <span className="font-mono">{detail.approval!.by}</span>. Outreach may proceed.
          </p>
        ) : (
          <>
            <p className="mb-2.5 text-[12px] text-ink-300">
              Nothing has been sent. {detail.contacts.length} donors will be contacted only after a
              coordinator approves.
            </p>
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <Field label="Approving as">
                  <input
                    className={inputClass}
                    value={who}
                    placeholder="your name"
                    onChange={(event) => setWho(event.target.value)}
                  />
                </Field>
              </div>
              <Button variant="gate" disabled={!who.trim() || busy} onClick={() => onApprove(who.trim())}>
                {busy ? 'Approving…' : 'Approve cohort'}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export function RequestRow({ detail, active, onClick }: {
  detail: RequestDetail; active: boolean; onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center justify-between gap-2 border-b border-ink-850/70 px-3.5 py-2.5 text-left transition-colors last:border-0 hover:bg-ink-850/60 ${
        active ? 'bg-ink-850' : ''
      }`}
    >
      <div className="min-w-0">
        <p className="truncate font-mono text-[11px] text-ink-300">{detail.request_id}</p>
        <p className="text-[11px] text-ink-400">
          {detail.units_needed} units · by {detail.needed_by}
        </p>
      </div>
      <Status value={detail.status} />
    </button>
  )
}
