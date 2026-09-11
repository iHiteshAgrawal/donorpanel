import { useEffect, useState } from 'react'

interface Pool {
  bot: string
  donors: number
  cities: number
  requests: number
  reached: number
  patient: { name: string; blood_group: string; condition: string; city: string; hospital: string } | null
}

const PAPER = '#f5f2eb'
const CARD = '#fbf9f4'
const INK = '#1a1715'
const SOFT = '#655f58'
const GREEN = '#34c759'
const DEEP = '#176f35'
const SOFT_GREEN = '#dff4df'
const LINE = 'rgba(46, 40, 34, 0.14)'

const THREAD: Array<{ me?: boolean; text: string; gap?: string }> = [
  { text: 'Hi Asha. My friend needs a transfusion in a week, could you find a donor for me?', me: true },
  { text: 'I understand, and I can help. What is the patient’s name, and which city do they need it in?' },
  { text: 'Lakshmi, she’s in Coimbatore. B positive.', me: true },
  { text: 'Thank you. How many units, and by what date?' },
  { text: '2 units, by the 19th.', me: true },
  { text: 'Opened. I am searching my network now and will report back.' },
  { text: 'I have reached 4 donors who match Lakshmi and are rested enough to give. I will tell you the moment one agrees.', gap: 'a minute later' },
]

const STEPS = [
  { k: 'Understand', h: 'Tell me who needs blood', b: 'A name, a city, a blood group, a date. No form, no account, no app to install.' },
  { k: 'Match', h: 'I find the people who can actually give', b: 'Compatible group, rested long enough, close enough, and not already asked this month.' },
  { k: 'Ask', h: 'I do the asking, and I know when to stop', b: 'Routine requests go out on their own. Anything unusual waits for a human.' },
]

const BUILT_ON = ['Bedrock AgentCore', 'Strands Agents', 'Amazon Location', 'Cognito', 'Amazon S3']

