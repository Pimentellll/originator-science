import { CiBar, Diamonds, Dots, Line, Plot } from '../../components/figures/Plot'
import { INK } from '../../components/figures/ink'
import { OutcomeMatrix } from '../../components/figures/OutcomeMatrix'
import { Reliability } from '../../components/figures/Reliability'
import { downloadText, outcome, reliability, toCsv } from '../../lib/growth/analysis'
import type { Condition, GrowthEpisode, GrowthGrid, GrowthRun, GrowthRunEntry, Rate } from '../../lib/growth/types'
import type { Route } from '../../state/route'
import { runMeta } from './agents'
import { growthClient, useAsync } from './data'
import { DocState, MetaBar } from './parts'

type Loaded = {
  runs: GrowthRunEntry[]
  grid: GrowthGrid
  details: GrowthRun[]
  demo: { runId: string; bp: GrowthEpisode; ma: GrowthEpisode } | null
}

async function load(): Promise<Loaded> {
  const c = growthClient()
  const [runs, grid] = await Promise.all([c.listRuns(), c.getGrid('strong')])
  const details = await Promise.all(grid.columns.map((col) => c.getRun(col.run_id)))
  const demoRun = runs.find((r) => r.matrix === 'demo')
  let demo: Loaded['demo'] = null
  if (demoRun) {
    const [bp, ma] = await Promise.all([c.getEpisode(demoRun.run_id, 'demo-BP'), c.getEpisode(demoRun.run_id, 'demo-MA')])
    demo = { runId: demoRun.run_id, bp, ma }
  }
  return { runs, grid, details, demo }
}

type Metrics = Record<string, { M1?: Rate; M2?: Rate; M3?: Rate; M4?: { mean: number }; Q1?: number; O1?: number; n?: number }>

function itt(run: GrowthRun): Metrics {
  const m = (run.summary as { metrics?: { intention_to_treat?: Metrics } } | null)?.metrics?.intention_to_treat
  return m ?? {}
}

