import { useEffect, useMemo, useState } from 'react'
import { useSession } from '../state/sessionContext'
import type { Route } from '../state/route'
import { ProvenancePill } from '../components/ui'
import { divergenceStep, SPR_DAMAGE } from '../lib/derive'
import { actionLabel, actionShort, formatMeasurement, isPoorQuality, measurementLabel } from '../lib/actions'
import { fmtMoney } from '../lib/format'
import type { CockpitState, EventView, PolicyComparison, PolicyTrack } from '../lib/types'
import { LoadState } from './Cockpit'

const STEP_MS = 1250

/** Compact tally of what a policy actually did, e.g. "SPR ×4 · REDESIGN ×2". */
function tally(frame: CockpitState): string {
  const counts = new Map<string, number>()
  for (const e of frame.events) if (e.action_type) counts.set(actionShort(e.action_type), (counts.get(actionShort(e.action_type)) ?? 0) + 1)
  return [...counts].map(([k, n]) => (n > 1 ? `${k} ×${n}` : k)).join(' · ')
}

function Card({ ev, decisionPoint, hidden, active }: { ev: EventView | undefined; decisionPoint: boolean; hidden: boolean; active: boolean }) {
  if (!ev) return <div className="cc cc--empty" />
  if (hidden) return <div className="cc cc--hidden" aria-hidden />
  const obs = ev.observation
  const damaged = ev.spr_delta < -SPR_DAMAGE
  return (
    <div className={`cc cc--${ev.kind} ${decisionPoint ? 'is-decision' : ''} ${damaged ? 'is-damaged' : ''} ${active ? 'is-active' : ''}`}>
      <div className="cc__top">
        <span className="cc__step mono">{ev.step === 0 ? '0' : `S${ev.step}`}</span>
        {ev.action_type ? <span className="cc__act mono">{actionShort(ev.action_type)}</span> : <span className="cc__act mono">FAILURE</span>}
        {decisionPoint && <span className="cc__dp">DECISION POINT</span>}
      </div>
      <div className="cc__title">{ev.kind === 'failure' ? ev.notes[0] : ev.kind === 'redesign' ? `→ ${ev.result_candidate_id}` : ev.kind === 'decision' ? `${actionLabel(ev.action_type!)} ${ev.candidate_id}` : ev.candidate_id}</div>
      {obs && (
        <div className="cc__meas mono">
          {obs.measurements.map((m) => (
            <span key={m.name}>
              <span className="faint">{measurementLabel(m.name)}</span> {formatMeasurement(m.name, m.value)}
            </span>
          ))}
          <span className={`cc__q ${isPoorQuality(obs.quality) ? 'is-poor' : ''}`}>{obs.quality}</span>
        </div>
      )}
      <div className="cc__foot mono">
        {ev.decision?.eig !== undefined && <span className="cc__eig">EIG {ev.decision.eig.toFixed(2)}</span>}
        {ev.cost.budget > 0 && <span className="faint">{fmtMoney(ev.cost.budget)}</span>}
        {damaged && (
          <span className="cc__dmg">
            SPR {(ev.resources_before?.spr_health ?? 1).toFixed(2)} → {ev.resources_after.spr_health.toFixed(2)}
          </span>
        )}
      </div>
    </div>
  )
}

/** One polyline across the shared step columns. */
function Trace({ title, values, max, upTo, cols, fmt, tone }: { title: string; values: number[]; max: number; upTo: number; cols: number; fmt: (v: number) => string; tone: 'spr' | 'entropy' }) {
  const W = cols * 100
  const H = 58
  const y = (v: number) => H - 4 - (Math.min(v, max) / max) * (H - 10)
  const pts = values.slice(0, upTo + 1).map((v, i) => [i * 100 + 50, y(v)] as const)
  const last = pts[pts.length - 1]
  return (
    <div className="tr">
      <span className="tr__t hdr__label">{title}</span>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className={`tr__svg tr__svg--${tone}`} role="img" aria-label={title}>
        {Array.from({ length: cols }, (_, i) => (
          <line key={i} x1={i * 100} x2={i * 100} y1={0} y2={H} className="tr__grid" />
        ))}
        <line x1="0" x2={W} y1={H - 4} y2={H - 4} className="tr__base" />
        {pts.length > 1 && <polyline points={pts.map((p) => p.join(',')).join(' ')} className="tr__line" vectorEffect="non-scaling-stroke" />}
        {last && <circle cx={last[0]} cy={last[1]} r="4" className="tr__dot" vectorEffect="non-scaling-stroke" />}
      </svg>
      {last && <span className="tr__v mono">{fmt(values[Math.min(upTo, values.length - 1)])}</span>}
    </div>
  )
}

