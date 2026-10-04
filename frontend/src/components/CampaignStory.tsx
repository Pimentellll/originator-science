import { useEffect, useMemo } from 'react'
import { DRAWERS } from '../lib/drawers'
import type { DrawerId } from '../lib/drawers'
import { useSession } from '../state/sessionContext'
import type { Route } from '../state/route'
import { buildBeats } from '../lib/guided'
import { beatsAt, groupHeadline, headline, narrate, stageOf, STAGES, topBeliefs } from '../lib/story'
import { actionLabel } from '../lib/actions'
import { fmtBudget, fmtP, fmtSample, MECH_LABEL } from '../lib/format'
import { Meter } from './ui'
import { VerdictBanner } from './Verdict'
import { ManualControls, ManualLog } from './ManualControls'
import { GuidedCoach } from './GuidedCoach'
import { CandidatePanel } from './CandidatePanel'
import { JustificationPanel } from './JustificationPanel'
import { EvidenceGraph } from './EvidenceGraph'
import { BeliefPanel } from './BeliefPanel'
import { ActionPanel } from './ActionPanel'
import { ResourcePanel } from './ResourcePanel'
import { Timeline } from './Timeline'

const noop = () => {}

function Drawer({ id, onClose, navigate }: { id: DrawerId; onClose: () => void; navigate: (r: Route) => void }) {
  useEffect(() => {
    const on = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', on)
    return () => window.removeEventListener('keydown', on)
  }, [onClose])
  const d = DRAWERS.find((x) => x.id === id)!
  return (
    <aside className="drawer" role="dialog" aria-label={d.title}>
      <header className="drawer__hd">
        <div>
          <h2>{d.title}</h2>
          <p>{d.hint}</p>
        </div>
        <button className="btn btn--ghost" onClick={onClose} aria-label="Close panel">
          ✕ Close
        </button>
      </header>
      <div className={`drawer__body drawer__body--${id}`}>
        {id === 'evidence' && <EvidenceGraph />}
        {id === 'timeline' && <Timeline />}
        {id === 'belief' && <BeliefPanel />}
        {id === 'action' && <ActionPanel navigate={navigate} />}
        {id === 'candidate' && (
          <>
            <CandidatePanel />
            <JustificationPanel />
          </>
        )}
        {id === 'resources' && <ResourcePanel />}
      </div>
    </aside>
  )
}

function NextStep({ navigate, openDrawer }: { navigate: (r: Route) => void; openDrawer: (d: DrawerId) => void }) {
  const s = useSession()
  const f = s.frame!
  const last = s.frames.length - 1
  if (f.status === 'terminal' && f.terminal)
    return (
      <section className="story__card story__card--verdict" aria-label="Verdict">
        <span className="story__kick">Verdict</span>
        <VerdictBanner evaluation={f.terminal.evaluation} decision={f.terminal.decision} />
        <div className="story__row">
          <button className="btn btn--primary" onClick={() => navigate('launch')}>
            Start another campaign
          </button>
          <button className="btn" onClick={() => openDrawer('candidate')}>
            See the justification
          </button>
        </div>
      </section>
    )
  if (!s.atEnd)
    return (
      <section className="story__card story__next" aria-label="Replay">
        <div>
          <span className="story__kick">Looking back</span>
          <b className="story__act">
            Step {s.cursor} of {last}
          </b>
          <span className="story__why">Step forward to see what MIRAGE did next.</span>
        </div>
        <div className="story__row">
          <button className="btn btn--primary" onClick={s.run} disabled={!s.canRun}>
            Next step ▸
          </button>
          <button className="btn btn--ghost" onClick={() => s.seek(last)}>
            Jump to latest
          </button>
        </div>
      </section>
    )
  if (s.launch.control === 'manual')
    return (
      <section className="story__card story__card--manual" aria-label="Your move">
        <span className="story__kick">Your move · you choose, MIRAGE only recommends</span>
        <ManualControls />
      </section>
    )
  const rec = f.recommendation
  if (!rec) return null
  const why = rec.rationale ?? (rec.discriminates.length ? `Tells apart ${rec.discriminates.map((m) => MECH_LABEL[m].toLowerCase()).join(' and ')}.` : null)
  const cost = rec.cost?.budget
  return (
    <section className="story__card story__next" aria-label="Next experiment">
      <div>
        <span className="story__kick">Next experiment</span>
        <b className="story__act">{actionLabel(rec.action_type)}</b>
        <span className="story__why">
          {why}
          {cost !== undefined && ` Costs ${fmtBudget(cost)} of the ${fmtBudget(f.resources.budget.remaining)} budget units left.`}
        </span>
      </div>
      <button className="btn btn--primary story__run" onClick={s.run} disabled={!s.canRun}>
        {s.phase === 'running' ? 'Running…' : 'Run it ▸'}
      </button>
    </section>
  )
}

/**
 * The progressive-disclosure cockpit: what is happening now, why, and the one thing to do next.
 * Every other panel stays one click away in a side drawer.
 */