export function Landing() {
  const [pool, setPool] = useState<Pool | null>(null)

  useEffect(() => {
    void fetch('/api/public').then((r) => r.json()).then(setPool).catch(() => {})
  }, [])

  const link = `https://t.me/${pool?.bot ?? 'donorpanelbot'}`
  const stats = [
    { n: pool ? `${pool.donors}` : '-', l: 'donors in the network' },
    { n: pool ? `${pool.reached}` : '-', l: 'donors I have reached' },
    { n: pool ? `${pool.cities}` : '-', l: 'cities covered' },
  ]

  return (
    <div
      className="min-h-screen"
      style={{ background: PAPER, color: INK, fontFamily: '"Bricolage Grotesque", ui-sans-serif, system-ui, sans-serif' }}
    >
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <div className="flex items-center gap-2.5">
          <span
            className="flex h-8 w-8 items-center justify-center rounded-full text-[14px] font-bold text-white"
            style={{ background: GREEN }}
          >
            A
          </span>
          <span className="text-[17px] font-semibold tracking-tight">Asha</span>
        </div>
        <nav className="flex items-center gap-5 text-[14px]" style={{ color: SOFT }}>
          <a href="/console" className="transition-opacity hover:opacity-60">Watch her work</a>
          <a
            href={link}
            target="_blank"
            rel="noreferrer"
            className="rounded-full px-4 py-2 text-[14px] font-semibold text-white transition-opacity hover:opacity-90"
            style={{ background: INK }}
          >
            Message me
          </a>
        </nav>
      </header>

      <main className="mx-auto max-w-6xl px-6">
        <section className="grid items-center gap-14 py-12 lg:grid-cols-[1.05fr_400px] lg:py-20">
          <div>
            <h1
              className="text-[42px] font-semibold leading-[1.05] tracking-[-0.02em] sm:text-[62px]"
              style={{ fontFamily: '"Plus Jakarta Sans", ui-sans-serif, system-ui, sans-serif' }}
            >
              I find blood donors, so families don&apos;t have to.
            </h1>
            <p className="mt-7 max-w-xl text-[18px] leading-[1.6]" style={{ color: SOFT }}>
              Thalassemia means a transfusion every few weeks, for life. Today the family
              rings round themselves, every single time. Tell me who needs blood and I
              will do the asking instead.
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-4">
              <a
                href={link}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 rounded-full px-7 py-4 text-[16px] font-semibold text-white transition-opacity hover:opacity-90"
                style={{ background: GREEN }}
              >
                Message me on Telegram
              </a>
              <span className="text-[14px]" style={{ color: SOFT }}>
                {pool
                  ? `${pool.donors} donor${pool.donors === 1 ? '' : 's'} joined by messaging me`
                  : 'Four messages to join. Five to ask.'}
              </span>
            </div>
          </div>

          <div
            className="rounded-[26px] p-5 shadow-[0_1px_2px_rgba(26,23,21,0.04),0_12px_32px_rgba(26,23,21,0.06)]"
            style={{ background: CARD, border: `1px solid ${LINE}` }}
          >
            <div className="mb-4 flex items-center gap-2.5 pb-4" style={{ borderBottom: `1px solid ${LINE}` }}>
              <span
                className="flex h-7 w-7 items-center justify-center rounded-full text-[12px] font-bold text-white"
                style={{ background: GREEN }}
              >
                A
              </span>
              <span className="text-[14px] font-semibold">Asha</span>
              <span className="ml-auto text-[12px]" style={{ color: DEEP }}>online</span>
            </div>
            <div className="space-y-2.5">
              {THREAD.map((m, i) => (
                <div key={i}>
                  {m.gap && (
                    <p className="py-2 text-center text-[12px]" style={{ color: SOFT }}>{m.gap}</p>
                  )}
                  <div className={m.me ? 'flex justify-end' : ''}>
                    <div
                      className="max-w-[85%] rounded-[18px] px-4 py-2.5 text-[14px] leading-[1.5]"
                      style={
                        m.me
                          ? { background: SOFT_GREEN, color: INK, borderBottomRightRadius: 6 }
                          : { background: '#fff', color: INK, border: `1px solid ${LINE}`, borderBottomLeftRadius: 6 }
                      }
                    >
                      {m.text}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="py-10" style={{ borderTop: `1px solid ${LINE}` }}>
          <p className="mb-6 text-center text-[13px] uppercase tracking-[0.14em]" style={{ color: SOFT }}>
            Built on
          </p>
          <div className="flex flex-wrap items-center justify-center gap-x-10 gap-y-4">
            {BUILT_ON.map((b) => (
              <span key={b} className="text-[15px] font-medium" style={{ color: SOFT }}>{b}</span>
            ))}
          </div>
        </section>

        <section className="py-16 lg:py-24" style={{ borderTop: `1px solid ${LINE}` }}>
          <div className="grid gap-10 sm:grid-cols-3">
            {STEPS.map((s) => (
              <div key={s.k}>
                <p className="mb-3 text-[13px] font-semibold uppercase tracking-[0.12em]" style={{ color: DEEP }}>
                  {s.k}
                </p>
                <h3
                  className="mb-2.5 text-[21px] font-semibold leading-snug tracking-[-0.01em]"
                  style={{ fontFamily: '"Plus Jakarta Sans", ui-sans-serif, system-ui, sans-serif' }}
                >
                  {s.h}
                </h3>
                <p className="text-[15px] leading-[1.6]" style={{ color: SOFT }}>{s.b}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="py-16" style={{ borderTop: `1px solid ${LINE}` }}>
          <div className="grid gap-10 sm:grid-cols-3">
            {stats.map((s) => (
              <div key={s.l}>
                <p
                  className="text-[44px] font-semibold leading-none tracking-[-0.02em]"
                  style={{ fontFamily: '"Plus Jakarta Sans", ui-sans-serif, system-ui, sans-serif' }}
                >
                  {s.n}
                </p>
                <p className="mt-2 text-[15px]" style={{ color: SOFT }}>{s.l}</p>
              </div>
            ))}
          </div>
        </section>

        {pool?.patient && (
          <section className="py-16" style={{ borderTop: `1px solid ${LINE}` }}>
            <div className="rounded-[22px] p-8 lg:p-10" style={{ background: CARD, border: `1px solid ${LINE}` }}>
              <p className="mb-3 text-[13px] uppercase tracking-[0.14em]" style={{ color: SOFT }}>
                Waiting right now
              </p>
              <p
                className="max-w-3xl text-[24px] font-medium leading-snug tracking-[-0.01em] sm:text-[28px]"
                style={{ fontFamily: '"Newsreader", Iowan Old Style, Georgia, serif' }}
              >
                {pool.patient.name} has {pool.patient.condition} and needs{' '}
                <span style={{ color: DEEP }}>{pool.patient.blood_group}</span> at{' '}
                {pool.patient.hospital}, {pool.patient.city}. Message me and I will tell
                you in one line whether your blood group can help.
              </p>
            </div>
          </section>
        )}

        <section className="py-16 lg:py-24" style={{ borderTop: `1px solid ${LINE}` }}>
          <h2
            className="max-w-3xl text-[28px] font-semibold leading-snug tracking-[-0.015em] sm:text-[36px]"
            style={{ fontFamily: '"Plus Jakarta Sans", ui-sans-serif, system-ui, sans-serif' }}
          >
            I run on my own, and only wake a human when there is a real decision to make.
          </h2>
          <p className="mt-5 max-w-2xl text-[16px] leading-[1.6]" style={{ color: SOFT }}>
            Every request moves through a graph of ten steps. Only two of them are a
            model. Everything that decides routing is ordinary code, so the same request
            always takes the same path.
          </p>
          <a
            href="/console"
            className="mt-7 inline-flex items-center gap-2 rounded-full px-6 py-3.5 text-[15px] font-semibold transition-opacity hover:opacity-70"
            style={{ border: `1px solid ${INK}`, color: INK }}
          >
            Watch a request move through it
          </a>
        </section>
      </main>

      <footer className="mx-auto max-w-6xl px-6 py-10" style={{ borderTop: `1px solid ${LINE}` }}>
        <p className="text-[13px] leading-relaxed" style={{ color: SOFT }}>
          A demo built for the AWS Agents for Humans hackathon. Donors registered here are
          fictional and all outreach routes to the operator&apos;s own phone.
        </p>
      </footer>
    </div>
  )
}
