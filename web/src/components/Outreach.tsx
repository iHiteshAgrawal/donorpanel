import type { Donor, RequestDetail } from '../types'
import { Badge, Empty } from './ui'

function when(iso: string | null): string {
  if (!iso) return ''
  const at = new Date(iso)
  return Number.isNaN(at.getTime()) ? '' : at.toLocaleTimeString()
}

export function Outreach({ detail, donors }: { detail: RequestDetail | null; donors: Donor[] }) {
  const reached = detail?.contacts.filter((c) => c.contacted_at) ?? []
  if (!detail || reached.length === 0) {
    return <Empty>Nothing has been sent yet. The agent reaches out once a request clears the gate.</Empty>
  }
  const byId = new Map(donors.map((d) => [d.donor_id, d]))

  return (
    <div className="space-y-3 px-5 py-4">
      {reached.map((contact) => {
        const donor = byId.get(contact.donor_id)
        const sent = contact.status === 'sent'
        return (
          <article key={contact.donor_id} className="rounded-lg border border-border bg-raised p-4">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="font-mono text-[12px] text-muted">{contact.rank}</span>
              <span className="text-[15px] font-medium text-text">
                {donor?.name ?? contact.donor_id}
              </span>
              <Badge tone="agent">{contact.channel ?? 'unknown'}</Badge>
              <Badge tone={sent ? 'success' : 'gate'}>{sent ? 'sent' : 'not delivered'}</Badge>
              <span className="ml-auto font-mono text-[12px] text-muted">
                {when(contact.contacted_at)}
              </span>
            </div>
            {sent ? (
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted">{contact.body}</p>
            ) : (
              <p className="text-sm text-error">{contact.note ?? 'delivery failed'}</p>
            )}
          </article>
        )
      })}
    </div>
  )
}
