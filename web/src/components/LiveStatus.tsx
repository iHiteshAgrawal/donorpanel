import { useEffect, useState } from 'react'
import type { GraphNodeSpec, NodeRun } from '../types'
import { Icon } from './ui'

interface Props {
  nodes: GraphNodeSpec[]
  runs: Record<string, NodeRun>
  startedAt: number | null
}

export function LiveStatus({ nodes, runs, startedAt }: Props) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!startedAt) return
    const tick = () => setElapsed(Math.floor((Date.now() - startedAt) / 1000))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [startedAt])

  const current = nodes.find((n) => runs[n.id]?.status === 'running')
  const doneCount = nodes.filter((n) => runs[n.id]?.status === 'done').length
  const total = nodes.length

  const minutes = Math.floor(elapsed / 60)
  const seconds = elapsed % 60
  const timeStr = minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-agent/30 bg-agent-surface px-4 py-3 animate-fade-in">
      <div className="flex items-center gap-2">
        <span className="relative flex size-2.5">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-agent opacity-75" />
          <span className="relative inline-flex size-2.5 rounded-full bg-agent" />
        </span>
        <span className="text-[13px] font-semibold text-agent">Agent working</span>
      </div>

      {current && (
        <div className="flex items-center gap-2 text-[13px] text-text">
          <Icon name="activity" size={14} className="text-agent" />
          <span className="font-medium">{current.label}</span>
          <span className="hidden text-muted sm:inline">
            {current.detail}
          </span>
        </div>
      )}

      <div className="ml-auto flex items-center gap-3 text-[12px] text-muted">
        <span className="font-mono tabular-nums">{timeStr}</span>
        <div className="flex items-center gap-1">
          {nodes.map((n) => {
            const status = runs[n.id]?.status ?? 'pending'
            return (
              <div
                key={n.id}
                title={n.label}
                className={`size-1.5 rounded-full transition-colors duration-300 ${
                  status === 'done' ? 'bg-agent' :
                  status === 'running' ? 'bg-agent animate-pulse-soft' :
                  'bg-border'
                }`}
              />
            )
          })}
        </div>
        <span className="font-mono tabular-nums">{doneCount}/{total}</span>
      </div>
    </div>
  )
}
