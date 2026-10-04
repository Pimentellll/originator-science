import { useEffect, useMemo, useRef, useState } from 'react'
import { useSession } from '../state/sessionContext'
import { buildBeats } from '../lib/guided'
import type { Focus } from '../lib/guided'
import { actionLabel } from '../lib/actions'

/**
 * Narrated walk through a real, deterministic campaign (fixed seed, fixed scenario, MIRAGE drives).
 * Each step is built from the public trace and the post-decision evaluator verdict; nothing is
 * scripted. NEXT executes the policy's next real action and narrates what actually happened.
 */
export function GuidedCoach({ onFocus }: { onFocus: (f: Focus | null) => void }) {
  const s = useSession()
  const beats = useMemo(() => buildBeats(s.frames), [s.frames])
  const [idx, setIdx] = useState(0)
  const pending = useRef<number | null>(null)

  // A run just appended beats: jump to the first new one.
  useEffect(() => {
    if (pending.current !== null && beats.length > pending.current) {
      setIdx(pending.current)
      pending.current = null
    }
  }, [beats.length])

  const cur = Math.min(idx, Math.max(beats.length - 1, 0))
  const beat = beats[cur]
  const { seek, cursor } = s
  useEffect(() => {
    if (!beat) return
    onFocus(beat.focus)
    if (beat.cursor !== cursor) seek(beat.cursor)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- follow the beat, not the cursor it caused
  }, [beat?.id])
  useEffect(() => () => onFocus(null), [onFocus])

  if (!beat) return null
  const atLatest = cur >= beats.length - 1
  const last = s.frames.at(-1)
  const finished = beat.kind === 'justification'
  const next = last?.recommendation
  const nextLabel = next ? actionLabel(next.action_type) : null

  const go = () => {
    if (!atLatest) return setIdx(cur + 1)
    if (s.canRun && s.phase === 'ready') {
      pending.current = beats.length
      s.run()
    }
  }

  return (
    <section className="coach" aria-label="Guided demo">
      <div className="coach__main">
        <div className="coach__head">
          <span className="pill pill--warn">GUIDED DEMO</span>
          <h2 className="coach__title">
            <span className="mono coach__n">STEP {cur + 1}</span> — {beat.heading}
          </h2>
          <span className="coach__dots" aria-hidden>
            {beats.map((b, i) => (
              <i key={b.id} className={i === cur ? 'is-on' : i < cur ? 'is-past' : ''} />
            ))}
          </span>
        </div>
        <div className="coach__body" aria-live="polite">
          {beat.body.map((line, i) => (
            <p key={i} className={i === 0 ? 'coach__lead' : ''}>
              {line}
            </p>
          ))}
        </div>
      </div>
      <div className="coach__ctl">
        <button className="btn" onClick={() => setIdx(Math.max(cur - 1, 0))} disabled={cur === 0}>
          ◀ BACK
        </button>
        {finished && atLatest ? (
          <>
            <button className="btn btn--primary" onClick={() => s.launchCampaign({ scenario: s.launch.scenario, semantics: s.launch.semantics, policy: s.launch.policy, seed: s.launch.seed, control: 'auto', guided: true })}>
              ↻ REPLAY GUIDED DEMO
            </button>
            <button className="btn" onClick={s.endGuided}>
              EXPLORE FREELY
            </button>
          </>
        ) : (
          <button className="btn btn--primary" onClick={go} disabled={atLatest && (!s.canRun || s.phase !== 'ready')}>
            {s.phase === 'running' ? 'RUNNING…' : atLatest && nextLabel ? `NEXT ▶ MIRAGE runs: ${nextLabel}` : 'NEXT ▶'}
          </button>
        )}
        {!(finished && atLatest) && (
          <button className="btn btn--ghost" onClick={s.endGuided} title="Leave the guided walk-through; the campaign stays open">
            EXIT GUIDED
          </button>
        )}
      </div>
    </section>
  )
}
