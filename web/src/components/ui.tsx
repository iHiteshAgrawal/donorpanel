import clsx from 'clsx'
import type { ReactNode } from 'react'

/* ── Panel ─────────────────────────────────────────────────── */

export function Panel({ title, action, children, className }: {
  title?: string; action?: ReactNode; children: ReactNode; className?: string
}) {
  return (
    <section className={clsx('flex min-h-0 flex-col rounded-xl border border-border bg-surface', className)}>
      {title && (
        <header className="flex shrink-0 items-center justify-between gap-2 border-b border-border px-5 py-3">
          <h2 className="text-[15px] font-semibold text-text">{title}</h2>
          {action}
        </header>
      )}
      <div className="min-h-0 flex-1 overflow-auto">{children}</div>
    </section>
  )
}

/* ── Status badge ──────────────────────────────────────────── */

const statusTone: Record<string, string> = {
  verified: 'bg-logic-dim text-logic',
  matching: 'bg-logic-dim text-logic',
  awaiting_approval: 'bg-warning-dim text-warning',
  dispatched: 'bg-agent-dim text-agent',
  fulfilled: 'bg-success-dim text-success',
  rejected: 'bg-error-dim text-error',
  draft: 'bg-raised text-muted',
  pending: 'bg-raised text-muted',
}

export function Status({ value }: { value: string }) {
  return (
    <span className={clsx(
      'rounded-md px-2.5 py-1 text-[12px] font-medium',
      statusTone[value] ?? 'bg-raised text-muted',
    )}>
      {value.replace(/_/g, ' ')}
    </span>
  )
}

/* ── Button ────────────────────────────────────────────────── */

export function Button({ children, variant = 'ghost', className, ...rest }: {
  variant?: 'primary' | 'ghost' | 'approve' | 'danger'
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...rest}
      className={clsx(
        'inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-[13px] font-medium transition-all duration-150',
        'disabled:cursor-not-allowed disabled:opacity-40',
        variant === 'primary' && 'bg-orange text-squid hover:bg-orange-hover shadow-sm',
        variant === 'approve' && 'bg-success text-white hover:bg-success/85 shadow-sm',
        variant === 'ghost' && 'border border-border text-text hover:border-faint hover:bg-raised',
        variant === 'danger' && 'border border-error/30 text-error hover:bg-error-dim',
        className,
      )}
    >
      {children}
    </button>
  )
}

/* ── Field ─────────────────────────────────────────────────── */

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-muted">{label}</span>
      {children}
    </label>
  )
}

/* ── Input styling ─────────────────────────────────────────── */

export const inputClass =
  'w-full rounded-lg border border-border bg-page-bg px-3 py-2.5 text-sm text-text ' +
  'outline-none transition-colors focus:border-primary focus:ring-1 focus:ring-primary/30'

/* ── Empty state ───────────────────────────────────────────── */

export function Empty({ children }: { children: ReactNode }) {
  return <p className="px-5 py-8 text-center text-sm text-muted">{children}</p>
}

/* ── Card (new) ────────────────────────────────────────────── */

export function Card({ children, className, accent }: {
  children: ReactNode; className?: string; accent?: 'success' | 'warning' | 'error' | 'agent'
}) {
  const accentBorder: Record<string, string> = {
    success: 'border-success/40',
    warning: 'border-warning/40',
    error: 'border-error/40',
    agent: 'border-agent/40',
  }
  return (
    <div className={clsx(
      'rounded-xl border bg-surface p-5',
      accent ? accentBorder[accent] : 'border-border',
      className,
    )}>
      {children}
    </div>
  )
}

/* ── Badge (new) ───────────────────────────────────────────── */

export function Badge({ children, tone = 'default' }: {
  children: ReactNode; tone?: 'agent' | 'logic' | 'gate' | 'success' | 'warning' | 'default'
}) {
  const styles: Record<string, string> = {
    agent: 'bg-agent-dim text-agent',
    logic: 'bg-logic-dim text-logic',
    gate: 'bg-error-dim text-error',
    success: 'bg-success-dim text-success',
    warning: 'bg-warning-dim text-warning',
    default: 'bg-raised text-muted',
  }
  return (
    <span className={clsx('inline-flex rounded-md px-2.5 py-1 text-[12px] font-medium', styles[tone])}>
      {children}
    </span>
  )
}

/* ── Inline SVG icons ──────────────────────────────────────── */

type IconName =
  | 'shield-check' | 'alert-triangle' | 'brain' | 'refresh'
  | 'user' | 'chevron-right' | 'play' | 'check' | 'x'
  | 'clock' | 'zap' | 'activity' | 'droplet' | 'users'
  | 'menu' | 'arrow-right' | 'loader' | 'inbox' | 'sparkles'

const paths: Record<IconName, string> = {
  'shield-check': 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z M9 12l2 2 4-4',
  'alert-triangle': 'M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z M12 9v4 M12 17h.01',
  brain: 'M12 2a4 4 0 014 4v1a3 3 0 012 5.22V14a4 4 0 01-3 3.87V20a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2.13A4 4 0 016 14v-1.78A3 3 0 018 7V6a4 4 0 014-4z',
  refresh: 'M23 4v6h-6 M1 20v-6h6 M3.51 9a9 9 0 0114.85-3.36L23 10 M1 14l4.64 4.36A9 9 0 0020.49 15',
  user: 'M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2 M12 3a4 4 0 100 8 4 4 0 000-8z',
  'chevron-right': 'M9 18l6-6-6-6',
  play: 'M5 3l14 9-14 9V3z',
  check: 'M20 6L9 17l-5-5',
  x: 'M18 6L6 18 M6 6l12 12',
  clock: 'M12 2a10 10 0 100 20 10 10 0 000-20z M12 6v6l4 2',
  zap: 'M13 2L3 14h9l-1 8 10-12h-9l1-8z',
  activity: 'M22 12h-4l-3 9L9 3l-3 9H2',
  droplet: 'M12 2.69l5.66 5.66a8 8 0 11-11.31 0z',
  users: 'M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2 M9 3a4 4 0 100 8 4 4 0 000-8z M23 21v-2a4 4 0 00-3-3.87 M16 3.13a4 4 0 010 7.75',
  menu: 'M3 12h18 M3 6h18 M3 18h18',
  'arrow-right': 'M5 12h14 M12 5l7 7-7 7',
  loader: 'M21 12a9 9 0 11-6.219-8.56',
  inbox: 'M22 12h-6l-2 3H10l-2-3H2 M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z',
  sparkles: 'M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z M19 13l.75 2.25L22 16l-2.25.75L19 19l-.75-2.25L16 16l2.25-.75L19 13z',
}

export function Icon({ name, size = 16, className }: {
  name: IconName; size?: number; className?: string
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={clsx('shrink-0', className)}
    >
      {paths[name].split(' M').map((segment, i) => (
        <path key={i} d={i === 0 ? segment : `M${segment}`} />
      ))}
    </svg>
  )
}
