import { Diamonds, Dots, Line, Plot } from '../../components/figures/Plot'
import { INK } from '../../components/figures/ink'
import type { ExploratoryRun, GrowthRun } from '../../lib/growth/types'
import type { Route } from '../../state/route'
import { runMeta } from './agents'
import { useAsync } from './data'
import { DocState } from './parts'
import { load } from './resultsData'

type Nav = (r: Route, ...p: string[]) => void

export function Overview({ navigate }: { navigate: Nav }) {
  const data = useAsync('results', load)
  if (data.state !== 'ready') return <DocState async={data} what="benchmark results" />
  const { details, demo, exploratory } = data.value
  const scored = details.filter((d) => d.run.headline)
  const families = exploratory.filter((r) => r.experiment === 'cross-family' && r.headline)
  const familyControlMin = families.length ? Math.min(...families.map((r) => r.headline!.M2.k)) : null
  const pb = scored.find((d) => d.run.agent === 'passive_bayes')?.run.headline
  const claude = scored.filter((d) => d.run.agent === 'claude').map((d) => d.run.headline!)
  const claudeMin = claude.length ? Math.min(...claude.map((h) => h.M3.k)) : null
  const n = scored[0]?.run.headline?.M1.n ?? 0

  return (
    <div className="doc ov">
      <div className="doc__wrap">
        <header className="doc__hero ov__hero">
          <p className="kicker">MIRAGE-Bio · a benchmark for AI scientists</p>
          <h1>Can an AI scientist tell when its evidence isn’t enough?</h1>
          <p className="lead">
            A plate reader can only count so high. When a bacterial growth curve flattens, either the culture has stopped growing or the reader has hit its ceiling, and
            the curve looks the same both ways. A careful scientist dilutes a sample and measures again. MIRAGE-Bio is a virtual lab that checks whether an AI agent
            does that, and scores the <b>reasoning</b>, not just the answer.
          </p>
        </header>

        {demo && (
          <section className="doc__section">
            <p className="kicker ov__num">1 · The problem</p>
            <h2>Two cultures, one curve.</h2>
            <div className="doc__cols ov__figs">
              <figure>
                <Plot ymax={4.5} yticks={[0, 1, 2, 3, 4]} right={20} height={260} title="Undiluted readings of two different cultures">
                  {(s) => (
                    <>
                      <Dots s={s} points={demo.ma.passive.map((r) => [r.time_h, r.mean_reading])} fill={INK.ink} r={3.2} />
                      <Dots s={s} points={demo.bp.passive.map((r) => [r.time_h, r.mean_reading])} fill="none" stroke={INK.ink2} r={5.5} />
                    </>
                  )}
                </Plot>
                <figcaption>
                  <b>What the agent sees.</b> Hourly readings from two different cultures (dots and rings). They are identical: both flatten near 1.0.
                </figcaption>
              </figure>
              <figure>
                <Plot ymax={4.5} yticks={[0, 1, 2, 3, 4]} right={118} height={260} title="Dilution-corrected readings and the hidden true biomass">
                  {(s) => (
                    <>
                      <Dots s={s} points={demo.ma.passive.map((r) => [r.time_h, r.mean_reading])} fill={INK.faint} r={2.6} />
                      <Line s={s} points={demo.ma.derived.latent_curve} stroke={INK.red} dash="4 3" width={1.2} />
                      <Line s={s} points={demo.bp.derived.latent_curve} stroke={INK.blue} dash="4 3" width={1.2} />
                      <Diamonds s={s} fill={INK.red} points={demo.ma.derived.measurements.flatMap((m, i) => (m.time_h === null || m.back_corrected === null ? [] : [{ t: m.time_h, v: m.back_corrected, key: `ma${i}`, dx: i % 2, tip: `1:${m.dilution_factor} at ${m.time_h} h → ${m.back_corrected.toFixed(2)}` }]))} />
                      <Diamonds s={s} fill={INK.blue} points={demo.bp.derived.measurements.flatMap((m, i) => (m.time_h === null || m.back_corrected === null ? [] : [{ t: m.time_h, v: m.back_corrected, key: `bp${i}`, dx: i % 2, tip: `1:${m.dilution_factor} at ${m.time_h} h → ${m.back_corrected.toFixed(2)}` }]))} />
                      <text className="fig__lab" x={s.x(18) + 10} y={s.y(demo.ma.episode.growth.k_odeq) + 4} style={{ fill: INK.red }}>
                        reader at its ceiling
                      </text>
                      <text className="fig__lab" x={s.x(18) + 10} y={s.y(demo.bp.episode.growth.k_odeq) + 14} style={{ fill: INK.blue }}>
                        real plateau
                      </text>
                    </>
                  )}
                </Plot>
                <figcaption>
                  <b>After one dilution.</b> Diluting a saved sample and multiplying back (diamonds) separates them. One culture really stopped at{' '}
                  {demo.bp.episode.growth.k_odeq.toFixed(1)}; the other holds about {(demo.ma.episode.growth.k_odeq / demo.bp.episode.growth.k_odeq).toFixed(0)}× more
                  cells than the reader showed. Dashed lines are the hidden truth.
                </figcaption>
              </figure>
            </div>
          </section>
        )}

        <section className="doc__section">
          <p className="kicker ov__num">2 · The test</p>
          <h2>Every agent gets the same lab and the same budget.</h2>
          <ol className="ov__steps">
            <li>
              <b>Look.</b>
              <span>The agent receives 19 hourly readings of one culture, free of charge.</span>
            </li>
            <li>
              <b>Decide whether to test.</b>
              <span>It may spend up to 6 units on diluted measurements of saved samples, one unit per replicate.</span>
            </li>
            <li>
              <b>Answer.</b>
              <span>It states whether the biomass is as read or above the reading, and how confident it is.</span>
            </li>
          </ol>
          <p className="ov__rule">
            A deterministic grader with no language model then asks two questions: <b>was the answer right?</b> and <b>was it backed by the dilution control?</b> A right
            answer without the control counts as right, but not as <i>justified</i>.
          </p>
        </section>

        <section className="doc__section">
          <p className="kicker ov__num">3 · What we found</p>
          <h2>Being right is not the same as knowing.</h2>
          <JustifiedBars
            groups={[
              { rows: scored.map(frozenRow) },
              ...(families.length ? [{ label: 'Other model families · exploratory, not part of the frozen evaluation', rows: families.map(exploratoryRow) }] : []),
            ]}
          />
          <div className="ov__calls">
            {pb && (
              <p>
                <b className="gap">
                  PassiveBayes: right {pb.M1.k}/{pb.M1.n}, justified {pb.M3.k}/{pb.M3.n}.
                </b>{' '}
                It never measures, so every right answer is a lucky guess. Accuracy alone would rank it as a decent scientist.
              </p>
            )}
            {claudeMin !== null && (
              <p>
                <b>
                  Claude Opus and Sonnet: justified {claudeMin}/{n}.
                </b>{' '}
                Both ran the dilution control in every episode. Both missed the same borderline plateau culture.
              </p>
            )}
            {familyControlMin !== null && (
              <p>
                <b>
                  {families.map((r) => r.label).join(' and ')}: ran the control {familyControlMin}/{families[0].headline!.M2.n}.
                </b>{' '}
                Outside Claude, the habit holds. Their misses are plateau cultures, read as artefacts after a correct dilution.{' '}
                <button className="ov__link" onClick={() => navigate('results')}>Table 2</button>
              </p>
            )}
          </div>
        </section>

        <section className="doc__section">
          <p className="kicker ov__num">4 · Explore</p>
          <div className="ov__cards">
            <Card title="See the results" go={() => navigate('results')}>
              The full scorecard with confidence intervals, every scored episode, and calibration.
            </Card>
            <Card title="Try it yourself" go={() => navigate('lab')}>
              Be the scientist: pick a culture, run a dilution, give your diagnosis, then see the hidden truth.
            </Card>
            <Card title="Watch an agent work" go={() => navigate('launch')} tag="guided demo">
            A second environment: a failing protein binder. The planner chooses assays, updates its belief about why the campaign failed, and is judged the same way.
          </Card>
          </div>
          <p className="small faint ov__foot">
            One synthetic scenario, {n} held-out episodes per agent. The <button onClick={() => navigate('method')}>Method</button> page lists the model, the scoring rules
            and the limitations.
          </p>
        </section>
      </div>
    </div>
  )
}

