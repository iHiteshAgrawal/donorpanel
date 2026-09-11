import type { MemoryRecord } from '../types'
import { Empty } from './ui'

export function Memory({ records }: { records: MemoryRecord[] }) {
  if (records.length === 0) {
    return <Empty>Nothing learned yet. Run a request.</Empty>
  }
  return (
    <div className="flex flex-col gap-2 px-3.5 py-3">
      {records.map((record, index) => (
        <article key={index} className="rounded-lg border border-ink-800 bg-ink-950/60 p-3">
          <div className="mb-1.5 flex items-center gap-1.5">
            {record.kind === 'preference' ? (
              <span className="rounded bg-agent/15 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide text-agent">
                preference
              </span>
            ) : (
              <span className="rounded bg-logic/15 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide text-logic">
                finding
              </span>
            )}
            {typeof record.score === 'number' && (
              <span className="font-mono text-[9px] text-ink-400">
                {record.score.toFixed(2)}
              </span>
            )}
          </div>
          <p className="text-[12px] leading-relaxed text-ink-300">{record.text}</p>
        </article>
      ))}
    </div>
  )
}
