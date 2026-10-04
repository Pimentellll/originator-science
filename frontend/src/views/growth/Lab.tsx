import { useState } from 'react'
import { Diamonds, Dots, HLine, Line, Plot } from '../../components/figures/Plot'
import { INK } from '../../components/figures/ink'
import { hypothesisFor } from '../../lib/growth/analysis'
import type { AutoplayResult, DiagnosisLabel, MeasureResult, Reading, SandboxVerdict, SubmitSuccess } from '../../lib/growth/types'
import { CONDITION_LABEL, DIAG_LABEL, agentMeta, fmt } from './agents'
import { growthClient } from './data'
import { Check, MetaBar } from './parts'

const DILUTIONS = [1, 2, 5, 10, 20, 50, 100]
const CULTURES = [
  { id: 'demo-BP', label: 'Culture A', note: 'matched demo pair' },
  { id: 'demo-MA', label: 'Culture B', note: 'matched demo pair' },
  { id: 'random', label: 'New culture', note: 'sampled from the scenario prior' },
] as const
type CultureId = (typeof CULTURES)[number]['id']

type Session = {
  id: string
  culture: CultureId
  passive: Reading[]
  budget: number
  total: number
  measurements: (MeasureResult & { turn: number; replicatesAsked: number })[]
}

export function Lab() {
  const sandbox = growthClient().sandbox
  const [session, setSession] = useState<Session | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [time, setTime] = useState(18)
  const [dilution, setDilution] = useState(10)
  const [reps, setReps] = useState(2)
  const [dx, setDx] = useState<DiagnosisLabel | null>(null)
  const [p, setP] = useState(0.5)
  const [estimate, setEstimate] = useState('')
  const [rationale, setRationale] = useState('')
  const [submitted, setSubmitted] = useState<SubmitSuccess | null>(null)
  const [verdict, setVerdict] = useState<SandboxVerdict | null>(null)
  const [verdictError, setVerdictError] = useState<string | null>(null)
  const [auto, setAuto] = useState<Record<string, AutoplayResult>>({})

  if (!sandbox) {
    return (
      <div className="doc">
        <div className="doc__wrap doc__state">
          <p>The Lab runs the virtual experiment on the MIRAGE API, so it is not available in the offline static build.</p>
          <p>
            Start the API with <span className="mono">--growth-results experiments/results</span> and open the app without <span className="mono">?growth=static</span>.
          </p>
        </div>
      </div>
    )
  }

  const run = async <T,>(label: string, f: () => Promise<T>): Promise<T | null> => {
    setBusy(label)
    setError(null)
    try {
      return await f()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      return null
    } finally {
      setBusy(null)
    }
  }

  const start = async (culture: CultureId) => {
    const created = await run('start', () => sandbox.create(culture === 'random' ? {} : { preset: culture }))
    if (!created) return
    setSession({
      id: created.session_id,
      culture,
      passive: created.observation.passive_readings,
      budget: created.observation.budget_remaining,
      total: created.observation.budget_total,
      measurements: [],
    })
    setSubmitted(null)
    setVerdict(null)
    setVerdictError(null)
    setAuto({})
    setDx(null)
    setP(0.5)
    setEstimate('')
    setRationale('')
  }

  const measure = async () => {
    if (!session) return
    const res = await run('measure', () => sandbox.measure(session.id, { time_h: time, dilution_factor: dilution, replicates: reps }))
    if (!res) return
    if (!res.ok || !res.result) {
      setError(res.error ?? 'measurement rejected')
      return
    }
    const r = res.result
    setSession({ ...session, budget: r.budget_remaining, measurements: [...session.measurements, { ...r, turn: session.measurements.length + 1, replicatesAsked: reps }] })
  }

  const diagnose = async () => {
    if (!session || !dx) return
    const est = estimate.trim() === '' ? null : Number(estimate)
    if (est !== null && !(Number.isFinite(est) && est > 0)) {
      setError('The late biomass estimate must be a positive number, or left blank.')
      return
    }
    const res = await run('diagnose', () => sandbox.diagnose(session.id, { diagnosis: dx, p_biomass_above_reading: p, late_biomass_estimate_od: est, rationale: rationale.trim() || '(no rationale given)' }))
    if (!res) return
    if ('ok' in res) {
      setError(res.error ?? 'diagnosis rejected')
      return
    }
    setSubmitted(res)
    try {
      setVerdict(await sandbox.verdict(session.id))
    } catch (e) {
      setVerdictError(e instanceof Error ? e.message : String(e))
    }
  }

  const autoplay = async (agent: 'good_scientist' | 'passive_bayes') => {
    if (!session) return
    const res = await run(agent, () => sandbox.autoplay(session.id, agent))
    if (res) setAuto((a) => ({ ...a, [agent]: res }))
  }

  const done = submitted !== null
  const cost = reps
  const canMeasure = !!session && !done && cost <= session.budget && busy === null
  const back = session?.measurements.map((m) => ({ ...m, corrected: m.mean_reading * m.dilution_factor })) ?? []
  const reveal = verdict?.reveal
  const ymax = Math.max(1, ...(session?.passive.map((r) => r.mean_reading) ?? []), ...back.map((m) => m.corrected), reveal ? reveal.growth.k_odeq : 0) * 1.15

  return (
    <div className="doc">
      <MetaBar
        items={[
          ['Lab', 'virtual plate reader'],
          ['Budget', '6 units · 1 per replicate'],
          ['Limits', '0–18 h · 1:1–1:100 · ≤ 3 replicates'],
          ['Scoring', 'deterministic evaluator'],
        ]}
      />
      <div className="doc__wrap">
        <header className="doc__hero" style={{ paddingBottom: 18 }}>
          <p className="kicker">Lab · you are the scientist</p>
          <h1>Is the culture really done growing, or is the reader?</h1>
          <p className="lead">Run the same experiment the agents ran. You see what they saw; the hidden world is revealed only after your diagnosis is scored.</p>
        </header>

        <section className="doc__section">
          <h3>01 · Choose a culture</h3>
          <div className="seg" role="group" aria-label="Culture">
            {CULTURES.map((c) => (
              <button key={c.id} className={session?.culture === c.id ? 'on' : ''} disabled={busy !== null} onClick={() => start(c.id)}>
                {c.label}
              </button>
            ))}
          </div>
          <p className="small faint" style={{ marginTop: 8 }}>
            A and B are the matched demo pair: identical undiluted curves, different hidden worlds. Choosing a culture starts a new session.
          </p>
        </section>

        {error && (
          <p className="fail" role="alert" style={{ fontFamily: 'var(--sans)' }}>
            {error}
          </p>
        )}

        {session && (
          <div className="doc__cols" style={{ gridTemplateColumns: '1.35fr 1fr', alignItems: 'start' }}>
            <div>
              <section className="doc__section">
                <h3>02 · Evidence so far</h3>
                <Plot width={620} height={300} ymax={ymax} yticks={ticks(ymax)} right={110} title="Lab growth curve" ydigits={ymax < 2 ? 1 : 0}>
                  {(s) => (
                    <>
                      {reveal && <HLine s={s} y={reveal.assay.s_odeq} stroke={INK.mute} />}
                      {reveal && <Line s={s} points={reveal.latent_curve} stroke={INK.red} dash="4 3" width={1.3} />}
                      <Dots s={s} points={session.passive.map((r) => [r.time_h, r.mean_reading])} fill={INK.ink} r={3} tip={([t, v]) => `${t} h, undiluted: ${v.toFixed(4)}`} />
                      <Diamonds
                        s={s}
                        fill={INK.blue}
                        points={back.map((m, i) => ({ t: m.time_h, v: m.corrected, key: String(i), dx: back.slice(0, i).filter((x) => x.time_h === m.time_h).length, tip: `1:${m.dilution_factor} at ${m.time_h} h → ${m.corrected.toFixed(3)}` }))}
                      />
                      {reveal && (
                        <text className="fig__lab" x={s.x(18) + 10} y={s.y(reveal.growth.k_odeq) + 4} style={{ fill: INK.red }}>
                          true biomass
                        </text>
                      )}
                    </>
                  )}
                </Plot>
                <figcaption>
                  Dots: free undiluted readings. Diamonds: your diluted readings × dilution factor.
                  {reveal ? ' Dashed red: hidden true biomass; dotted: reader ceiling.' : ''}
                </figcaption>
              </section>

              <section className="doc__section">
                <h3>03 · Your measurements</h3>
                {back.length === 0 ? (
                  <p className="small faint">None yet. Undiluted readings cannot rise above the reader's ceiling, whatever the time point.</p>
                ) : (
                  <table className="bk dense">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Aliquot</th>
                        <th>Dilution</th>
                        <th className="l">Replicates</th>
                        <th>Mean</th>
                        <th>× factor</th>
                        <th>vs undiluted</th>
                      </tr>
                    </thead>
                    <tbody>
                      {back.map((m) => {
                        const u = session.passive.find((r) => r.time_h === m.time_h)?.mean_reading
                        return (
                          <tr key={m.turn}>
                            <td>{m.turn}</td>
                            <td>{m.time_h} h</td>
                            <td>1:{m.dilution_factor}</td>
                            <td className="l mono">{m.readings.map((v) => v.toFixed(4)).join('  ')}</td>
                            <td className="mono">{m.mean_reading.toFixed(4)}</td>
                            <td className="mono">
                              <b>{m.corrected.toFixed(3)}</b>
                            </td>
                            <td>{u ? `${(m.corrected / u).toFixed(2)}×` : '—'}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                )}
              </section>
            </div>

            <div>
              <section className="doc__section">
                <h3>Design a measurement</h3>
                <div className="field">
                  <label htmlFor="lab-time">
                    Aliquot time <b>{time} h</b>
                  </label>
                  <input id="lab-time" type="range" min={0} max={18} step={1} value={time} disabled={done} onChange={(e) => setTime(Number(e.target.value))} />
                </div>
                <div className="field">
                  <span className="lbl">Dilution</span>
                  <div className="seg" role="group" aria-label="Dilution factor">
                    {DILUTIONS.map((d) => (
                      <button key={d} className={dilution === d ? 'on' : ''} disabled={done} onClick={() => setDilution(d)}>
                        1:{d}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="field">
                  <span className="lbl">Replicates</span>
                  <div className="seg" role="group" aria-label="Replicates">
                    {[1, 2, 3].map((r) => (
                      <button key={r} className={reps === r ? 'on' : ''} disabled={done} onClick={() => setReps(r)}>
                        {r}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="budget" aria-label={`Budget: ${session.budget} of ${session.total} units left`}>
                  {Array.from({ length: session.total }, (_, i) => (
                    <i key={i} className={i < session.total - session.budget ? 'used' : i < session.total - session.budget + cost ? 'next' : ''} />
                  ))}
                  <span>
                    {session.budget} of {session.total} units left · this costs {cost}
                  </span>
                </div>
                <button className="pbtn" disabled={!canMeasure} onClick={measure}>
                  {busy === 'measure' ? 'Measuring…' : `Measure ${reps}× at ${time} h, 1:${dilution}`}
                </button>
              </section>

              <section className="doc__section">
                <h3>Diagnose</h3>
                <div className="hyp">
                  {(['BIOMASS_AS_READ', 'BIOMASS_ABOVE_READING'] as const).map((d) => (
                    <button key={d} className={`hyp__opt ${dx === d ? 'on' : ''}`} disabled={done} onClick={() => setDx(d)} aria-pressed={dx === d}>
                      <code>{d}</code>
                      {d === 'BIOMASS_AS_READ' ? 'The culture plateaued where the readings flatten.' : 'The reader saturated; true biomass is higher.'}
                    </button>
                  ))}
                </div>
                <div className="field">
                  <label htmlFor="lab-p">
                    P(biomass above reading) <b>{p.toFixed(2)}</b>
                  </label>
                  <input id="lab-p" type="range" min={0} max={1} step={0.01} value={p} disabled={done} onChange={(e) => setP(Number(e.target.value))} />
                </div>
                <div className="field">
                  <label htmlFor="lab-est">Late biomass estimate (OD, optional)</label>
                  <input id="lab-est" type="number" min={0} step={0.01} value={estimate} disabled={done} onChange={(e) => setEstimate(e.target.value)} />
                </div>
                <div className="field">
                  <label htmlFor="lab-why">Rationale</label>
                  <textarea id="lab-why" rows={3} value={rationale} disabled={done} onChange={(e) => setRationale(e.target.value)} placeholder="What evidence supports this?" />
                </div>
                <button className="pbtn pbtn--solid" disabled={!dx || done || busy !== null} onClick={diagnose}>
                  {busy === 'diagnose' ? 'Scoring…' : 'Submit diagnosis'}
                </button>
              </section>
            </div>
          </div>
        )}

        {submitted && (
          <section className="doc__section">
            <h3>04 · Scored by the evaluator</h3>
            {verdict ? (
              <div className="doc__cols" style={{ alignItems: 'start' }}>
                <table className="bk checks">
                  <tbody>
                    <tr>
                      <td>M1 · Correct diagnosis</td>
                      <td className="why">you said {DIAG_LABEL[submitted.diagnosis.diagnosis]}</td>
                      <td>
                        <Check ok={verdict.scores.correct} />
                      </td>
                    </tr>
                    <tr>
                      <td>M2 · Diagnostic control</td>
                      <td className="why">a late, diluted read before diagnosing</td>
                      <td>
                        <Check ok={verdict.scores.diagnostic_control} />
                      </td>
                    </tr>
                    <tr>
                      <td>M3 · Correct and justified</td>
                      <td className="why">{verdict.scores.correct && !verdict.scores.justified ? 'right, but you had no evidence for it' : 'M1 and M2 both hold'}</td>
                      <td>
                        <Check ok={verdict.scores.justified} />
                      </td>
                    </tr>
                    <tr>
                      <td>Brier</td>
                      <td className="why">(p − y)²</td>
                      <td className="mono">{fmt(verdict.scores.brier, 4)}</td>
                    </tr>
                    <tr>
                      <td>Units</td>
                      <td className="why">of 6</td>
                      <td className="mono">{verdict.scores.cost_units}</td>
                    </tr>
                  </tbody>
                </table>
                <div className="truthbox">
                  <span className="sc">Hidden world · revealed after scoring</span>
                  <dl className="kv" style={{ marginTop: 8 }}>
                    <dt>Condition</dt>
                    <dd>
                      {CONDITION_LABEL[verdict.reveal.condition]} (expects <code>{hypothesisFor(verdict.reveal.condition)}</code>)
                    </dd>
                    <dt>True biomass K</dt>
                    <dd>{verdict.reveal.growth.k_odeq.toFixed(3)} OD</dd>
                    <dt>Reader ceiling S</dt>
                    <dd>{verdict.reveal.assay.s_odeq.toFixed(3)} OD</dd>
                    <dt>K / S</dt>
                    <dd>{verdict.reveal.k_ratio.toFixed(2)}</dd>
                  </dl>
                </div>
              </div>
            ) : (
              <p className="small">
                Diagnosis recorded. The evaluator verdict needs the evaluator token on the API proxy{verdictError ? ` (${verdictError})` : ''}.
              </p>
            )}

            {verdict && (
              <>
                <h3 style={{ marginTop: 24 }}>Same culture, scripted agents</h3>
                <div className="dlbar">
                  <button disabled={busy !== null} onClick={() => autoplay('good_scientist')}>
                    {busy === 'good_scientist' ? 'Running GoodScientist…' : 'Run GoodScientist'}
                  </button>
                  <button disabled={busy !== null} onClick={() => autoplay('passive_bayes')}>
                    {busy === 'passive_bayes' ? 'Running PassiveBayes (≈15 s)…' : 'Run PassiveBayes'}
                  </button>
                </div>
                {Object.keys(auto).length > 0 && (
                  <table className="bk dense" style={{ marginTop: 12 }}>
                    <thead>
                      <tr>
                        <th>Agent</th>
                        <th>Diagnosis</th>
                        <th>P</th>
                        <th>Units</th>
                        <th>M1</th>
                        <th>M3</th>
                        <th className="l">Rationale</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(auto).map(([k, a]) => (
                        <tr key={k}>
                          <td>{agentMeta(k).name}</td>
                          <td>{a.diagnosis ? DIAG_LABEL[a.diagnosis.diagnosis] : '—'}</td>
                          <td className="mono">{fmt(a.diagnosis?.p_biomass_above_reading, 3)}</td>
                          <td className="mono">{a.scores.cost_units}</td>
                          <td>
                            <Check ok={a.diagnosis ? a.scores.correct : null} />
                          </td>
                          <td>
                            <Check ok={a.diagnosis ? a.scores.justified : null} />
                          </td>
                          <td className="why">{a.diagnosis?.rationale ?? ''}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </>
            )}
          </section>
        )}
      </div>
    </div>
  )
}

function ticks(max: number) {
  const step = max <= 1.5 ? 0.25 : max <= 3.5 ? 0.5 : 1
  return Array.from({ length: Math.floor(max / step) + 1 }, (_, i) => +(i * step).toFixed(2))
}