export function CampaignStory({ navigate, drawer, setDrawer }: { navigate: (r: Route) => void; drawer: DrawerId | null; setDrawer: (d: DrawerId | null) => void }) {
  const s = useSession()
  const beats = useMemo(() => buildBeats(s.frames), [s.frames])
  const f = s.frame!
  const group = beatsAt(beats, s.cursor)
  const current = group.at(-1)
  const stage = stageOf(current)
  const { lead, more } = narrate(group)
  const guided = s.launch.guided && s.transport.kind === 'live'
  const history = beats.filter((b) => b.cursor < (current?.cursor ?? 0) && b.kind !== 'update')
  const top = topBeliefs(f, s.prevFrame, 3)
  const r = f.resources
  const close = useMemo(() => () => setDrawer(null), [setDrawer])

  return (
    <div className={`story ${drawer ? 'has-drawer' : ''}`}>
      <ol className="story__steps" aria-label="Where the campaign is">
        {STAGES.map((label, i) => (
          <li key={label} className={i < stage ? 'is-done' : i === stage ? 'is-now' : ''} aria-current={i === stage ? 'step' : undefined}>
            <i className="mono">{i + 1}</i> {label}
          </li>
        ))}
      </ol>

      <div className="story__grid">
        <section className="story__now" aria-live="polite">
          {guided ? (
            <GuidedCoach key={s.session?.session_id} onFocus={noop} />
          ) : (
            <>
              <div className="story__kick">
                Step {s.cursor}
                {f.total_steps !== null ? ` of ${f.total_steps}` : ''} · {STAGES[stage]}
              </div>
              <h1 className="story__h">{groupHeadline(group)}</h1>
              {lead.map((l, i) => (
                <p key={i} className="story__lead">
                  {l}
                </p>
              ))}
              {more.length > 0 && (
                <details className="story__more">
                  <summary>More detail</summary>
                  {more.map((l, i) => (
                    <p key={i}>{l}</p>
                  ))}
                </details>
              )}
              <NextStep navigate={navigate} openDrawer={setDrawer} />
            </>
          )}

          <div className="story__links">
            <button className="linkbtn" onClick={() => setDrawer('evidence')}>
              See the evidence
            </button>
            {f.recommendation && f.status !== 'terminal' && (
              <button className="linkbtn" onClick={() => setDrawer('action')}>
                Why this test?
              </button>
            )}
            <button className="linkbtn" onClick={() => setDrawer('timeline')}>
              Timeline
            </button>
          </div>

          {!guided && history.length > 0 && (
            <details className="story__history">
              <summary>
                What happened so far · {history.length} step
                {history.length === 1 ? '' : 's'}
              </summary>
              <ol>
                {history.map((b) => (
                  <li key={b.id}>
                    <button className="linkbtn" onClick={() => s.seek(b.cursor)}>
                      <span className="mono">{b.cursor}</span> {headline(b)}
                    </button>
                  </li>
                ))}
              </ol>
            </details>
          )}
          {s.launch.control === 'manual' && <ManualLog />}
        </section>

        <aside className="story__side" aria-label="At a glance">
          <h3>What MIRAGE believes now</h3>
          <ul className="story__beliefs">
            {top.map((row) => (
              <li key={row.mechanism}>
                <span>{MECH_LABEL[row.mechanism]}</span>
                <i aria-hidden>
                  <b style={{ width: `${row.p * 100}%` }} />
                </i>
                <span className="mono">{fmtP(row.p)}</span>
              </li>
            ))}
          </ul>
          <p className="story__fine">The model's belief in each explanation, not a measured probability.</p>
          <button className="linkbtn" onClick={() => setDrawer('belief')}>
            Show all {Object.keys(f.belief.p).length} explanations ▸
          </button>

          <h3>Budget</h3>
          <Meter
            label="Budget used"
            value={
              <>
                {fmtBudget(r.budget.total - r.budget.remaining)} <small>/ {fmtBudget(r.budget.total)}</small>
              </>
            }
            fraction={(r.budget.total - r.budget.remaining) / r.budget.total}
            tone={r.budget.remaining / r.budget.total < 0.15 ? 'warn' : 'default'}
          />
          <Meter
            label="Sample used"
            value={
              <>
                {fmtSample(r.sample.total - r.sample.remaining)} <small>/ {fmtSample(r.sample.total)}</small>
              </>
            }
            fraction={(r.sample.total - r.sample.remaining) / r.sample.total}
          />
          <button className="linkbtn" onClick={() => setDrawer('resources')}>
            Instrument health and details ▸
          </button>
        </aside>

        <nav className="story__tabs" aria-label="More panels">
          {DRAWERS.map((d) => (
            <button key={d.id} className="story__tab" aria-pressed={drawer === d.id} title={d.hint} onClick={() => setDrawer(drawer === d.id ? null : d.id)}>
              {d.label}
            </button>
          ))}
        </nav>
      </div>

      {drawer && <Drawer id={drawer} onClose={close} navigate={navigate} />}
    </div>
  )
}
