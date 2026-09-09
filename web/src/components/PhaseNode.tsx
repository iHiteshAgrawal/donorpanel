import { Handle, Position, type NodeProps } from '@xyflow/react'
import clsx from 'clsx'
import type { NodeKind, NodeRun } from '../types'

export interface PhaseNodeData extends Record<string, unknown> {
  label: string
  kind: NodeKind
  detail: string
  run: NodeRun
}

const palette: Record<NodeKind, { ring: string; chip: string; text: string; glow: string }> = {
  agent: {
    ring: 'border-agent/60', chip: 'bg-agent/15 text-agent',
    text: 'text-agent', glow: 'shadow-[0_0_28px_-6px_rgb(167_139_250/.55)]',
  },
  deterministic: {
    ring: 'border-logic/55', chip: 'bg-logic/15 text-logic',
    text: 'text-logic', glow: 'shadow-[0_0_28px_-6px_rgb(96_165_250/.5)]',
  },
  gate: {
    ring: 'border-gate/60', chip: 'bg-gate/15 text-gate',
    text: 'text-gate', glow: 'shadow-[0_0_28px_-6px_rgb(251_113_133/.5)]',
  },
}

const kindLabel: Record<NodeKind, string> = {
  agent: 'Agent',
  deterministic: 'MultiAgentBase',
  gate: 'Gate',
}

export function PhaseNode({ data }: NodeProps & { data: PhaseNodeData }) {
  const tone = palette[data.kind]
  const { status, ms } = data.run
  const idle = status === 'pending'

  return (
    <div
      className={clsx(
        'w-60 rounded-xl border bg-ink-850/95 px-3.5 py-3 backdrop-blur transition-all duration-300',
        idle ? 'border-ink-700 opacity-45' : tone.ring,
        status === 'running' && `running ${tone.glow}`,
        status === 'done' && 'opacity-100',
      )}
    >
      <Handle type="target" position={Position.Top} className="!size-1.5 !border-0 !bg-ink-600" />

      <div className="flex items-center justify-between gap-2">
        <span className={clsx('font-mono text-[13px] font-medium', idle ? 'text-ink-300' : tone.text)}>
          {data.label}
        </span>
        {status === 'running' && (
          <span className="size-1.5 shrink-0 animate-ping rounded-full bg-current" />
        )}
        {status === 'done' && ms !== undefined && (
          <span className="shrink-0 font-mono text-[10px] text-ink-400">
            {ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`}
          </span>
        )}
      </div>

      <div className="mt-1.5 flex items-center gap-1.5">
        <span className={clsx('rounded px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide', tone.chip)}>
          {kindLabel[data.kind]}
        </span>
        {data.kind === 'deterministic' && (
          <span className="font-mono text-[9px] text-ink-400">no model call</span>
        )}
      </div>

      <p className="mt-2 text-[11px] leading-snug text-ink-400">{data.detail}</p>

      <Handle type="source" position={Position.Bottom} className="!size-1.5 !border-0 !bg-ink-600" />
    </div>
  )
}
