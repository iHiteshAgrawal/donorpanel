import { useState } from 'react'
import type { RequestDetail, Verdict } from '../types'
import { Button, Card, Field, Icon, inputClass } from './ui'

interface Props {
  verdict: Verdict | null
  detail: RequestDetail | null
  onApprove: (by: string) => void
  busy: boolean
}

export function OutcomeCard({ verdict, detail, onApprove, busy }: Props) {
  const [who, setWho] = useState('')

  if (!verdict || !detail) return null

  if (verdict.gate === 'auto') {
    return (
      <Card accent="success" className="animate-fade-in">
        <div className="flex items-start gap-4">
          <div className="flex size-14 shrink-0 items-center justify-center rounded-xl bg-success-dim">
            <Icon name="shield-check" size={28} className="text-success" />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="text-[22px] font-semibold text-success">Sent automatically</h3>
            <p className="mt-1.5 text-sm leading-relaxed text-muted">
              The agent determined this is a routine request and dispatched outreach without human intervention.
            </p>
          </div>
        </div>

        {verdict.checks_passed && verdict.checks_passed.length > 0 && (
          <div className="mt-4 space-y-2 rounded-lg border border-success/20 bg-success-dim p-4">
            <p className="text-[12px] font-medium uppercase tracking-wider text-success">Checks passed</p>
            <ul className="space-y-2">
              {verdict.checks_passed.map((check, i) => (
                <li key={i} className="flex items-start gap-2.5 text-sm text-text">
                  <Icon name="check" size={14} className="mt-0.5 text-success" />
                  <span>{check}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-4 flex items-center gap-2.5 text-sm text-muted">
          <Icon name="zap" size={16} className="text-orange" />
          <span>{detail.contacts.length} donor{detail.contacts.length !== 1 ? 's' : ''} contacted</span>
          <span className="text-faint">·</span>
          <span>{detail.units_needed} unit{detail.units_needed !== 1 ? 's' : ''} needed by {detail.needed_by}</span>
        </div>
      </Card>
    )
  }

  if (verdict.gate === 'escalated') {
    const approved = Boolean(detail.approval)
    return (
      <Card accent="warning" className="animate-fade-in">
        <div className="flex items-start gap-4">
          <div className="flex size-14 shrink-0 items-center justify-center rounded-xl bg-warning-dim">
            <Icon name="alert-triangle" size={28} className="text-warning" />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="text-[22px] font-semibold text-warning">Needs coordinator review</h3>
            <p className="mt-1.5 text-sm leading-relaxed text-muted">
              The agent flagged this request for human approval before contacting donors.
            </p>
          </div>
        </div>

        {verdict.reasons && verdict.reasons.length > 0 && (
          <div className="mt-4 space-y-2 rounded-lg border border-warning/20 bg-warning-dim p-4">
            <p className="text-[12px] font-medium uppercase tracking-wider text-warning">Escalation reasons</p>
            <ul className="space-y-2">
              {verdict.reasons.map((reason, i) => (
                <li key={i} className="flex items-start gap-2 text-[13px] text-text">
                  <Icon name="alert-triangle" size={14} className="mt-0.5 text-warning" />
                  <span>{reason}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {approved ? (
          <div className="mt-4 rounded-lg border border-success/20 bg-success-dim p-4">
            <div className="flex items-center gap-2">
              <Icon name="check" size={16} className="text-success" />
              <p className="text-sm text-success">
                Approved by <span className="font-semibold">{detail.approval!.by}</span>. Outreach may proceed.
              </p>
            </div>
          </div>
        ) : (
          <div className="mt-4 rounded-lg border border-border bg-raised p-4">
            <p className="mb-3 text-sm text-muted">
              {detail.contacts.length} donor{detail.contacts.length !== 1 ? 's' : ''} will be contacted only after a coordinator approves.
            </p>
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <Field label="Your name">
                  <input
                    className={inputClass}
                    value={who}
                    placeholder="e.g. Dr. Sharma"
                    onChange={(e) => setWho(e.target.value)}
                  />
                </Field>
              </div>
              <Button
                variant="approve"
                disabled={!who.trim() || busy}
                onClick={() => onApprove(who.trim())}
              >
                {busy ? 'Approving...' : 'Approve'}
              </Button>
            </div>
          </div>
        )}
      </Card>
    )
  }

  // gate === 'approved'
  return (
    <Card accent="success" className="animate-fade-in">
      <div className="flex items-start gap-4">
        <div className="flex size-14 shrink-0 items-center justify-center rounded-xl bg-success-dim">
          <Icon name="shield-check" size={28} className="text-success" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-[22px] font-semibold text-success">Approved</h3>
          <p className="mt-1.5 text-sm leading-relaxed text-muted">
            {detail.approval
              ? <>Approved by <span className="font-semibold text-text">{detail.approval.by}</span>. Outreach dispatched.</>
              : 'This request has been approved. Outreach dispatched.'}
          </p>
        </div>
      </div>
      <div className="mt-4 flex items-center gap-2 text-[12px] text-muted">
        <Icon name="zap" size={14} className="text-orange" />
        <span>{detail.contacts.length} donor{detail.contacts.length !== 1 ? 's' : ''} contacted</span>
      </div>
    </Card>
  )
}