function Lane({ track, cols, cursor, dp, entropyMax }: { track: PolicyTrack; cols: number; cursor: number; dp: number; entropyMax: number }) {
  const last = track.frames[track.frames.length - 1]
  const upTo = Math.min(cursor, track.frames.length - 1)
  const done = cursor >= track.frames.length - 1
  const ev = last.terminal?.evaluation
  const verdict = ev ? (ev.terminal_correct ? (ev.justified ? 'ok' : 'warn') : 'bad') : 'none'
  const spr = track.frames.map((f) => f.resources.spr_health)
  const ent = track.frames.map((f) => f.belief.entropy)
  const damagedAt = last.events.find((e) => e.spr_delta < -SPR_DAMAGE)
  return (
    <section className={`lane lane--${track.policy.name === 'GreedyEIGPolicy' ? 'greedy' : 'mirage'}`} aria-label={track.policy.label}>
      <header className="lane__hd">
        <h2>{track.policy.label}</h2>
        <p>{track.policy.description}</p>
        <div className="lane__tally mono">{tally({ ...last, events: last.events.slice(0, upTo + 1) })}</div>
        <div className={`lane__stamp lane__stamp--${done ? verdict : 'none'}`}>
          {!done ? 'RUNNING…' : verdict === 'ok' ? '✓ CORRECT · JUSTIFIED' : verdict === 'warn' ? '≈ CORRECT · NOT JUSTIFIED' : verdict === 'bad' ? '✗ INCORRECT' : 'NO VERDICT ATTACHED'}
        </div>
        {done && damagedAt && <div className="lane__note">SPR instrument damaged at step {damagedAt.step}</div>}
        {done && !damagedAt && <div className="lane__note lane__note--good">SPR instrument preserved</div>}
      </header>
      <div className="lane__body">
        <div className="lane__cards" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
          {Array.from({ length: cols }, (_, i) => (
            <Card key={i} ev={last.events[i]} decisionPoint={i === dp + 1 && dp >= 0} hidden={i > cursor && i < last.events.length} active={i === cursor} />
          ))}
        </div>
        <Trace title="SPR instrument health" values={spr} max={1} upTo={upTo} cols={cols} fmt={(v) => v.toFixed(2)} tone="spr" />
        <Trace title="Posterior entropy" values={ent} max={entropyMax} upTo={upTo} cols={cols} fmt={(v) => v.toFixed(2)} tone="entropy" />
      </div>
    </section>
  )
}

