import { useEffect, useMemo, useState } from 'react'
import { useSession } from '../state/sessionContext'
import type { Route } from '../state/route'
import { ProvenancePill } from '../components/ui'
import { CANONICAL_POLICIES, canonicalPolicyKey } from '../lib/actions'
import { divergenceStep, SPR_DAMAGE } from '../lib/derive'
import { actionLabel, actionShort, formatMeasurement, isPoorQuality, measurementLabel } from '../lib/actions'
import { fmtBudget, fmtNum, fmtSample } from '../lib/format'
import type { CockpitState, EventView, PolicyComparison, PolicyTrack } from '../lib/types'
import { LoadState } from './Cockpit'

const STEP_MS = 1250

/** Contrast pair first, then the baselines. */
function orderTracks(tracks: PolicyTrack[]): PolicyTrack[] {
  // The contrast pair leads (campaign-level, then myopic), then the baselines in canonical order.
  const lead: Record<string, number> = { campaign: 0, mock: 0, myopic: 1 }
  const rank = (t: PolicyTrack) => {
    const i = CANONICAL_POLICIES.findIndex((p) => p.key === canonicalPolicyKey(t.policy.name))
    return (lead[t.policy.family] ?? 2) * 100 + (i < 0 ? 99 : i)
  }
  return [...tracks].sort((a, b) => rank(a) - rank(b))
}

/**
 * The long-horizon thesis is claimed only when the data back it: a real campaign-level lane that
 * ends with a healthier SPR instrument than greedy EIG and is not evaluator-marked unjustified,
 * or the clearly labelled mock lane.
 */
function thesisKind(tracks: PolicyTrack[]): { kind: 'real' | 'mock'; label: string } | null {
  const spr = (t: PolicyTrack) => t.frames[t.frames.length - 1].resources.spr_health
  const greedy = tracks.find((t) => t.policy.family === 'myopic')
  if (!greedy) return null
  const real = tracks.find((t) => {
    const final = t.frames[t.frames.length - 1]
    return (
      t.policy.family === 'campaign' &&
      t.provenance.source !== 'mock' &&
      spr(t) > spr(greedy) &&
      final.terminal?.evaluation?.justified !== false
    )
  })
  if (real) return { kind: 'real', label: real.policy.label }
  const mock = tracks.find((t) => t.policy.family === 'mock')
  if (mock) return { kind: 'mock', label: mock.policy.label }
  return null
}

