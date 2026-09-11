import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, runRequest } from './api'
import { CohortMap } from './components/CohortMap'
import { GraphCanvas } from './components/GraphCanvas'
import { Approval, Cohort, NodeOutput, RequestRow } from './components/Inspector'
import { Memory } from './components/Memory'
import { Button, Empty, Field, inputClass, Panel } from './components/ui'
import type {
  Donor, GraphEdgeSpec, GraphNodeSpec, MemoryRecord, NodeRun, Patient, RequestDetail, RunState,
} from './types'

const TABS = ['Output', 'Cohort', 'Drafts'] as const
type Tab = (typeof TABS)[number]

export default function App() {
  const [spec, setSpec] = useState<{ nodes: GraphNodeSpec[]; edges: GraphEdgeSpec[] }>({ nodes: [], edges: [] })
  const [health, setHealth] = useState<{ region: string; model: string; storage: string } | null>(null)
  const [patients, setPatients] = useState<Patient[]>([])
  const [donors, setDonors] = useState<Donor[]>([])
  const [requests, setRequests] = useState<RequestDetail[]>([])
  const [memory, setMemory] = useState<MemoryRecord[]>([])
  const [recalling, setRecalling] = useState(false)

  const [runs, setRuns] = useState<Record<string, NodeRun>>({})
  const [activeEdges, setActiveEdges] = useState<Set<string>>(new Set())
  const [state, setState] = useState<RunState>('idle')
  const [error, setError] = useState<string | null>(null)

  const [detail, setDetail] = useState<RequestDetail | null>(null)
  const [selectedNode, setSelectedNode] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('Output')
  const [approving, setApproving] = useState(false)

  const [patientId, setPatientId] = useState('')
  const [neededBy, setNeededBy] = useState(() => {
    const date = new Date()
    date.setDate(date.getDate() + 14)
    return date.toISOString().slice(0, 10)
  })
  const [units, setUnits] = useState(2)

  useEffect(() => {
    // Deliberately not Promise.all. One slow endpoint would otherwise hold back
    // every other panel, and the graph should paint immediately.
    const fail = (exc: unknown) => setError(String(exc))
    void api.graph().then(setSpec).catch(fail)
    void api.health().then(setHealth).catch(fail)
    void api.donors().then(setDonors).catch(fail)
    void api.requests().then(setRequests).catch(fail)
    void api.memory().then(setMemory).catch(fail)
    void api.patients().then((pats) => {
      setPatients(pats)
      if (pats[0]) setPatientId(pats[0].patient_id)
    }).catch(fail)
  }, [])

  const recall = useCallback(async () => {
    setRecalling(true)
    try {
      setMemory(await api.memory())
    } catch { /* an empty panel beats a broken one */ } finally {
      setRecalling(false)
    }
  }, [])

  const refresh = useCallback(async () => {
    try {
      setRequests(await api.requests())
    } catch { /* list refresh is best effort */ }
  }, [])

  const start = useCallback(async () => {
    setState('running')
    setError(null)
    setDetail(null)
    setSelectedNode(null)
    setTab('Output')
    setRuns(Object.fromEntries(spec.nodes.map((n) => [n.id, { status: 'pending' as const }])))
    setActiveEdges(new Set())

    try {
      await runRequest(
        { patient_id: patientId, needed_by: neededBy, units_needed: units },
        {
          onNodeStart: (nodeId) => {
            setSelectedNode((current) => current ?? nodeId)
            setRuns((prev) => ({ ...prev, [nodeId]: { status: 'running' } }))
          },
          onNodeStop: ({ node_id, ms, output }) =>
            setRuns((prev) => ({ ...prev, [node_id]: { status: 'done', ms, output } })),
          onHandoff: ({ from, to }) =>
            setActiveEdges((prev) => {
              const next = new Set(prev)
              from.forEach((f) => to.forEach((t) => next.add(`${f}->${t}`)))
              return next
            }),
          onDone: (data) => {
            setDetail(data.detail as RequestDetail)
            setState('done')
            setTab('Drafts')
            void refresh()
            void recall()
          },
          onFailed: (message) => {
            setError(message)
            setState('failed')
          },
        },
      )
    } catch (exc) {
      setError(String(exc))
      setState('failed')
    }
  }, [patientId, neededBy, units, spec.nodes, refresh, recall])

  const open = useCallback(async (id: string) => {
    try {
      setDetail(await api.detail(id))
      setTab('Cohort')
    } catch (exc) {
      setError(String(exc))
    }
  }, [])

  const approve = useCallback(async (by: string) => {
    if (!detail) return
    setApproving(true)
    try {
      setDetail(await api.approve(detail.request_id, by))
      await refresh()
    } catch (exc) {
      setError(String(exc))
    } finally {
      setApproving(false)
    }
  }, [detail, refresh])

  const patient = useMemo(
    () => patients.find((p) => p.patient_id === (detail?.patient_id ?? patientId)) ?? null,
    [patients, detail, patientId],
  )
  const cohortIds = useMemo(() => detail?.contacts.map((c) => c.donor_id) ?? [], [detail])
  const nodeSpec = useMemo(
    () => spec.nodes.find((n) => n.id === selectedNode) ?? null,
    [spec.nodes, selectedNode],
  )
  const running = state === 'running'

  return (
    <div className="flex h-full flex-col bg-ink-950">
      <header className="flex shrink-0 items-center justify-between border-b border-ink-800 px-4 py-2.5">
        <div className="flex items-baseline gap-2.5">
          <h1 className="text-[15px] font-semibold tracking-tight text-ink-200">DonorPanel</h1>
          <p className="text-[11px] text-ink-400">
            Matched donor coordination for transfusion-dependent patients
          </p>
        </div>
        {health && (
          <div className="flex items-center gap-3 font-mono text-[10px] text-ink-400">
            <span>{health.region}</span>
            <span className="text-ink-700">·</span>
            <span>{health.model}</span>
            <span className="text-ink-700">·</span>
            <span className="truncate max-w-[16rem]">{health.storage}</span>
          </div>
        )}
      </header>

      <main className="grid min-h-0 flex-1 gap-3 p-3 lg:grid-cols-[19rem_minmax(0,1fr)_25rem]">
        <div className="flex min-h-0 flex-col gap-3">
          <Panel title="New request" className="shrink-0">
            <div className="space-y-2.5 px-3.5 py-3">
              <Field label="Patient">
                <select
                  className={inputClass}
                  value={patientId}
                  disabled={running}
                  onChange={(event) => setPatientId(event.target.value)}
                >
                  {patients.map((p) => (
                    <option key={p.patient_id} value={p.patient_id}>
                      {p.name} · {p.blood_group} · {p.condition}
                    </option>
                  ))}
                </select>
              </Field>
              <div className="grid grid-cols-[1fr_5.5rem] gap-2">
                <Field label="Needed by">
                  <input type="date" className={inputClass} value={neededBy}
                         disabled={running}
                         onChange={(event) => setNeededBy(event.target.value)} />
                </Field>
                <Field label="Units">
                  <input type="number" min={1} max={12} className={inputClass} value={units}
                         disabled={running}
                         onChange={(event) => setUnits(Number(event.target.value))} />
                </Field>
              </div>
              <Button variant="primary" className="w-full" disabled={running || !patientId} onClick={() => void start()}>
                {running ? 'Running graph…' : 'Run request graph'}
              </Button>
              {error && <p className="text-[11px] text-gate">{error}</p>}
            </div>
          </Panel>

          <Panel title={`Requests · ${requests.length}`} className="min-h-0 flex-1">
            {requests.length === 0
              ? <Empty>No requests yet.</Empty>
              : requests.map((row) => (
                  <RequestRow key={row.request_id} detail={row}
                              active={detail?.request_id === row.request_id}
                              onClick={() => void open(row.request_id)} />
                ))}
          </Panel>
        </div>

        <Panel
          title="Request graph"
          action={
            <span className="font-mono text-[10px] text-ink-400">
              {running ? 'executing' : state === 'done' ? 'complete' : 'idle'}
            </span>
          }
        >
          <GraphCanvas spec={spec} runs={runs} activeEdges={activeEdges}
                       selected={selectedNode} onSelect={setSelectedNode} />
        </Panel>

        <div className="flex min-h-0 flex-col gap-3">
          <Panel
            className="min-h-0 flex-1"
            title={tab === 'Output' ? (nodeSpec?.label ?? 'Inspector') : tab === 'Cohort' ? 'Matched cohort' : 'Outreach drafts'}
            action={
              <div className="flex gap-1">
                {TABS.map((name) => (
                  <button key={name} onClick={() => setTab(name)}
                          className={`rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide transition-colors ${
                            tab === name ? 'bg-ink-800 text-ink-200' : 'text-ink-400 hover:text-ink-300'
                          }`}>
                    {name}
                  </button>
                ))}
              </div>
            }
          >
            {tab === 'Output' && <NodeOutput node={nodeSpec} run={selectedNode ? runs[selectedNode] : undefined} />}
            {tab === 'Cohort' && <Cohort detail={detail} donors={donors} />}
            {tab === 'Drafts' && <Approval detail={detail} onApprove={(by) => void approve(by)} busy={approving} />}
          </Panel>

          <Panel
            title="Agent memory"
            className="h-56 shrink-0"
            action={
              <button onClick={() => void recall()} disabled={recalling}
                      className="rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide text-ink-400 transition-colors hover:text-ink-200 disabled:opacity-40">
                {recalling ? 'reading' : 'refresh'}
              </button>
            }
          >
            <Memory records={memory} />
          </Panel>

          <Panel title="Donor geography" className="h-56 shrink-0">
            <CohortMap patient={patient} donors={donors} cohortIds={cohortIds} />
          </Panel>
        </div>
      </main>
    </div>
  )
}
