import clsx from 'clsx'
import type { ReactNode } from 'react'

export function Panel({ title, action, children, className }: {
  title?: string; action?: ReactNode; children: ReactNode; className?: string
}) {
  return (
    <section className={clsx('flex min-h-0 flex-col rounded-xl border border-ink-800 bg-ink-900/70', className)}>
      {title && (
        <header className="flex shrink-0 items-center justify-between gap-2 border-b border-ink-800 px-3.5 py-2.5">
          <h2 className="font-mono text-[11px] uppercase tracking-widest text-ink-400">{title}</h2>
          {action}
        </header>
      )}
      <div className="min-h-0 flex-1 overflow-auto">{children}</div>
    </section>
  )
}

const statusTone: Record<string, string> = {
  verified: 'bg-logic/15 text-logic',
  matching: 'bg-logic/15 text-logic',
  awaiting_approval: 'bg-warn/15 text-warn',
  dispatched: 'bg-agent/15 text-agent',
  fulfilled: 'bg-good/15 text-good',
  rejected: 'bg-gate/15 text-gate',
  draft: 'bg-ink-800 text-ink-300',
  pending: 'bg-ink-800 text-ink-300',
}

export function Status({ value }: { value: string }) {
  return (
    <span className={clsx(
      'rounded px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide',
      statusTone[value] ?? 'bg-ink-800 text-ink-300',
    )}>
      {value.replace(/_/g, ' ')}
    </span>
  )
}

export function Button({ children, variant = 'ghost', className, ...rest }: {
  variant?: 'primary' | 'ghost' | 'gate'
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...rest}
      className={clsx(
        'rounded-lg px-3 py-1.5 font-medium text-[12px] transition-colors disabled:cursor-not-allowed disabled:opacity-40',
        variant === 'primary' && 'bg-agent text-ink-950 hover:bg-agent/85',
        variant === 'gate' && 'bg-good text-ink-950 hover:bg-good/85',
        variant === 'ghost' && 'border border-ink-700 text-ink-200 hover:border-ink-600 hover:bg-ink-850',
        className,
      )}
    >
      {children}
    </button>
  )
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-ink-400">{label}</span>
      {children}
    </label>
  )
}

export const inputClass =
  'w-full rounded-lg border border-ink-700 bg-ink-950 px-2.5 py-1.5 text-[13px] text-ink-200 ' +
  'outline-none transition-colors focus:border-agent/70'

export function Empty({ children }: { children: ReactNode }) {
  return <p className="px-3.5 py-6 text-center text-[12px] text-ink-400">{children}</p>
}
