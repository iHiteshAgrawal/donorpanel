import {
  Background, BackgroundVariant, ReactFlow, type Edge, type Node,
} from '@xyflow/react'
import { useMemo } from 'react'
import type { GraphEdgeSpec, GraphNodeSpec, NodeRun } from '../types'
import { PhaseNode, type PhaseNodeData } from './PhaseNode'

const nodeTypes = { phase: PhaseNode }

// Laid out by hand in three phase columns so the flow reads left to right and
// matches the architecture diagram. Dagre would reflow it into a diagonal.
const LAYOUT: Record<string, { x: number; y: number }> = {
  intake: { x: 0, y: 0 },
  verify: { x: 0, y: 150 },
  adjudicate: { x: 0, y: 300 },
  close: { x: 0, y: 460 },
  accept: { x: 330, y: 300 },
  eligibility: { x: 330, y: 450 },
  rank: { x: 330, y: 600 },
  compose: { x: 660, y: 450 },
  gate: { x: 660, y: 600 },
}

const PHASES = [
  { label: 'Phase 1 · Intake', x: 0, y: -54 },
  { label: 'Phase 2 · Match', x: 330, y: 246 },
  { label: 'Phase 3 · Approve', x: 660, y: 396 },
]

interface Props {
  spec: { nodes: GraphNodeSpec[]; edges: GraphEdgeSpec[] }
  runs: Record<string, NodeRun>
  activeEdges: Set<string>
  onSelect: (nodeId: string) => void
  selected: string | null
}

export function GraphCanvas({ spec, runs, activeEdges, onSelect, selected }: Props) {
  const nodes = useMemo<Node<PhaseNodeData>[]>(
    () =>
      spec.nodes.map((node) => ({
        id: node.id,
        type: 'phase',
        position: LAYOUT[node.id] ?? { x: 0, y: 0 },
        selected: selected === node.id,
        data: {
          label: node.label,
          kind: node.kind,
          detail: node.detail,
          run: runs[node.id] ?? { status: 'pending' },
        },
      })),
    [spec.nodes, runs, selected],
  )

  const edges = useMemo<Edge[]>(
    () =>
      spec.edges.map((edge) => {
        const key = `${edge.source}->${edge.target}`
        const live = activeEdges.has(key)
        return {
          id: key,
          source: edge.source,
          target: edge.target,
          label: edge.label,
          animated: false,
          className: live ? 'flowing' : undefined,
          style: {
            stroke: live ? '#a78bfa' : '#232d40',
            strokeWidth: live ? 2 : 1.25,
            transition: 'stroke .3s',
          },
          labelStyle: { fill: '#64748b', fontSize: 10, fontFamily: 'var(--font-mono)' },
          labelBgStyle: { fill: '#0d111a' },
          labelBgPadding: [5, 2] as [number, number],
          labelBgBorderRadius: 3,
        }
      }),
    [spec.edges, activeEdges],
  )

  return (
    <div className="relative h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={(_, node) => onSelect(node.id)}
        fitView
        fitViewOptions={{ padding: 0.18 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        minZoom={0.4}
        maxZoom={1.4}
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#1b2333" />
      </ReactFlow>

      <div className="pointer-events-none absolute inset-0">
        {PHASES.map((phase) => (
          <span key={phase.label} className="sr-only">{phase.label}</span>
        ))}
      </div>
    </div>
  )
}
