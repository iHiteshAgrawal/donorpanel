import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, runRequest } from './api'
import { CohortMap } from './components/CohortMap'
import { GraphCanvas } from './components/GraphCanvas'
import { HeroSection } from './components/HeroSection'
import { Cohort, Drafts, NodeOutput, RequestRow } from './components/Inspector'
import { LiveStatus } from './components/LiveStatus'
import { Memory } from './components/Memory'
import { OutcomeCard } from './components/OutcomeCard'
import { Badge, Button, Empty, Field, Icon, Panel, inputClass } from './components/ui'
import type {
  Actor, Donor, GraphEdgeSpec, GraphNodeSpec, MemoryRecord,
  NodeRun, Patient, RequestDetail, RunState, Stats, Verdict,
} from './types'

/* ── Detail tab names ──────────────────────────────────────── */

const DETAIL_TABS = ['Cohort', 'Drafts', 'Node output', 'Map'] as const
type DetailTab = (typeof DETAIL_TABS)[number]

/* ── App ───────────────────────────────────────────────────── */

export default function App() {
  /* ── Data state ────────────────────────────────────────── */
  const [spec, setSpec] = useState<{ nodes: GraphNodeSpec[]; edges: GraphEdgeSpec[] }>({ nodes: [], edges: [] })
  const [health, setHealth] = useState<{ region: string; model: string; storage: string } | null>(null)
  const [actor, setActor] = useState<Actor | null>(null)
  const [patients, setPatients] = useState<Patient[]>([])
  const [donors, setDonors] = useState<Donor[]>([])
  const [requests, setRequests] = useState<RequestDetail[]>([])
  const [memory, setMemory] = useState<MemoryRecord[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [recalling, setRecalling] = useState(false)

  /* ── Run state ─────────────────────────────────────────── */
  const [runs, setRuns] = useState<Record<string, NodeRun>>({})
  const [activeEdges, setActiveEdges] = useState<Set<string>>(new Set())
  const [state, setState] = useState<RunState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [startedAt, setStartedAt] = useState<number | null>(null)
  const [verdict, setVerdict] = useState<Verdict | null>(null)
  const [hasEverRun, setHasEverRun] = useState(false)

  /* ── UI state ──────────────────────────────────────────── */
  const [detail, setDetail] = useState<RequestDetail | null>(null)
  const [selectedNode, setSelectedNode] = useState<string | null>(null)
  const [detailTab, setDetailTab] = useState<DetailTab>('Cohort')
  const [approving, setApproving] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [resetting, setResetting] = useState(false)

  /* ── Form state ────────────────────────────────────────── */
  const [patientId, setPatientId] = useState('')
  const [neededBy, setNeededBy] = useState(() => {
    const date = new Date()
    date.setDate(date.getDate() + 14)
    return date.toISOString().slice(0, 10)
  })
  const [units, setUnits] = useState(2)
  const [source, setSource] = useState('scheduled')

  /* ── Initial data load ─────────────────────────────────── */
  useEffect(() => {
    const fail = (exc: unknown) => setError(String(exc))
    void api.graph().then(setSpec).catch(fail)
    void api.health().then(setHealth).catch(fail)
    void api.donors().then(setDonors).catch(fail)
    void api.requests().then(setRequests).catch(fail)
    void api.memory().then(setMemory).catch(fail)
    void api.me().then(setActor).catch(fail)
    void api.stats().then(setStats).catch(fail)
    void api.patients().then((pats) => {
      setPatients(pats)
      if (pats[0]) setPatientId(pats[0].patient_id)
    }).catch(fail)
  }, [])

  /* ── Actions ───────────────────────────────────────────── */
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
      setStats(await api.stats())
    } catch { /* list refresh is best effort */ }
  }, [])

  const resetSandbox = useCallback(async () => {
    setResetting(true)
    try {
      await api.resetSandbox()
      // Reload all data
      const [pats, dons, reqs, mem, st] = await Promise.all([
        api.patients(), api.donors(), api.requests(), api.memory(), api.stats(),
      ])
      setPatients(pats)
      setDonors(dons)
      setRequests(reqs)
      setMemory(mem)
      setStats(st)
      if (pats[0]) setPatientId(pats[0].patient_id)
      setDetail(null)
      setVerdict(null)
      setState('idle')
      setHasEverRun(false)
      setRuns({})
      setActiveEdges(new Set())
      setError(null)
    } catch (exc) {
      setError(String(exc))
    } finally {
      setResetting(false)
    }
  }, [])

  const start = useCallback(async () => {
    setState('running')
    setError(null)
    setDetail(null)
    setSelectedNode(null)
    setVerdict(null)
    setDetailTab('Cohort')
    setStartedAt(Date.now())
    setHasEverRun(true)
    setRuns(Object.fromEntries(spec.nodes.map((n) => [n.id, { status: 'pending' as const }])))
    setActiveEdges(new Set())
    setSidebarOpen(false)

    try {
      await runRequest(
        { patient_id: patientId, needed_by: neededBy, units_needed: units, source },
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
            setStartedAt(null)
            // Extract verdict from the done event
            if (data.gate) {
              setVerdict({
                gate: data.gate as Verdict['gate'],
                checks_passed: data.checks_passed as string[] | undefined,
                reasons: data.reasons as string[] | undefined,
              })
            }
            void refresh()
            void recall()
          },
          onFailed: (message) => {
            setError(message)
            setState('failed')
            setStartedAt(null)
          },
        },
      )
    } catch (exc) {
      setError(String(exc))
      setState('failed')
      setStartedAt(null)
    }
  }, [patientId, neededBy, units, source, spec.nodes, refresh, recall])

  const open = useCallback(async (id: string) => {
    try {
      const d = await api.detail(id)
      setDetail(d)
      setDetailTab('Cohort')
      setVerdict(null) // Clear live verdict when viewing history
      // Try to reconstruct verdict from the request status
      if (d.status === 'dispatched' && d.approval === null) {
        setVerdict({ gate: 'auto' })
      } else if (d.status === 'awaiting_approval') {
        setVerdict({ gate: 'escalated' })
      } else if (d.approval) {
        setVerdict({ gate: 'approved' })
      }
    } catch (exc) {
      setError(String(exc))
    }
  }, [])

  const approve = useCallback(async (by: string) => {
    if (!detail) return
    setApproving(true)
    try {
      const updated = await api.approve(detail.request_id, by)
      setDetail(updated)
      setVerdict({ gate: 'approved' })
      await refresh()
    } catch (exc) {
      setError(String(exc))
    } finally {
      setApproving(false)
    }
  }, [detail, refresh])

  /* ── Derived ───────────────────────────────────────────── */
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
  const showGraph = running || state === 'done' || state === 'failed'

  /* ── Render ────────────────────────────────────────────── */
  return (
    <div className="flex h-full flex-col bg-page-bg">

      {/* ── Top bar ────────────────────────────────────── */}
      <header className="z-30 flex shrink-0 items-center justify-between border-b border-border bg-squid px-5 py-3">
        <div className="flex items-center gap-3">
          {/* Mobile menu button */}
          <button
            className="rounded p-1.5 text-muted hover:text-text lg:hidden"
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            <Icon name="menu" size={22} />
          </button>

          <div className="flex items-baseline gap-3">
            <h1 className="text-lg font-bold tracking-tight text-text-strong">
              <span className="text-orange">Donor</span>Panel
            </h1>
            <p className="hidden text-sm text-muted sm:block">
              Matched donor coordination for transfusion-dependent patients
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Health info */}
          {health && (
            <div className="hidden items-center gap-2 lg:flex">
              <Badge>{health.region}</Badge>
              <Badge tone="agent">{health.model}</Badge>
            </div>
          )}

          {/* Identity */}
          {actor && (
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 rounded-lg border border-border bg-raised px-2.5 py-1">
                <Icon name="user" size={16} className="text-muted" />
                <span className="text-sm text-text">
                  {actor.authenticated ? actor.name : `Guest ${actor.actor_id.slice(0, 8)}`}
                </span>
              </div>
            </div>
          )}

          {/* Reset */}
          <Button
            variant="ghost"
            onClick={() => void resetSandbox()}
            disabled={resetting || running}
          >
            <Icon name="refresh" size={16} />
            <span className="hidden sm:inline">{resetting ? 'Resetting...' : 'Reset sandbox'}</span>
          </Button>
        </div>
      </header>

      {/* ── Sandbox notice ─────────────────────────────── */}
      {actor && !actor.authenticated && (
        <div className="border-b border-border-dim bg-raised px-5 py-2 text-center text-[13px] text-faint">
          You are in a private sandbox. Each visitor gets their own data so demos do not collide.
        </div>
      )}

      {/* ── Main layout ────────────────────────────────── */}
      <main className="flex min-h-0 flex-1">

        {/* ── Sidebar overlay (mobile) ─────────────────── */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 z-40 bg-page-bg/60 backdrop-blur-sm lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        {/* ── Sidebar ──────────────────────────────────── */}
        <aside className={`
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
          fixed inset-y-0 left-0 z-50 flex w-[340px] flex-col border-r border-border bg-surface
          transition-transform duration-200 lg:relative lg:translate-x-0
        `}>
          {/* Mobile close */}
          <button
            className="absolute right-3 top-3 rounded p-1.5 text-muted hover:text-text lg:hidden"
            onClick={() => setSidebarOpen(false)}
          >
            <Icon name="x" size={20} />
          </button>

          {/* Request form */}
          <div className="shrink-0 border-b border-border p-5">
            <h2 className="mb-3 text-[15px] font-semibold text-text">New request</h2>
            <div className="space-y-3">
              <Field label="Patient">
                <select
                  className={inputClass}
                  value={patientId}
                  disabled={running}
                  onChange={(e) => setPatientId(e.target.value)}
                >
                  {patients.map((p) => (
                    <option key={p.patient_id} value={p.patient_id}>
                      {p.name} · {p.blood_group} · {p.condition}
                    </option>
                  ))}
                </select>
              </Field>
              <div className="grid grid-cols-[1fr_5rem] gap-2">
                <Field label="Needed by">
                  <input
                    type="date"
                    className={inputClass}
                    value={neededBy}
                    disabled={running}
                    onChange={(e) => setNeededBy(e.target.value)}
                  />
                </Field>
                <Field label="Units">
                  <input
                    type="number"
                    min={1}
                    max={12}
                    className={inputClass}
                    value={units}
                    disabled={running}
                    onChange={(e) => setUnits(Number(e.target.value))}
                  />
                </Field>
              </div>
              <Field label="Source">
                <select
                  className={inputClass}
                  value={source}
                  disabled={running}
                  onChange={(e) => setSource(e.target.value)}
                >
                  <option value="scheduled">Scheduled transfusion</option>
                  <option value="emergency">Emergency</option>
                </select>
              </Field>
              <Button
                variant="primary"
                className="w-full"
                disabled={running || !patientId}
                onClick={() => void start()}
              >
                {running ? (
                  <>
                    <Icon name="loader" size={16} className="animate-spin" />
                    Agent running...
                  </>
                ) : (
                  <>
                    <Icon name="play" size={16} />
                    Run request
                  </>
                )}
              </Button>
              {error && (
                <p className="rounded-lg border border-error/30 bg-error-dim px-3 py-2 text-sm text-error">
                  {error}
                </p>
              )}
            </div>
          </div>

          {/* Requests list */}
          <div className="min-h-0 flex-1 overflow-auto border-b border-border">
            <div className="flex items-center justify-between px-5 py-3">
              <h2 className="text-[15px] font-semibold text-text">
                Requests{requests.length > 0 && <span className="ml-1.5 text-muted">({requests.length})</span>}
              </h2>
            </div>
            {requests.length === 0
              ? <Empty>No requests yet.</Empty>
              : requests.map((row) => (
                  <RequestRow
                    key={row.request_id}
                    detail={row}
                    active={detail?.request_id === row.request_id}
                    onClick={() => void open(row.request_id)}
                  />
                ))}
          </div>

          {/* Memory */}
          <div className="h-64 shrink-0 overflow-auto">
            <div className="flex items-center justify-between px-5 py-3">
              <h2 className="flex items-center gap-2 text-[15px] font-semibold text-text">
                <Icon name="brain" size={16} className="text-agent" />
                Agent memory
              </h2>
              <button
                onClick={() => void recall()}
                disabled={recalling}
                className="rounded-md px-2.5 py-1 text-[13px] font-medium text-muted transition-colors hover:bg-raised hover:text-text disabled:opacity-40"
              >
                {recalling ? 'Reading...' : 'Refresh'}
              </button>
            </div>
            <Memory records={memory} hasRunCompleted={hasEverRun} />
          </div>
        </aside>

        {/* ── Main content ─────────────────────────────── */}
        <div className="flex min-h-0 flex-1 flex-col overflow-auto">

          {/* Welcome hero (before any run) */}
          {!showGraph && !detail && (
            <HeroSection stats={stats} />
          )}

          {/* Live status bar (during run) */}
          {running && (
            <div className="shrink-0 p-5 pb-0">
              <LiveStatus nodes={spec.nodes} runs={runs} startedAt={startedAt} />
            </div>
          )}

          {/* Graph */}
          {showGraph && (
            <div className="shrink-0 p-5 pb-0">
              <Panel
                title="Agent pipeline"
                action={
                  <span className="text-sm text-muted">
                    {running ? 'executing' : state === 'done' ? 'complete' : state === 'failed' ? 'failed' : 'idle'}
                  </span>
                }
                className="h-[560px]"
              >
                <GraphCanvas
                  spec={spec}
                  runs={runs}
                  activeEdges={activeEdges}
                  selected={selectedNode}
                  onSelect={setSelectedNode}
                />
              </Panel>
            </div>
          )}

          {/* Outcome card */}
          {(verdict && detail) && (
            <div className="shrink-0 p-5 pb-0">
              <OutcomeCard
                verdict={verdict}
                detail={detail}
                onApprove={(by) => void approve(by)}
                busy={approving}
              />
            </div>
          )}

          {/* Detail tabs (after run or when viewing a request) */}
          {detail && (
            <div className="min-h-0 flex-1 p-5">
              <Panel
                title={detailTab}
                action={
                  <div className="flex gap-1">
                    {DETAIL_TABS.map((name) => (
                      <button
                        key={name}
                        onClick={() => setDetailTab(name)}
                        className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                          detailTab === name
                            ? 'bg-raised text-text'
                            : 'text-muted hover:text-text'
                        }`}
                      >
                        {name}
                      </button>
                    ))}
                  </div>
                }
              >
                {detailTab === 'Cohort' && <Cohort detail={detail} donors={donors} />}
                {detailTab === 'Drafts' && <Drafts detail={detail} />}
                {detailTab === 'Node output' && (
                  <div>
                    {/* Node selector */}
                    <div className="flex flex-wrap gap-1.5 border-b border-border px-5 py-3">
                      {spec.nodes.map((n) => {
                        const nodeRun = runs[n.id]
                        const hasDone = nodeRun?.status === 'done'
                        return (
                          <button
                            key={n.id}
                            onClick={() => setSelectedNode(n.id)}
                            className={`rounded-md px-2.5 py-1 text-[13px] font-medium transition-colors ${
                              selectedNode === n.id
                                ? 'bg-agent-dim text-agent'
                                : hasDone
                                  ? 'text-muted hover:text-text hover:bg-raised'
                                  : 'text-faint'
                            }`}
                          >
                            {n.label}
                          </button>
                        )
                      })}
                    </div>
                    <NodeOutput node={nodeSpec} run={selectedNode ? runs[selectedNode] : undefined} />
                  </div>
                )}
                {detailTab === 'Map' && (
                  <div className="h-96">
                    <CohortMap patient={patient} donors={donors} cohortIds={cohortIds} />
                  </div>
                )}
              </Panel>
            </div>
          )}

          {/* Viewing a historic request without a graph */}
          {!showGraph && detail && !verdict && (
            <div className="p-5">
              <div className="rounded-xl border border-border bg-surface p-5">
                <p className="text-sm text-muted">
                  Viewing request <span className="font-mono text-text">{detail.request_id.slice(0, 12)}</span> - {detail.status}
                </p>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
