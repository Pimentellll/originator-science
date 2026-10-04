import { useSession } from '../state/sessionContext'
import { Panel, Sparkline } from './ui'
import { beliefRows, beliefSum, entropySeries } from '../lib/derive'
import type { BeliefRow } from '../lib/derive'
import { fmtDelta, fmtP, MECH_LABEL } from '../lib/format'
import { measurementLabel } from '../lib/actions'
import { MECHANISM_GROUPS } from '../lib/types'
import type { Mechanism } from '../lib/types'

function Row({ r, selected, onSelect }: { r: BeliefRow; selected: boolean; onSelect: () => void }) {
  const d = r.delta
  const dCls = d === null || Math.abs(d) < 0.005 ? '' : d > 0 ? 'is-up' : 'is-down'
  return (
    <li className={`brow brow--${r.status} ${selected ? 'is-selected' : ''}`}>
      <button className="brow__btn" onClick={onSelect} aria-pressed={selected} aria-label={`${MECH_LABEL[r.mechanism]} probability ${fmtP(r.p)}`}>
        <span className="brow__name">
          <i className="brow__dot" aria-hidden />
          {MECH_LABEL[r.mechanism]}
        </span>
        <span className="brow__bar" aria-hidden>
          <span className="brow__mid" />
          <span className="brow__fill" style={{ width: `${r.p * 100}%` }} />
          {r.prev !== null && Math.abs(r.prev - r.p) >= 0.005 && <span className="brow__prev" style={{ left: `${r.prev * 100}%` }} />}
        </span>
        <span className="brow__p mono">{fmtP(r.p)}</span>
        <span className={`brow__d mono ${dCls}`}>{fmtDelta(d)}</span>
      </button>
    </li>
  )
}

export function BeliefPanel() {
  const { frame, prevFrame, frames, cursor, selection, select } = useSession()
  if (!frame) return <Panel index="03" title="Causal belief">{null}</Panel>

  const rows = beliefRows(frame, prevFrame)
  const H = frame.belief.entropy
  const Hprev = prevFrame ? prevFrame.belief.entropy : null
  const series = entropySeries(frames, cursor)
  const sum = beliefSum(frame.belief)
  const sel = (m: Mechanism) => selection === `m:${m}`
  const toggle = (m: Mechanism) => select(sel(m) ? null : `m:${m}`)
  const est = Object.keys(frame.belief.means)

  return (
    <Panel index="03" title="Causal belief" aside={<span className="dim">Δ vs. {prevFrame ? `step ${prevFrame.step}` : '—'}</span>} className="belief">
      <p className="belief__caveat">
        <b>Model posterior, not an empirical biological probability.</b>
      </p>
      <p className="belief__note">
        How strongly the evidence so far implicates each failure mode of <span className="mono">{frame.candidate.id}</span>. <b>Not mutually exclusive</b>: several can be high at once, and rows need not sum to 1.
      </p>

      <div className="belief__axis mono" aria-hidden>
        <span>0</span>
        <span>0.5</span>
        <span>1</span>
      </div>
      {MECHANISM_GROUPS.map((g, gi) => {
        const members = rows.filter((r) => g.members.includes(r.mechanism))
        const loc = frame.belief.localisation?.[g.id]
        return (
          <section key={g.id} className={`bgrp bgrp--${g.id}`} aria-label={`${g.label} failure modes`}>
            <header className="bgrp__hd">
              <span className="bgrp__idx mono">{'ABC'[gi]}</span>
              <span className="bgrp__name">{g.label}</span>
              {g.sub && <span className="bgrp__sub">{g.sub}</span>}
              <span className="bgrp__loc mono" title={loc === undefined ? 'FailureLocalisation is not available from the backend' : 'Group-level failure-localisation probability'}>
                {loc === undefined ? 'group p —' : `group p ${fmtP(loc)}`}
              </span>
            </header>
            <ul className="belief__list">
              {members.map((r) => (
                <Row key={r.mechanism} r={r} selected={sel(r.mechanism)} onSelect={() => toggle(r.mechanism)} />
              ))}
            </ul>
          </section>
        )
      })}
      <p className="belief__loc">
        {frame.belief.localisation ? 'Group probabilities are FailureLocalisation outputs; they are not the sum or maximum of the rows.' : 'Group-level FailureLocalisation: not available from the backend.'}
      </p>

      <div className="belief__legend mono" aria-hidden>
        <span>
          <i className="lg lg--tick" /> previous step
        </span>
        <span>
          <i className="lg lg--dot" /> ≥ 0.5 leading
        </span>
      </div>

      <div className="belief__entropy">
        <div className="belief__ehd">
          <span className="hdr__label">Posterior entropy</span>
          <span className="mono belief__eval">
            {H.toFixed(2)}
            {Hprev !== null && (
              <em className={H < Hprev - 0.005 ? 'is-down' : H > Hprev + 0.005 ? 'is-up' : ''}>
                {' '}
                {H - Hprev > 0 ? '+' : '−'}
                {Math.abs(H - Hprev).toFixed(2)}
              </em>
            )}
          </span>
        </div>
        <Sparkline values={series} max={Math.max(...frames.map((f) => f.belief.entropy), 1)} width={314} height={34} marker={series.length - 1} className="belief__spark" />
        <div className="belief__sum mono">
          Σ p = {sum.toFixed(2)} <span className="faint">· marginals, not a distribution</span>
        </div>
        {frame.belief.ess !== null && (
          <div className="belief__ess2 mono" title="Effective sample size of the posterior approximation (higher means less degenerate). Particle count and inference-validation status are not part of the public state, so they are not shown.">
            ESS <b>{Math.round(frame.belief.ess)}</b> <span className="faint">· posterior approximation health</span>
          </div>
        )}
      </div>

      {est.length > 0 && (
        <div className="belief__est">
          <h3 className="hdr__label">
            Posterior estimates <span className="faint">· mean ± sd</span>
          </h3>
          <ul>
            {est.map((k) => (
              <li key={k}>
                <span>{measurementLabel(k)}</span>
                <span className="mono">
                  {frame.belief.means[k].toFixed(2).replace('-', '−')} <span className="faint">± {Math.sqrt(frame.belief.variances[k] ?? 0).toFixed(2)}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  )
}
