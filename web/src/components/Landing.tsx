import { useEffect, useState } from 'react'
import { Icon } from './ui'

interface Pool {
  bot: string
  donors: number
  cities: number
  patient: { name: string; blood_group: string; condition: string; city: string; hospital: string } | null
}

const STEPS = [
  { n: '01', h: 'You tell Asha your blood group and city', b: 'Four messages on Telegram. No app, no form, no account.' },
  { n: '02', h: 'Asha watches the transfusion calendar', b: 'Patients on a fixed cycle are predictable. The agent knows who is due before anyone has to ask.' },
  { n: '03', h: 'She asks only the people who can actually help', b: 'Compatible group, rested long enough, close enough, not already asked this month.' },
  { n: '04', h: 'She decides whether a human is needed', b: 'Routine repeat goes out on its own. Anything unusual stops and waits for a coordinator.' },
]

export function Landing() {
  const [pool, setPool] = useState<Pool | null>(null)

  useEffect(() => {
    void fetch('/api/public').then((r) => r.json()).then(setPool).catch(() => {})
  }, [])

  const link = `https://t.me/${pool?.bot ?? 'donorpanelbot'}`

  return (
    <div className="min-h-screen bg-page-bg text-text">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
        <div className="flex items-center gap-2">
          <Icon name="brain" size={18} className="text-orange" />
          <span className="text-[15px] font-semibold text-text-strong">DonorPanel</span>
        </div>
        <a href="/console" className="text-[13px] text-muted transition-colors hover:text-text">
          Watch the agent work
        </a>
      </header>

      <main className="mx-auto max-w-5xl px-6">
        <section className="py-16 sm:py-24">
          <p className="mb-5 font-mono text-[12px] uppercase tracking-[0.2em] text-orange">
            Agents for Humans
          </p>
          <h1 className="max-w-3xl text-[38px] font-semibold leading-[1.1] tracking-tight text-text-strong sm:text-[56px]">
            Some patients need matched blood every three weeks. For life.
          </h1>
          <p className="mt-6 max-w-2xl text-[17px] leading-relaxed text-muted sm:text-[19px]">
            Their families find the donors themselves. Every cycle, by phone, forever.
            Asha is an agent that holds the donor network and does the asking instead.
          </p>

          <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
            <a
              href={link}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-orange px-6 py-3.5 text-[15px] font-semibold text-squid transition-colors hover:bg-orange-hover"
            >
              Talk to Asha on Telegram
              <Icon name="play" size={15} />
            </a>
            <span className="text-[13px] text-faint">
              {pool ? `${pool.donors} donor${pool.donors === 1 ? '' : 's'} across ${pool.cities} ${pool.cities === 1 ? 'city' : 'cities'} have joined this way` : 'Joining takes four messages'}
            </span>
          </div>
        </section>

        {pool?.patient && (
          <section className="rounded-xl border border-border bg-surface p-6 sm:p-8">
            <p className="mb-2 font-mono text-[11px] uppercase tracking-[0.18em] text-muted">
              Waiting right now
            </p>
            <p className="text-[17px] leading-relaxed text-text">
              <span className="font-semibold text-text-strong">{pool.patient.name}</span> has{' '}
              {pool.patient.condition} and needs{' '}
              <span className="font-mono text-orange">{pool.patient.blood_group}</span> blood at{' '}
              {pool.patient.hospital}, {pool.patient.city}. If your group is compatible, Asha
              will tell you when you message her.
            </p>
          </section>
        )}

        <section className="py-16 sm:py-20">
          <h2 className="mb-10 text-[22px] font-semibold text-text-strong sm:text-[26px]">
            What the agent actually does
          </h2>
          <div className="grid gap-x-10 gap-y-8 sm:grid-cols-2">
            {STEPS.map((s) => (
              <div key={s.n}>
                <p className="mb-2 font-mono text-[12px] text-orange">{s.n}</p>
                <h3 className="mb-1.5 text-[16px] font-semibold text-text-strong">{s.h}</h3>
                <p className="text-[14px] leading-relaxed text-muted">{s.b}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="border-t border-border py-16 sm:py-20">
          <h2 className="max-w-2xl text-[22px] font-semibold leading-snug text-text-strong sm:text-[26px]">
            The agent runs on its own and only interrupts a human when there is a real
            decision to make.
          </h2>
          <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-muted">
            Every run is a graph of nine steps. Only two of them are a model. Everything
            that decides routing is deterministic code, so the same request always takes
            the same path.
          </p>
          <a
            href="/console"
            className="mt-6 inline-flex items-center gap-2 text-[14px] font-medium text-primary transition-colors hover:text-text-strong"
          >
            Watch a request move through the graph
            <Icon name="play" size={13} />
          </a>
        </section>
      </main>

      <footer className="mx-auto max-w-5xl border-t border-border px-6 py-8">
        <p className="text-[12px] text-faint">
          Built on Amazon Bedrock AgentCore and Strands Agents. Demo pool: donors
          registered here are fictional and outreach routes to the operator.
        </p>
      </footer>
    </div>
  )
}