function Card({ title, go, tag, children }: { title: string; go: () => void; tag?: string; children: string }) {
  return (
    <button className="ov__card" onClick={go}>
      <span className="ov__ct">
        {title} <span aria-hidden>→</span>
      </span>
      {tag && <span className="ov__tag">{tag}</span>}
      <span className="ov__cd">{children}</span>
    </button>
  )
}

type BarRow = { key: string; name: string; j: number; u: number; n: number }
type BarGroup = { label?: string; rows: BarRow[] }

function frozenRow(d: GrowthRun): BarRow {
  const h = d.run.headline!
  return { key: d.run.run_id, name: runMeta(d.run).name, j: h.M3.k, u: h.M1.k - h.M3.k, n: h.M1.n }
}

function exploratoryRow(r: ExploratoryRun): BarRow {
  const h = r.headline!
  return { key: `${r.experiment}/${r.run_id}`, name: r.label, j: h.M3.k, u: h.M1.k - h.M3.k, n: h.M1.n }
}

function layoutBars(groups: BarGroup[], row: number, head: number) {
  const laid: { g: BarGroup; top: number; placed: { r: BarRow; at: number }[] }[] = []
  let y = 0
  groups.forEach((g, gi) => {
    const top = y + (g.label && gi ? 10 : 0)
    y = top + (g.label ? head : 0)
    const placed = g.rows.map((r, i) => ({ r, at: y + i * row + 8 }))
    y += g.rows.length * row
    laid.push({ g, top, placed })
  })
  return { laid, H: y + 34 }
}