/** Neutral description of the decision point, derived from the traces. */
function firstActions(tracks: PolicyTrack[]): string {
  const parts = tracks.map((t) => {
    const a = t.frames[0].recommendation?.action_type
    return `${t.policy.label} → ${a ? actionShort(a) : '—'}`
  })
  return `Identical public state at step 1. First actions: ${parts.join(' · ')}.`
}

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
        {ev.cost.budget > 0 && <span className="faint">cost {fmtBudget(ev.cost.budget)}</span>}
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
function Trace({ title, values, max, upTo, cols, fmt, tone, h }: { title: string; values: number[]; max: number; upTo: number; cols: number; fmt: (v: number) => string; tone: 'spr' | 'entropy'; h: number }) {
  const W = cols * 100
  const H = h
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

function Lane({ track, cols, cursor, dp, entropyMax, compact }: { track: PolicyTrack; cols: number; cursor: number; dp: number; entropyMax: number; compact: boolean }) {
  const last = track.frames[track.frames.length - 1]
  const upTo = Math.min(cursor, track.frames.length - 1)
  const done = cursor >= track.frames.length - 1
  const ev = last.terminal?.evaluation
  const verdict = ev ? (ev.terminal_correct === null ? 'abstain' : ev.terminal_correct ? (ev.justified ? 'ok' : 'warn') : ev.justified ? 'warn' : 'bad') : 'none'
  const decision = last.terminal ? `${actionShort(last.terminal.decision)}` : 'NO DECISION'
  const spr = track.frames.map((f) => f.resources.spr_health)
  const ent = track.frames.map((f) => f.belief.entropy)
  const damagedAt = last.events.find((e) => e.spr_delta < -SPR_DAMAGE)
  return (
    <section className={`lane lane--${track.policy.family}`} aria-label={track.policy.label}>
      <header className="lane__hd">
        <h2>{track.policy.label}</h2>
        <ProvenancePill provenance={track.provenance} />
        {track.provenance.source === 'live' && <span className="pill pill--live">LIVE TRACE</span>}
        <p>{track.policy.description}</p>
        <div className="lane__tally mono">{tally({ ...last, events: last.events.slice(0, upTo + 1) })}</div>
        <div className={`lane__stamp lane__stamp--${done ? verdict : 'none'}`}>
          {!done ? 'RUNNING…' : verdict === 'ok' ? '✓ CORRECT · JUSTIFIED' : verdict === 'warn' ? '≈ CORRECT · NOT JUSTIFIED' : verdict === 'bad' ? '✗ INCORRECT · NOT JUSTIFIED' : verdict === 'abstain' ? `ABSTAINED · ${ev?.justified ? 'JUSTIFIED' : 'NOT JUSTIFIED'}` : `${decision} · no evaluator verdict`}
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
        <Trace title="SPR instrument health" values={spr} max={1} upTo={upTo} cols={cols} fmt={(v) => v.toFixed(2)} tone="spr" h={compact ? 34 : 58} />
        <Trace title="Posterior entropy" values={ent} max={entropyMax} upTo={upTo} cols={cols} fmt={(v) => v.toFixed(2)} tone="entropy" h={compact ? 34 : 58} />
      </div>
    </section>
  )
}

function NotRunRow({ policy, reason }: { policy: { label: string }; reason: string }) {
  return (
    <section className="lane lane--notrun" aria-label={`${policy.label}: not run`}>
      <header className="lane__hd lane__hd--nr">
        <h2>{policy.label}</h2>
        <span className="lane__nr mono">NOT RUN</span>
      </header>
      <div className="lane__nrbody">{reason}</div>
    </section>
  )
}

function Scoreboard({ tracks, reveal }: { tracks: PolicyTrack[]; reveal: boolean }) {
  const rows: { label: string; get: (f: CockpitState) => string; num?: (f: CockpitState) => number; better?: 'lower' | 'higher' }[] = [
    { label: 'Terminal decision', get: (f) => (f.terminal ? `${actionShort(f.terminal.decision)} ${f.terminal.candidate_id}` : '—') },
    { label: 'Evaluator verdict', get: (f) => (f.terminal?.evaluation ? (f.terminal.evaluation.terminal_correct === null ? 'abstained' : `${f.terminal.evaluation.terminal_correct ? 'correct' : 'incorrect'} · ${f.terminal.evaluation.justified ? 'justified' : 'not justified'}`) : 'not attached') },
    { label: 'Final SPR health', get: (f) => f.resources.spr_health.toFixed(2), num: (f) => f.resources.spr_health, better: 'higher' },
    { label: 'Cost', get: (f) => fmtBudget(f.resources.budget.total - f.resources.budget.remaining), num: (f) => f.resources.budget.total - f.resources.budget.remaining, better: 'lower' },
    { label: 'Sample used', get: (f) => fmtSample(f.resources.sample.total - f.resources.sample.remaining), num: (f) => f.resources.sample.total - f.resources.sample.remaining, better: 'lower' },
    { label: 'Sim. time', get: (f) => fmtNum(f.resources.time.elapsed), num: (f) => f.resources.time.elapsed, better: 'lower' },
    { label: 'Redesigns', get: (f) => String(f.events.filter((e) => e.kind === 'redesign').length), num: (f) => f.events.filter((e) => e.kind === 'redesign').length, better: 'lower' },
    { label: 'Final posterior entropy', get: (f) => f.belief.entropy.toFixed(2), num: (f) => f.belief.entropy, better: 'lower' },
  ]
  const lasts = tracks.map((t) => t.frames[t.frames.length - 1])
  return (
    <table className={`score ${reveal ? 'is-on' : ''}`}>
      <thead>
        <tr>
          <th />
          {tracks.map((t) => (
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
  const { comparison: cmp, comparisonError } = useSession()
  if (cmp === undefined) return <LoadState what="policy comparison" />
  if (cmp === null && comparisonError)
    return (
      <div className="state" role="alert">
        <b>Policy comparison failed</b>
        <pre>{comparisonError}</pre>
        <span className="faint">This is a failure to produce the comparison, not a NOT RUN result.</span>
        <button className="btn" onClick={() => window.location.reload()}>RETRY</button>
      </div>
    )
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
  const tracks = useMemo(() => orderTracks(cmp.tracks), [cmp])
  const maxStep = useMemo(() => Math.max(...cmp.tracks.map((t) => t.frames.length - 1)), [cmp])
  const [cursor, setCursor] = useState(0)
  const [playing, setPlaying] = useState(true)

  const isPlaying = playing && cursor < maxStep
  useEffect(() => {
    if (!isPlaying) return
    const id = window.setTimeout(() => setCursor((c) => c + 1), cursor === 0 ? 1600 : STEP_MS)
    return () => window.clearTimeout(id)
  }, [isPlaying, cursor])

  const cols = maxStep + 1
  const dp = divergenceStep(tracks)
  const entropyMax = Math.max(...tracks.flatMap((t) => t.frames.map((f) => f.belief.entropy)), 1)
  const finished = cursor >= maxStep
  const thesis = thesisKind(tracks)

  return (
    <div className="cmp">
      <div className="cmp__hero">
        <div className="cmp__thesis">
          {thesis ? (
            <h1>
              <span className="cmp__a">Greedy picks the best next experiment.</span>
              <span className="cmp__b">{thesis.kind === 'real' ? `${thesis.label} picks the better scientific campaign.` : 'A long-horizon policy picks the better scientific campaign.'}</span>
            </h1>
          ) : (
            <h1>
              <span className="cmp__a">Same seeded world.</span>
              <span className="cmp__b">Different scientific campaigns.</span>
            </h1>
          )}
          <p>{cmp.divergence_note ?? firstActions(tracks)}</p>
          {!thesis && <p className="cmp__warn mono">No campaign-level lane protects the instrument better than greedy EIG in these traces, so no long-horizon claim is made.</p>}
          {thesis?.kind === 'mock' && <p className="cmp__warn mono">The long-horizon lane is an authored DEV / MOCK illustration. It is not Lookahead or PPO output.</p>}
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
        {tracks.map((t) => (
          <Lane key={t.policy.name} track={t} cols={cols} cursor={cursor} dp={dp} entropyMax={entropyMax} compact={tracks.length > 2} />
        ))}
        {cmp.not_run.map((n) => (
          <NotRunRow key={n.policy.name} policy={n.policy} reason={n.reason} />
        ))}
      </div>

      <div className="cmp__foot">
        <Scoreboard tracks={tracks} reveal={finished} />
        <p className="cmp__legend">
          Traces and cards are the public replay of each policy on the same seeded world. Verdicts come from the privileged evaluator and are attached to the record only after the terminal decision. <b>EIG</b> = expected information gain (bits) the policy assigned to the action it took.
        </p>
      </div>
    </div>
  )
}
