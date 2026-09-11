import type { MemoryRecord } from '../types'
import { Badge, Empty, Icon } from './ui'

interface Props {
  records: MemoryRecord[]
  hasRunCompleted?: boolean
}

export function Memory({ records, hasRunCompleted }: Props) {
  if (records.length === 0) {
    if (hasRunCompleted) {
      return (
        <div className="flex flex-col items-center gap-3 px-4 py-8 text-center">
          <div className="shimmer h-3 w-3/4 rounded" />
          <div className="shimmer h-3 w-1/2 rounded" />
          <p className="mt-2 text-[12px] text-muted">
            Still learning... findings appear within seconds, preferences take about a minute.
          </p>
        </div>
      )
    }
    return <Empty>Nothing learned yet. Run a request to see what the agent remembers.</Empty>
  }

  const findings = records.filter((r) => r.kind === 'finding')
  const preferences = records.filter((r) => r.kind === 'preference')

  return (
    <div className="flex flex-col gap-2 px-4 py-3">
      {findings.length > 0 && (
        <div className="space-y-2">
          {findings.map((record, index) => (
            <MemoryItem key={`f-${index}`} record={record} />
          ))}
        </div>
      )}

      {preferences.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 pb-1 pt-2">
            <Icon name="sparkles" size={12} className="text-agent" />
            <span className="text-[11px] font-medium text-agent">Learned preferences</span>
          </div>
          {preferences.map((record, index) => (
            <MemoryItem key={`p-${index}`} record={record} />
          ))}
        </div>
      )}

      {hasRunCompleted && preferences.length === 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-border-dim bg-raised px-3 py-2.5">
          <div className="shimmer size-2 rounded-full" />
          <p className="text-[11px] text-muted">
            Preferences extract asynchronously and may appear after ~1 minute.
          </p>
        </div>
      )}
    </div>
  )
}

function MemoryItem({ record }: { record: MemoryRecord }) {
  return (
    <article className="rounded-lg border border-border-dim bg-raised p-3">
      <div className="mb-1.5 flex items-center gap-1.5">
        <Badge tone={record.kind === 'preference' ? 'agent' : 'logic'}>
          {record.kind}
        </Badge>
        {typeof record.score === 'number' && (
          <span className="font-mono text-[10px] text-faint">
            {record.score.toFixed(2)}
          </span>
        )}
      </div>
      <p className="text-[12px] leading-relaxed text-text">{record.text}</p>
    </article>
  )
}
