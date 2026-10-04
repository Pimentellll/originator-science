import type { Focus } from '../lib/guided'

const STEPS: { id: Focus; label: string; sel: string }[] = [
  { id: 'candidate', label: 'CANDIDATE', sel: '.cand' },
  { id: 'evidence', label: 'EVIDENCE', sel: '.evid' },
  { id: 'belief', label: 'BELIEF', sel: '.belief' },
  { id: 'action', label: 'ACTION', sel: '.act' },
  { id: 'resources', label: 'RESOURCES', sel: '.res' },
  { id: 'timeline', label: 'TIMELINE', sel: '.tl' },
]

/** The reading order of the cockpit. Clicking a step moves keyboard focus to that panel. */
export function PathStrip({ focus }: { focus: Focus | null }) {
  const go = (sel: string) => {
    const el = document.querySelector<HTMLElement>(sel)
    if (!el) return
    el.setAttribute('tabindex', '-1')
    el.focus({ preventScroll: false })
    el.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }
  return (
    <nav className="path" aria-label="Reading order of the cockpit">
      {STEPS.map((st, i) => (
        <span key={st.id} className="path__item">
          <button className={`path__step ${focus === st.id || (focus === 'justification' && st.id === 'candidate') ? 'is-focus' : ''}`} onClick={() => go(st.sel)}>
            <i className="mono">{i + 1}</i> {st.label}
          </button>
          {i < STEPS.length - 1 && (
            <span className="path__arrow" aria-hidden>
              →
            </span>
          )}
        </span>
      ))}
    </nav>
  )
}
