import { useMemo, useState } from 'react'
import { useSession } from '../state/sessionContext'
import type { Route } from '../state/route'
import { Modal, Panel } from './ui'
import { fmtBits, fmtHours, fmtMoney, MECH_LABEL, pct } from '../lib/format'
import type { AlternativeView, CockpitState, Recommendation } from '../lib/types'
import { actionKind, actionLabel, actionShort } from '../lib/actions'
import { counterfactualFor } from '../lib/derive'

function Stat({ label, children, sub }: { label: string; children: React.ReactNode; sub?: string }) {
  return (
    <div className="astat">
      <span className="hdr__label">{label}</span>
      <b className="mono">{children}</b>
      {sub && <small className="mono">{sub}</small>}
    </div>
  )
}

const yn = (v: boolean | null | undefined) => (v === null || v === undefined ? 'n/a' : v ? 'yes' : 'no')

function Terminal({ frame }: { frame: CockpitState }) {
  const t = frame.terminal!
  const ev = t.evaluation
  const spent = frame.resources.budget.total - frame.resources.budget.remaining
  const used = frame.resources.sample.total - frame.resources.sample.remaining
  const redesigns = frame.events.filter((e) => e.kind === 'redesign').length
  return (
    <div className="aterm">
      <div className="aterm__head">
        <span className="hdr__label">Episode complete</span>
        <span className="pill pill--warn">
          {actionShort(t.decision)} {t.candidate_id}
        </span>
        {ev && (
          <>
            <span className={`pill ${ev.terminal_correct ? 'pill--ok' : 'pill--bad'}`}>{ev.terminal_correct ? 'CORRECT' : 'INCORRECT'}</span>
            <span className={`pill ${ev.justified ? 'pill--ok' : 'pill--bad'}`}>{ev.justified ? 'JUSTIFIED' : 'NOT JUSTIFIED'}</span>
          </>
        )}
        <span className="dim">{ev ? 'Verdict from the privileged evaluator, shown after the decision.' : 'No evaluator verdict attached to this record.'}</span>
      </div>
      <div className="aterm__grid">
        <Stat label="Actions">{frame.events.length - 1}</Stat>
        <Stat label="Cost">{fmtMoney(spent)}</Stat>
        <Stat label="Sample used">{used} µg</Stat>
        <Stat label="Sim. time">{Math.round(frame.resources.time.elapsed)} h</Stat>
        <Stat label="Redesigns">{redesigns}</Stat>
        <Stat label="SPR health">{frame.resources.spr_health.toFixed(2)}</Stat>
        <Stat label="Unnecessary redesigns">{ev?.unnecessary_redesigns ?? 'n/a'}</Stat>
        <Stat label="Compound recognised">{yn(ev?.compound_recognised)}</Stat>
        <Stat label="Assay invalid detected">{yn(ev?.assay_invalid_detected)}</Stat>
      </div>
    </div>
  )
}

