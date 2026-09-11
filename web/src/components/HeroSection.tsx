import type { Stats } from '../types'
import { Icon } from './ui'

interface Props {
  stats: Stats | null
}

export function HeroSection({ stats }: Props) {
  return (
    <div className="flex flex-col items-center px-4 py-12 text-center animate-fade-in lg:py-16">
      <div className="mb-6 flex size-16 items-center justify-center rounded-2xl bg-orange/10 ring-1 ring-orange/20">
        <Icon name="droplet" size={32} className="text-orange" />
      </div>

      <h2 className="max-w-xl text-[28px] font-bold leading-tight text-text-strong lg:text-[34px]">
        An agent that coordinates blood donors
      </h2>

      <p className="mt-4 max-w-lg text-[15px] leading-relaxed text-muted">
        DonorPanel holds the donor network for patients who need matched blood repeatedly for life.
        It decides what is routine, handles outreach on its own, and only wakes a human when something genuinely needs judgement.
      </p>

      {stats && (
        <div className="mt-8 grid w-full max-w-md grid-cols-3 gap-3">
          <StatCard label="Donors in pool" value={stats.donors} icon="users" />
          <StatCard label="Requests" value={stats.requests} icon="inbox" />
          <StatCard
            label="Awaiting review"
            value={stats.awaiting_approval}
            icon="alert-triangle"
            highlight={stats.awaiting_approval > 0}
          />
        </div>
      )}

      <div className="mt-10 w-full max-w-lg">
        <p className="mb-5 text-[11px] font-medium uppercase tracking-widest text-faint">How it works</p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <StepCard step={1} title="Request" desc="Select a patient and submit a transfusion request" icon="play" />
          <StepCard step={2} title="Agent processes" desc="Nine pipeline nodes verify, match donors, and draft outreach" icon="activity" />
          <StepCard step={3} title="Autonomy decision" desc="Routine? Sent automatically. Unusual? Escalated for review" icon="shield-check" />
        </div>
      </div>

      <div className="mt-8 flex items-center gap-2 text-[13px] text-primary">
        <Icon name="arrow-right" size={16} />
        <span>Start a request in the sidebar to see the agent work</span>
      </div>
    </div>
  )
}

function StatCard({ label, value, icon, highlight }: {
  label: string; value: number; icon: 'users' | 'inbox' | 'alert-triangle'; highlight?: boolean
}) {
  return (
    <div className="rounded-xl border border-border bg-raised p-4 text-center">
      <Icon name={icon} size={18} className={highlight ? 'mx-auto text-warning' : 'mx-auto text-muted'} />
      <p className={`mt-2 text-[22px] font-bold tabular-nums ${highlight ? 'text-warning' : 'text-text-strong'}`}>
        {value}
      </p>
      <p className="mt-0.5 text-[11px] text-muted">{label}</p>
    </div>
  )
}

function StepCard({ step, title, desc, icon }: {
  step: number; title: string; desc: string; icon: 'play' | 'activity' | 'shield-check'
}) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-border-dim bg-surface p-4 text-center">
      <div className="mb-2 flex size-8 items-center justify-center rounded-lg bg-primary/10 text-[12px] font-bold text-primary">
        {step}
      </div>
      <div className="mb-1 flex items-center gap-1.5">
        <Icon name={icon} size={14} className="text-primary" />
        <p className="text-[13px] font-semibold text-text">{title}</p>
      </div>
      <p className="text-[12px] leading-snug text-muted">{desc}</p>
    </div>
  )
}
