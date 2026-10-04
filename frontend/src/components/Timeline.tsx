import { useMemo } from 'react'
import { useSession } from '../state/sessionContext'
import { Panel } from './ui'
import { SPR_DAMAGE, timelineItems } from '../lib/derive'
import { actionShort } from '../lib/actions'
import { fmtT } from '../lib/format'

const GLYPH: Record<string, string> = { failure: '✕', measurement: '●', redesign: '◆', decision: '■' }

export function Timeline() {
  const s = useSession()
  const items = useMemo(() => (s.frames.length ? timelineItems(s.frames) : []), [s.frames])
  const replay = s.session?.mode === 'replay'
  const live = s.session?.mode === 'live'

  return (
    <Panel
      index="06"
      title="Experiment & redesign timeline"
      className="tl"
      aside={
        <span className="tl__ctl">
          <button className="btn btn--ghost tl__b" onClick={() => s.seek(0)} disabled={s.cursor === 0} aria-label="First step">|◀</button>
          <button className="btn btn--ghost tl__b" onClick={() => s.seek(s.cursor - 1)} disabled={s.cursor === 0} aria-label="Previous step">◀</button>
          {replay && (
            <button className="btn btn--ghost tl__b tl__play" onClick={s.togglePlay} aria-label={s.playing ? 'Pause replay' : 'Play replay'}>
              {s.playing ? '❚❚ PAUSE' : '▶ PLAY'}
            </button>
          )}
          <button className="btn btn--ghost tl__b" onClick={() => s.seek(s.cursor + 1)} disabled={s.cursor >= s.frames.length - 1} aria-label="Next step">▶</button>
          <button className="btn btn--ghost tl__b" onClick={s.reset} aria-label="Reset">↺</button>
        </span>
      }
    >
      <ol className="tl__track" aria-label="Episode steps">
        {items.map((it) => {
          const state = it.step < s.cursor ? 'past' : it.step === s.cursor ? 'now' : 'future'
          return (
            <li key={it.eventId} className={`tl__item tl__item--${it.kind} is-${state}`}>
              <button
                className="tl__mk"
                onClick={() => {
                  s.seek(it.step)
                  s.select(it.eventId)
                }}
                aria-current={state === 'now' ? 'step' : undefined}
                title={it.label}
              >
                <span className="tl__glyph">{GLYPH[it.kind]}</span>
              </button>
              <span className="tl__lbl">{it.action_type ? actionShort(it.action_type) : 'FAILURE'}</span>
              <span className="tl__t mono">{fmtT(it.t_h)}</span>
              {it.spr_delta < -SPR_DAMAGE && <span className="tl__dmg mono">SPR {it.spr_delta.toFixed(2)}</span>}
            </li>
          )
        })}
        {live && !s.atEnd && (
          <li className="tl__item tl__item--pending">
            <span className="tl__mk tl__mk--pending">…</span>
            <span className="tl__lbl">NEXT</span>
          </li>
        )}
      </ol>
    </Panel>
  )
}
