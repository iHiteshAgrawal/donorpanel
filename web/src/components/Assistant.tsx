import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Button, Empty, Icon, inputClass } from './ui'

interface Turn {
  who: 'you' | 'asha'
  text: string
}

const OPENERS = [
  'What is going on with my panel?',
  'Is anything waiting for me?',
  'Tell me about Asha',
]

export function Assistant() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const tail = useRef<HTMLDivElement>(null)

  useEffect(() => {
    tail.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns, busy])

  async function ask(question: string) {
    const asked = question.trim()
    if (!asked || busy) return
    setTurns((t) => [...t, { who: 'you', text: asked }])
    setText('')
    setBusy(true)
    try {
      const { text: answer } = await api.chat(asked)
      setTurns((t) => [...t, { who: 'asha', text: answer }])
    } catch (exc) {
      setTurns((t) => [...t, { who: 'asha', text: `I could not answer that: ${exc}` }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-auto px-4 py-3">
        {turns.length === 0 && (
          <>
            <Empty>Ask about your panel. Asha reads it live and never guesses.</Empty>
            <div className="flex flex-col gap-1.5 px-1">
              {OPENERS.map((o) => (
                <button
                  key={o}
                  onClick={() => void ask(o)}
                  className="rounded-lg border border-border px-3 py-2 text-left text-[13px] text-muted transition-colors hover:border-agent/60 hover:text-text"
                >
                  {o}
                </button>
              ))}
            </div>
          </>
        )}
        <div className="space-y-3">
          {turns.map((turn, i) => (
            <div key={i} className={turn.who === 'you' ? 'flex justify-end' : ''}>
              <div
                className={
                  turn.who === 'you'
                    ? 'max-w-[85%] rounded-lg rounded-br-sm bg-agent-surface px-3 py-2 text-[13px] text-text'
                    : 'max-w-[90%] rounded-lg rounded-bl-sm border border-border bg-raised px-3 py-2 text-[13px] leading-relaxed text-muted'
                }
              >
                {turn.text}
              </div>
            </div>
          ))}
          {busy && (
            <div className="flex items-center gap-2 px-1 text-[12px] text-muted">
              <Icon name="loader" size={13} className="animate-spin" />
              reading the panel
            </div>
          )}
        </div>
        <div ref={tail} />
      </div>

      <form
        className="flex shrink-0 gap-2 border-t border-border p-3"
        onSubmit={(e) => {
          e.preventDefault()
          void ask(text)
        }}
      >
        <input
          className={inputClass}
          placeholder="Ask about a request, a donor, what needs you"
          value={text}
          disabled={busy}
          onChange={(e) => setText(e.target.value)}
        />
        <Button type="submit" disabled={busy || !text.trim()}>
          <Icon name="play" size={14} />
        </Button>
      </form>
    </div>
  )
}
