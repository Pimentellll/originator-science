import { useSession } from '../state/sessionContext'
import { actionKind, actionLabel, actionShort } from '../lib/actions'
import { ACTION_TYPES } from '../lib/wire'
import type { ActionType } from '../lib/types'
import { MECH_LABEL } from '../lib/format'

const GROUPS: { title: string; kind: 'measurement' | 'redesign' | 'decision'; hint: string }[] = [
  { title: 'MEASURE', kind: 'measurement', hint: 'Spend budget and sample to learn something' },
  { title: 'REDESIGN', kind: 'redesign', hint: 'Make a new candidate; the old one is superseded' },
  { title: 'DECIDE', kind: 'decision', hint: 'Ends the campaign' },
]

/**
 * MANUAL SCIENTIST: the person chooses the next action from what the PUBLIC state allows, next to
 * what MIRAGE recommends from the same state. Only public information is shown; hidden truth never
 * reaches this component.
 */
export function ManualControls() {
  const s = useSession()
  const { frame, session } = s
  if (!frame) return null
  const allowed = new Set<ActionType>(session?.available_actions ?? [])
  const ra = frame.recommendation
  const busy = s.phase !== 'ready' || !s.atEnd
  const choose = (a: ActionType) => !busy && allowed.has(a) && s.act(a)

  return (
    <div className="man">
      <div className="man__you">
        <div className="man__hd">
          <span className="hdr__label">Your action</span>
          <span className="dim">Would you run SPR now? Pick any enabled action. Greyed actions are not affordable with the remaining budget or sample.</span>
        </div>
        <div className="man__groups">
          {GROUPS.map((g) => (
            <div key={g.kind} className="man__group" role="group" aria-label={g.title}>
              <span className="man__gt mono" title={g.hint}>
                {g.title}
              </span>
              <div className="man__btns">
                {ACTION_TYPES.filter((a) => actionKind(a) === g.kind).map((a) => {
                  const ok = allowed.has(a)
                  return (
                    <button key={a} className={`man__btn man__btn--${g.kind} ${ra?.action_type === a ? 'is-rec' : ''}`} disabled={busy || !ok} onClick={() => choose(a)} title={ok ? actionLabel(a) : `${actionLabel(a)}: not affordable in the current state`}>
                      <span className="mono man__short">{actionShort(a)}</span>
                      {actionLabel(a)}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
      <aside className="man__rec" aria-label="MIRAGE recommends">
        <span className="hdr__label">MIRAGE recommends</span>
        {ra ? (
          <>
            <b className="man__recname">{actionLabel(ra.action_type)}</b>
            <span className="man__recwhy">{ra.rationale ?? 'The policy gave no public rationale for this step.'}</span>
            <span className="man__recdisc">{ra.discriminates.map((m) => <span key={m} className="chip">{MECH_LABEL[m]}</span>)}</span>
            <button className="btn" onClick={() => choose(ra.action_type)} disabled={busy}>
              USE MIRAGE'S CHOICE
            </button>
            <span className="dim man__fine">From the same public state you see. Not truth, and not a score.</span>
          </>
        ) : (
          <span className="dim">No recommendation for this state.</span>
        )}
      </aside>
    </div>
  )
}

/** Choices so far, next to what MIRAGE would have done at each step. */
export function ManualLog() {
  const { manualLog } = useSession()
  if (manualLog.length === 0) return null
  const same = manualLog.filter((m) => m.recommended === m.chosen).length
  return (
    <div className="manlog" aria-label="Your choices compared with MIRAGE's recommendations">
      <span className="hdr__label">
        You vs MIRAGE · matched {same} of {manualLog.length}
      </span>
      <ul>
        {manualLog.map((m) => (
          <li key={m.step} className={m.recommended === m.chosen ? 'is-same' : 'is-diff'}>
            <span className="mono">{m.step}</span> you: <b>{actionShort(m.chosen)}</b>
            <span className="dim"> · MIRAGE: {m.recommended ? actionShort(m.recommended) : '—'}</span>
            <span className="manlog__mark mono">{m.recommended === m.chosen ? '=' : '≠'}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