function Scoreboard({ cmp, reveal }: { cmp: PolicyComparison; reveal: boolean }) {
  const rows: { label: string; get: (f: CockpitState) => string; num?: (f: CockpitState) => number; better?: 'lower' | 'higher' }[] = [
    { label: 'Terminal decision', get: (f) => (f.terminal ? `${actionShort(f.terminal.decision)} ${f.terminal.candidate_id}` : '—') },
    { label: 'Evaluator verdict', get: (f) => (f.terminal?.evaluation ? (f.terminal.evaluation.terminal_correct ? (f.terminal.evaluation.justified ? 'correct · justified' : 'correct · not justified') : 'incorrect') : 'not attached') },
    { label: 'Final SPR health', get: (f) => f.resources.spr_health.toFixed(2), num: (f) => f.resources.spr_health, better: 'higher' },
    { label: 'Cost', get: (f) => fmtMoney(f.resources.budget.total - f.resources.budget.remaining), num: (f) => f.resources.budget.total - f.resources.budget.remaining, better: 'lower' },
    { label: 'Sample used', get: (f) => `${f.resources.sample.total - f.resources.sample.remaining} µg`, num: (f) => f.resources.sample.total - f.resources.sample.remaining, better: 'lower' },
    { label: 'Sim. time', get: (f) => `${Math.round(f.resources.time.elapsed)} h`, num: (f) => f.resources.time.elapsed, better: 'lower' },
    { label: 'Redesigns', get: (f) => String(f.events.filter((e) => e.kind === 'redesign').length), num: (f) => f.events.filter((e) => e.kind === 'redesign').length, better: 'lower' },
    { label: 'Final posterior entropy', get: (f) => f.belief.entropy.toFixed(2), num: (f) => f.belief.entropy, better: 'lower' },
  ]
  const lasts = cmp.tracks.map((t) => t.frames[t.frames.length - 1])
  return (
    <table className={`score ${reveal ? 'is-on' : ''}`}>
      <thead>
        <tr>
          <th />
          {cmp.tracks.map((t) => (
            <th key={t.policy.name}>{t.policy.label}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const nums = r.num ? lasts.map(r.num) : []
          const best = r.num && r.better ? (r.better === 'lower' ? Math.min(...nums) : Math.max(...nums)) : null
          const allEqual = nums.length > 0 && nums.every((n) => n === nums[0])
          return (
            <tr key={r.label}>
              <td className="hdr__label">{r.label}</td>
              {lasts.map((f, i) => (
                <td key={i} className={`mono ${best !== null && !allEqual && nums[i] === best ? 'is-best' : ''}`}>
                  {r.get(f)}
                </td>
              ))}
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

export function ComparePolicies({ navigate }: { navigate: (r: Route) => void }) {
  const cmp = useSession().comparison
  if (cmp === undefined) return <LoadState what="policy comparison" />
  if (cmp === null)
    return (
      <div className="state" role="status">
        <b>NOT RUN</b>
        <span>No policy comparison exists for this scenario.</span>
        <span className="faint">A comparison needs two or more policies run on the identical seeded world.</span>
        <button className="btn" onClick={() => navigate('cockpit')}>BACK TO COCKPIT</button>
      </div>
    )
  // Remount per scenario so playback restarts from the failure.
  return <CompareView key={cmp.scenario.id} cmp={cmp} navigate={navigate} />
}

function CompareView({ cmp, navigate }: { cmp: PolicyComparison; navigate: (r: Route) => void }) {
  const maxStep = useMemo(() => (cmp ? Math.max(...cmp.tracks.map((t) => t.frames.length - 1)) : 0), [cmp])
  const [cursor, setCursor] = useState(0)
  const [playing, setPlaying] = useState(true)

  const isPlaying = playing && cursor < maxStep
  useEffect(() => {
    if (!isPlaying) return
    const id = window.setTimeout(() => setCursor((c) => c + 1), cursor === 0 ? 1600 : STEP_MS)
    return () => window.clearTimeout(id)
  }, [isPlaying, cursor])

  const cols = maxStep + 1
  const dp = divergenceStep(cmp.tracks)
  const entropyMax = Math.max(...cmp.tracks.flatMap((t) => t.frames.map((f) => f.belief.entropy)), 1)
  const finished = cursor >= maxStep

  return (
    <div className="cmp">
      <div className="cmp__hero">
        <div className="cmp__thesis">
          <h1>
            <span className="cmp__a">Greedy picks the best next experiment.</span>
            <span className="cmp__b">MIRAGE picks the better scientific campaign.</span>
          </h1>
          <p>
            {cmp.divergence_note ?? (dp >= 0 ? `The policies share the same public state until step ${dp + 1}, then choose different actions.` : 'The policies chose the same first action.')}
          </p>
        </div>
        <div className="cmp__ctl">
          <div className="cmp__meta mono">
            <span>seed {cmp.seed}</span>
            <span className="faint">identical seeded world</span>
            <ProvenancePill provenance={cmp.provenance} />
          </div>
          <div className="cmp__btns">
            <button
              className="btn btn--primary"
              onClick={() => {
                if (finished) {
                  setCursor(0)
                  setPlaying(true)
                } else setPlaying((p) => !p)
              }}
            >
              {finished ? '↺ REPLAY' : isPlaying ? '❚❚ PAUSE' : '▶ PLAY'}
            </button>
            <button className="btn" onClick={() => { setPlaying(false); setCursor(maxStep) }} disabled={finished}>
              SHOW ALL
            </button>
            <button className="btn" onClick={() => navigate('cockpit')}>
              OPEN COCKPIT
            </button>
          </div>
          <input
            className="cmp__scrub"
            type="range"
            min={0}
            max={maxStep}
            value={cursor}
            aria-label="Campaign step"
            onChange={(e) => {
              setPlaying(false)
              setCursor(+e.target.value)
            }}
          />
        </div>
      </div>

      <div className="cmp__axis mono" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }} aria-hidden>
        {Array.from({ length: cols }, (_, i) => (
          <span key={i} className={i === cursor ? 'is-now' : i === dp + 1 ? 'is-dp' : ''}>
            {i === 0 ? 'FAILURE' : `STEP ${i}`}
          </span>
        ))}
      </div>

      <div className="cmp__lanes">
        {dp >= 0 && <div className="cmp__dpline" style={{ left: `calc(var(--lane-x) + (100% - var(--lane-x)) * ${(dp + 1) / cols})` }} aria-hidden />}
        {cmp.tracks.map((t) => (
          <Lane key={t.policy.name} track={t} cols={cols} cursor={cursor} dp={dp} entropyMax={entropyMax} />
        ))}
      </div>

      <div className="cmp__foot">
        <Scoreboard cmp={cmp} reveal={finished} />
        <p className="cmp__legend">
          Traces and cards are the public replay of each policy on the same seeded world. Verdicts come from the privileged evaluator and are attached to the record only after the terminal decision. <b>EIG</b> = expected information gain (bits) the policy assigned to the action it took.
        </p>
      </div>
    </div>
  )
}