function WhyDialog({ frame, ra, onClose }: { frame: CockpitState; ra: Recommendation; onClose: () => void }) {
  const alts: (AlternativeView & { chosen?: boolean })[] = [
    { action_type: ra.action_type, candidate_id: ra.candidate_id, score: ra.score, eig: ra.eig, cost: ra.cost, why_not: '', chosen: true },
    ...ra.alternatives,
  ].sort((a, b) => (b.score ?? -1) - (a.score ?? -1))
  const max = Math.max(...alts.map((a) => a.score ?? 0), 0.01)
  return (
    <Modal title={`WHY ${actionLabel(ra.action_type).toUpperCase()}?`} onClose={onClose} badge={<span className="pill">{frame.policy.label}</span>}>
      {ra.rationale ? <p className="why__rationale">{ra.rationale}</p> : <p className="dim">The policy supplied no public rationale for this step.</p>}
      <div className="why__meta">
        <div>
          <span className="hdr__label">Precondition / risk</span>
          <p>{ra.risk ?? '—'}</p>
        </div>
        <div>
          <span className="hdr__label">Discriminates between</span>
          <p className="why__chips">{ra.discriminates.length ? ra.discriminates.map((m) => <span key={m} className="chip">{MECH_LABEL[m]}</span>) : <span className="dim">nothing: ends the episode</span>}</p>
        </div>
      </div>
      <span className="hdr__label">Ranked by policy score · why the others were passed over</span>
      <table className="why__tbl">
        <thead>
          <tr>
            <th>#</th>
            <th>Action</th>
            <th>Policy score</th>
            <th>EIG</th>
            <th>Cost</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {alts.map((a, i) => (
            <tr key={a.action_type} className={a.chosen ? 'is-chosen' : ''}>
              <td className="mono">{i + 1}</td>
              <td>
                {actionLabel(a.action_type)} {a.chosen && <span className="chip chip--accent">CHOSEN</span>}
              </td>
              <td>
                {a.score !== undefined ? (
                  <>
                    <span className="why__bar">
                      <span style={{ width: `${(a.score / max) * 100}%` }} />
                    </span>
                    <span className="mono">{a.score.toFixed(2)}</span>
                  </>
                ) : (
                  '—'
                )}
              </td>
              <td className="mono">{fmtBits(a.eig)}</td>
              <td className="mono">{a.cost?.budget !== undefined ? fmtMoney(a.cost.budget) : '—'}</td>
              <td className="why__why">{a.chosen ? ra.rationale?.split('. ')[0] : a.why_not}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Modal>
  )
}

function CounterfactualDialog({ onClose }: { onClose: () => void }) {
  const s = useSession()
  const frame = s.frame!
  const cf = useMemo(() => counterfactualFor(s.comparison ?? null, frame.policy.name, frame.step), [s.comparison, frame])
  const modeCost = cf?.firstEffect.cost
  return (
    <Modal title={`COUNTERFACTUAL · STEP ${frame.step}`} onClose={onClose} badge={<span className="pill pill--simulated">SIMULATED BRANCH</span>}>
      {s.comparison === undefined && <p className="dim">Loading identical-seed comparison…</p>}
      {s.comparison !== undefined && !cf && (
        <p className="dim">
          NOT AVAILABLE. A counterfactual is shown only where another policy ran this exact seeded world and chose a different action from this same state.
          {s.comparison === null ? ' No policy comparison has been run for this scenario.' : ' The policies do not diverge at this step.'}
        </p>
      )}
      {cf && (
        <>
          <div className="cf__vs">
            <div className="cf__side">
              <span className="hdr__label">{cf.chosen.policy} chose</span>
              <b>{actionLabel(cf.chosen.action)}</b>
            </div>
            <span className="mono faint">vs</span>
            <div className="cf__side cf__side--alt">
              <span className="hdr__label">{cf.alternative.policy} chose</span>
              <b>{cf.alternative.label}</b>
              {modeCost && (
                <span className="mono dim">
                  {fmtMoney(modeCost.budget)} · {modeCost.sample} µg · {fmtHours(modeCost.time)}
                </span>
              )}
            </div>
          </div>
          <p className="cf__headline">Same seeded world, same history, different next action. What that branch did, from its public trace:</p>
          <ul className="cf__list">
            {cf.consequences.map((c, i) => (
              <li key={i} className={`cf--${c.severity}`}>
                <span className="cf__kind mono">{c.kind.toUpperCase()}</span>
                <span>{c.text}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Modal>
  )
}

export function ActionPanel({ navigate }: { navigate: (r: Route) => void }) {
  const s = useSession()
  const { frame } = s
  const [why, setWhy] = useState(false)
  const [cf, setCf] = useState(false)

  if (!frame) return <Panel index="04" title="Next action">{null}</Panel>
  const ra = frame.recommendation
  const terminal = frame.status === 'terminal'
  const running = s.phase === 'running'
  const histStep = s.session?.mode === 'replay' && s.cursor < s.frames.length - 1
  const kind = ra ? actionKind(ra.action_type) : 'measurement'

  return (
    <Panel
      index="04"
      title="Next action"
      className="act"
      aside={
        <>
          <span className="dim">{frame.policy.label}</span>
          {histStep && (
            <span className="pill">
              STEP {frame.step} OF {s.frames.length - 1}
            </span>
          )}
        </>
      }
    >
      {terminal && frame.terminal ? (
        <Terminal frame={frame} />
      ) : ra ? (
        <div className="act__grid">
          <div className="act__main">
            <div className="act__head">
              <span className={`act__kind act__kind--${kind}`}>{actionShort(ra.action_type)}</span>
              <h2 className="act__title">
                {actionLabel(ra.action_type)} <span className="mono dim act__cand">{ra.candidate_id}</span>
              </h2>
              <span className="act__disc">{ra.discriminates.map((m) => <span key={m} className="chip">{MECH_LABEL[m]}</span>)}</span>
            </div>
            <div className="act__stats">
              <Stat label="Policy score">{ra.score !== undefined ? ra.score.toFixed(2) : '—'}</Stat>
              <div className="astat">
                <span className="hdr__label">Confidence</span>
                <b className="mono">{ra.confidence !== undefined ? pct(ra.confidence) : '—'}</b>
                {ra.confidence !== undefined && (
                  <span className="astat__bar">
                    <span style={{ width: pct(ra.confidence) }} />
                  </span>
                )}
              </div>
              <Stat label="Expected info">{fmtBits(ra.eig)}</Stat>
              <Stat label="Cost" sub={ra.cost?.budget !== undefined ? `${((ra.cost.budget / frame.resources.budget.total) * 100).toFixed(1)}% of budget` : undefined}>
                {ra.cost?.budget !== undefined ? fmtMoney(ra.cost.budget) : '—'}
              </Stat>
              <Stat label="Sample">{ra.cost?.sample !== undefined ? `${ra.cost.sample} µg` : '—'}</Stat>
              <Stat label="Time">{ra.cost?.time !== undefined ? fmtHours(ra.cost.time) : '—'}</Stat>
            </div>
            <div className="act__text">
              <div>
                <span className="hdr__label">Scientific rationale</span>
                <p>{ra.rationale ?? 'No public rationale supplied.'}</p>
              </div>
              <div>
                <span className="hdr__label">Risk / precondition</span>
                <p className="dim">{ra.risk ?? '—'}</p>
              </div>
            </div>
          </div>
          <div className="act__ctl">
            <button className="btn btn--primary" onClick={s.run} disabled={!s.canRun || running}>
              {running ? 'RUNNING…' : '▶ RUN'}
            </button>
            <button className="btn" onClick={() => setWhy(true)}>
              WHY?
            </button>
            <button className="btn" onClick={() => navigate('compare')}>
              COMPARE POLICIES
            </button>
            <button className="btn" onClick={() => setCf(true)}>
              SHOW COUNTERFACTUAL
            </button>
          </div>
        </div>
      ) : (
        <p className="dim" style={{ padding: 16 }}>
          The policy has not supplied a recommendation for this state.
        </p>
      )}

      {why && ra && <WhyDialog frame={frame} ra={ra} onClose={() => setWhy(false)} />}
      {cf && <CounterfactualDialog onClose={() => setCf(false)} />}
    </Panel>
  )
}