export function Results({ navigate }: { navigate: (r: Route, ...p: string[]) => void }) {
  const data = useAsync('results', load)
  if (data.state !== 'ready') return <DocState async={data} what="benchmark results" />
  const { grid, details, demo, runs } = data.value
  const labels = details.map((d) => {
    const m = runMeta(d.run)
    return `${m.code} ${m.name}`
  })
  const pb = details.find((d) => d.run.agent === 'passive_bayes')
  const n = details[0]?.run.n_episodes ?? 0

  const table1 = details.map((d) => {
    const h = d.run.headline
    const o = itt(d).overall
    return {
      agent: labels[details.indexOf(d)],
      run_id: d.run.run_id,
      M1_k: h?.M1.k ?? null,
      M2_k: h?.M2.k ?? null,
      M3_k: h?.M3.k ?? null,
      n: h?.M1.n ?? null,
      M1_wilson95: h ? h.M1.wilson95.map((v) => v.toFixed(3)).join('–') : null,
      M3_wilson95: h ? h.M3.wilson95.map((v) => v.toFixed(3)).join('–') : null,
      Q1: h?.Q1 ?? null,
      brier_mean: d.run.brier_mean,
      units_mean: o?.M4?.mean ?? null,
    }
  })

  return (
    <div className="doc">
      <MetaBar
        items={[
          ['Benchmark', 'MIRAGE-Bio · OD600 saturation'],
          ['Scenario', 'scenario-v1 (frozen)'],
          ['Matrix', `strong · ${n} episodes per agent`],
          ['Evaluator', 'deterministic, no LLM'],
        ]}
      />
      <div className="doc__wrap">
        <header className="doc__hero">
          <p className="kicker">Results · held-out evaluation seeds</p>
          <h1>
            A correct answer is not evidence that the agent <i>knew</i>.
          </h1>
          <p className="lead">
            Each agent sees the same 18-hour growth curve that has flattened. The flat line is either a real plateau or a plate reader at its ceiling, and only a diluted
            measurement can tell them apart. MIRAGE-Bio scores whether the answer was right <b>and</b> whether the agent ran the control that justifies it.
          </p>
          {pb?.run.headline && (
            <p className="lead" style={{ marginTop: 14 }}>
              PassiveBayes never measures. It is right on <b>{pb.run.headline.M1.k}</b> of {pb.run.headline.M1.n} episodes and justified on{' '}
              <b className="gap">{pb.run.headline.M3.k}</b>.
            </p>
          )}
        </header>

        {demo && (
          <section className="doc__section">
            <h3>Figure 1</h3>
            <div className="doc__cols">
              <figure>
                <div className="plabel">a · Undiluted readings</div>
                <Plot ymax={4.5} yticks={[0, 1, 2, 3, 4]} right={20} title="Undiluted readings of the two demo cultures">
                  {(s) => (
                    <>
                      <Dots s={s} points={demo.ma.passive.map((r) => [r.time_h, r.mean_reading])} fill={INK.ink} r={3.2} />
                      <Dots s={s} points={demo.bp.passive.map((r) => [r.time_h, r.mean_reading])} fill="none" stroke={INK.ink2} r={5} />
                      <text className="fig__lab" x={s.x(6.5)} y={s.y(2.6)} style={{ fill: INK.ink2 }}>
                        Plateau culture (rings) and saturated
                      </text>
                      <text className="fig__lab" x={s.x(6.5)} y={s.y(2.25)} style={{ fill: INK.ink2 }}>
                        culture (dots): the same readings.
                      </text>
                    </>
                  )}
                </Plot>
              </figure>
              <figure>
                <div className="plabel">b · After a dilution control</div>
                <Plot ymax={4.5} yticks={[0, 1, 2, 3, 4]} right={118} title="Dilution-corrected measurements and hidden true biomass">
                  {(s) => (
                    <>
                      <Dots s={s} points={demo.ma.passive.map((r) => [r.time_h, r.mean_reading])} fill={INK.faint} r={2.6} />
                      <Line s={s} points={demo.ma.derived.latent_curve} stroke={INK.red} dash="4 3" width={1.2} />
                      <Line s={s} points={demo.bp.derived.latent_curve} stroke={INK.blue} dash="4 3" width={1.2} />
                      <Diamonds s={s} fill={INK.red} points={demo.ma.derived.measurements.flatMap((m, i) => (m.time_h === null || m.back_corrected === null ? [] : [{ t: m.time_h, v: m.back_corrected, key: `ma${i}`, dx: i % 2, tip: `1:${m.dilution_factor} at ${m.time_h} h → ${m.back_corrected.toFixed(2)}` }]))} />
                      <Diamonds s={s} fill={INK.blue} points={demo.bp.derived.measurements.flatMap((m, i) => (m.time_h === null || m.back_corrected === null ? [] : [{ t: m.time_h, v: m.back_corrected, key: `bp${i}`, dx: i % 2, tip: `1:${m.dilution_factor} at ${m.time_h} h → ${m.back_corrected.toFixed(2)}` }]))} />
                      <text className="fig__lab" x={s.x(18) + 10} y={s.y(demo.ma.episode.growth.k_odeq) + 4} style={{ fill: INK.red }}>
                        saturated, K = {demo.ma.episode.growth.k_odeq.toFixed(1)}
                      </text>
                      <text className="fig__lab" x={s.x(18) + 10} y={s.y(demo.bp.episode.growth.k_odeq) + 14} style={{ fill: INK.blue }}>
                        plateau, K = {demo.bp.episode.growth.k_odeq.toFixed(1)}
                      </text>
                    </>
                  )}
                </Plot>
              </figure>
            </div>
            <figcaption>
              <b>Figure 1. The passive curve cannot decide; one dilution can.</b> The matched demo pair: a plateau culture and a saturated culture whose undiluted
              readings coincide (a). Diamonds are the live Claude demo run's diluted readings multiplied by their dilution factor; dashed lines are the hidden true
              biomass, revealed after scoring (b). Source: <span className="mono">experiments/results/{demo.runId}/</span>.{' '}
              <button className="crumb-link" onClick={() => navigate('episode', demo.runId, 'demo-MA')}>
                Open the saturated culture's record
              </button>
            </figcaption>
          </section>
        )}

        <section className="doc__section">
          <h3>Table 1</h3>
          <table className="bk">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Correct (M1)</th>
                <th>Ran the control (M2)</th>
                <th>Correct and justified (M3)</th>
                <th>Q1</th>
                <th>Brier ↓</th>
                <th>Units used</th>
              </tr>
            </thead>
            <tbody>
              {details.map((d, i) => {
                const h = d.run.headline
                const m = runMeta(d.run)
                const units = itt(d).overall?.M4?.mean
                return (
                  <tr key={d.run.run_id}>
                    <td>
                      {labels[i]}
                      <span className="sub">
                        {m.kind}
                        {d.run.frozen ? ' · frozen record' : ''}
                      </span>
                    </td>
                    {h ? (
                      <>
                        {(['M1', 'M2', 'M3'] as const).map((k) => (
                          <td key={k}>
                            <span className={`num ${k === 'M3' && h.M1.k - h.M3.k > 5 ? 'gap' : ''}`}>
                              {h[k].k}
                              <small>/{h[k].n}</small>
                            </span>
                            <CiBar k={h[k].k} n={h[k].n} lo={h[k].wilson95[0]} hi={h[k].wilson95[1]} />
                          </td>
                        ))}
                        <td className="num">{h.Q1 === null ? '—' : h.Q1.toFixed(2)}</td>
                      </>
                    ) : (
                      <td colSpan={4}>no summary</td>
                    )}
                    <td className="num">{d.run.brier_mean === null ? '—' : d.run.brier_mean.toFixed(3)}</td>
                    <td className="num">
                      {units === undefined ? '—' : units.toFixed(2)}
                      <small> / 6</small>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <figcaption>
            <b>Table 1. Accuracy alone does not separate the agents; justification does.</b> Counts are over the {n} held-out strong-matrix episodes (intention to
            treat). Bars are Wilson 95% intervals on [0, 1]. M2: a late, diluted measurement in the frozen diagnostic action set, made before the diagnosis. M3: M1 and
            M2 both hold. Q1: fraction of episodes with an adequate biomass reconstruction. Brier: mean (p − y)² for the stated P(biomass above reading). Units: mean
            measurement units spent of the 6 available.
          </figcaption>
          <div className="dlbar" style={{ marginTop: 10 }}>
            <button onClick={() => downloadText('mirage-growth-table1.csv', toCsv(Object.keys(table1[0] ?? {}), table1), 'text/csv')}>Table 1 as CSV</button>
            <button onClick={() => downloadText('mirage-growth-runs.json', JSON.stringify(runs, null, 2), 'application/json')}>Run index as JSON</button>
          </div>
        </section>

        <section className="doc__section">
          <h3>Figure 2</h3>
          <OutcomeMatrix grid={grid} labels={labels} onOpen={(run, ep) => navigate('episode', run, ep)} />
          <div className="legend">
            <span>
              <i className="sw sw--j" />
              correct and justified
            </span>
            <span>
              <i className="sw sw--u" />
              correct, not justified
            </span>
            <span>
              <i className="sw sw--w" />
              wrong
            </span>
            <span>
              <i className="sw sw--n" />
              no diagnosis
            </span>
            <span className="faint">P = plateau · S = reader saturation (hidden condition)</span>
          </div>
          <figcaption>
            <b>Figure 2. Every scored episode.</b> Columns are the {grid.rows.length} evaluation seeds; select any square to open that agent's full record. Hatched
            squares are right answers with no diagnostic control behind them.
          </figcaption>
          <div className="dlbar" style={{ marginTop: 10 }}>
            <button
              onClick={() =>
                downloadText(
                  'mirage-growth-grid-strong.csv',
                  toCsv(
                    ['episode_id', 'seed', 'condition', ...grid.columns.map((c) => c.run_id)],
                    grid.rows.map((r) => ({
                      episode_id: r.episode_id,
                      seed: r.seed,
                      condition: r.condition,
                      ...Object.fromEntries(grid.columns.map((c) => [c.run_id, r.cells[c.run_id] ? outcome(r.cells[c.run_id]) : 'none'])),
                    })),
                  ),
                  'text/csv',
                )
              }
            >
              Outcome grid as CSV
            </button>
          </div>
        </section>

        <section className="doc__section">
          <h3>Table 2</h3>
          <table className="bk">
            <thead>
              <tr>
                <th rowSpan={2}>Agent</th>
                <th colSpan={2} style={{ textAlign: 'center' }}>
                  Plateau
                </th>
                <th colSpan={2} style={{ textAlign: 'center' }}>
                  Reader saturation
                </th>
              </tr>
              <tr>
                <th>M1</th>
                <th>M3</th>
                <th>M1</th>
                <th>M3</th>
              </tr>
            </thead>
            <tbody>
              {details.map((d, i) => {
                const m = itt(d)
                const cell = (c: Condition, k: 'M1' | 'M3') => {
                  const v = m[c]?.[k]
                  return v ? `${v.k}/${m[c]?.n ?? '?'}` : '—'
                }
                return (
                  <tr key={d.run.run_id}>
                    <td>{labels[i]}</td>
                    <td className="num">{cell('BIOLOGICAL_PLATEAU', 'M1')}</td>
                    <td className="num">{cell('BIOLOGICAL_PLATEAU', 'M3')}</td>
                    <td className="num">{cell('MEASUREMENT_ARTIFACT', 'M1')}</td>
                    <td className="num">{cell('MEASUREMENT_ARTIFACT', 'M3')}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <figcaption>
            <b>Table 2. Results by hidden condition.</b> Both Claude models miss the same plateau episode, <span className="mono">s500028-BP</span>. There the reader
            under-reads the plateau by 2–4%, so a careful dilution looks like slightly more biomass than the undiluted reading. This known residual is recorded in{' '}
            <span className="mono">OPEN_RULINGS.md</span>, and no episode was rescored because of it.
          </figcaption>
        </section>

        <section className="doc__section">
          <h3>Figure 3</h3>
          <div className="doc__cols3" style={{ gridTemplateColumns: `repeat(${details.length}, 1fr)` }}>
            {details.map((d, i) => (
              <figure key={d.run.run_id}>
                <div className="plabel">{labels[i]}</div>
                <Reliability title={`Reliability diagram for ${labels[i]}`} bins={reliability(d.episodes.map((e) => ({ p: e.p_biomass_above_reading, condition: e.condition })))} />
                <div className="small faint" style={{ fontFamily: 'var(--sans)', fontSize: 12 }}>
                  Brier {d.run.brier_mean === null ? '—' : d.run.brier_mean.toFixed(3)}
                </div>
              </figure>
            ))}
          </div>
          <figcaption>
            <b>Figure 3. Calibration.</b> Episodes are binned by the stated P(biomass above reading) into five equal bins; each marker is the bin's mean stated
            probability against the observed fraction of saturated cultures, with area proportional to the episode count. Points on the dashed diagonal are calibrated.
            PassiveBayes stays near 0.5 because the passive curve carries almost no information about the hidden condition.
          </figcaption>
        </section>

        <section className="doc__section">
          <h3>What these results do not show</h3>
          <p className="small">
            One synthetic scenario with one assay failure mode, and {n} episodes per agent. Growth follows a Richards model and the reader a fixed saturation curve;
            real plate readers, media and cultures vary in ways this does not model. With {n} episodes the two Claude models cannot be told apart (both 95% intervals
            overlap almost entirely). The scripted baselines are references for the scoring rule, not competitors.
          </p>
          <p className="doc__foot">
            Records under <span className="mono">experiments/results/</span>; C1 hashes in <span className="mono">FREEZE.md</span>. Data source:{' '}
            {growthClient().kind === 'static' ? 'static export (offline)' : 'local MIRAGE API'}.
          </p>
        </section>
      </div>
    </div>
  )
}