function JustifiedBars({ groups }: { groups: BarGroup[] }) {
  const W = 760
  const L = 190
  const R = 150
  const row = 40
  const head = 34
  const bw = W - L - R
  const rows = groups.flatMap((g) => g.rows)
  const N = Math.max(1, ...rows.map((r) => r.n))
  const { laid, H } = layoutBars(groups, row, head)
  return (
    <figure className="ov__bars">
      <svg className="fig" width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Correct and justified answers per agent">
        <defs>
          <pattern id="ov-hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="5" stroke={INK.red} strokeWidth="2" />
          </pattern>
        </defs>
        {laid.map(({ g, top, placed }) => (
          <g key={g.label ?? 'frozen'}>
            {g.label && (
              <>
                <line x1={0} x2={W} y1={top + 6} y2={top + 6} stroke={INK.rule} />
                <text x={0} y={top + 26} style={{ fontSize: 11.5, letterSpacing: '0.06em', textTransform: 'uppercase', fill: INK.mute }}>
                  {g.label}
                </text>
              </>
            )}
            {placed.map(({ r, at }) => {
              const sc = bw / r.n
              return (
                <g key={r.key}>
                  <text x={0} y={at + 17} style={{ fontSize: 13.5, fill: INK.ink }}>
                    {r.name}
                  </text>
                  <rect x={L} y={at} width={bw} height={24} fill="none" stroke={INK.rule} />
                  <rect x={L} y={at} width={r.j * sc} height={24} fill={INK.ink} />
                  {r.u > 0 && <rect x={L + r.j * sc} y={at} width={r.u * sc} height={24} fill="url(#ov-hatch)" stroke={INK.red} />}
                  <text x={L + bw + 12} y={at + 17} style={{ fontSize: 13, fill: INK.ink }}>
                    <tspan style={{ fontWeight: 600 }}>{r.j}</tspan> justified
                    {r.u > 0 && <tspan style={{ fill: INK.red }}> · {r.u} lucky</tspan>}
                  </text>
                </g>
              )
            })}
          </g>
        ))}
        {[0, 1, 2, 3].map((q) => Math.round((q * N) / 3)).map((t) => (
          <text key={t} x={L + (t / N) * bw} y={H - 6} textAnchor="middle" style={{ fill: INK.mute }}>
            {t}
          </text>
        ))}
      </svg>
      <div className="legend">
        <span>
          <i className="sw sw--j" /> right and justified by a dilution control
        </span>
        <span>
          <i className="sw sw--u" /> right, but no control: a lucky guess
        </span>
        <span>
          <i className="sw sw--n" /> wrong
        </span>
      </div>
      <figcaption>
        Answers out of {N} held-out episodes per agent. Exploratory rows were registered before their first scored call but designed after the frozen results were known.
      </figcaption>
    </figure>
  )
}
