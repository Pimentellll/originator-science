import { useEffect, useMemo, useState } from 'react'
import { useSession } from '../state/sessionContext'
import { ProvenancePill } from '../components/ui'
import { aggregateCell, ALL_FAMILIES } from '../lib/derive'
import type { BenchmarkReport, MetricInfo } from '../lib/types'
import { LoadState } from './Cockpit'

function fmt(m: MetricInfo, v: number): string {
  if (m.max <= 1) return v.toFixed(2)
  return v.toFixed(1)
}

export function BenchmarkLab() {
  const s = useSession()
  const [report, setReport] = useState<BenchmarkReport | undefined>(undefined)
  const [err, setErr] = useState<string | null>(null)
  const [family, setFamily] = useState<string>(ALL_FAMILIES)

  useEffect(() => {
    let alive = true
    s.transport
      .getBenchmark()
      .then((r) => alive && setReport(r))
      .catch((e) => alive && setErr(e instanceof Error ? e.message : String(e)))
    return () => {
      alive = false
    }
  }, [s.transport])

  const rows = useMemo(() => {
    if (!report) return []
    return report.metrics.map((m) => {
      const cells = report.policies.map((p) => aggregateCell(report, family, p.name, m.id))
      const oks = cells.map((c) => (c.cell.status === 'ok' ? c.cell.value : null))
      const valid = oks.filter((v): v is number => v !== null)
      const best = valid.length > 1 ? (m.direction === 'higher' ? Math.max(...valid) : Math.min(...valid)) : null
      return { m, cells, oks, best }
    })
  }, [report, family])

  if (err) return <div className="state" role="alert"><b>Cannot load benchmark</b><pre>{err}</pre></div>
  if (report === undefined) return <LoadState what="benchmark" />

  const isMock = report.status === 'mock'
  const ran = new Set(
    report.policies
      .filter((p) => Object.values(report.cells).some((f) => Object.values(f[p.name] ?? {}).some((c) => c.status === 'ok')))
      .map((p) => p.name),
  )
  const slices = report.families.filter((f) => f.slice)
  const worlds = report.families.filter((f) => !f.slice)

  return (
    <div className="lab">
      <div className="lab__hd">
        <div>
          <h1>Benchmark Lab</h1>
          <p>Policies compared on identical seeded worlds. Correctness and justification are reported separately.</p>
        </div>
        <div className="lab__prov">
          <ProvenancePill provenance={report.provenance} />
          {report.seed_set && <span className="mono faint">{report.seed_set}</span>}
        </div>
      </div>

      {isMock && (
        <div className="lab__banner" role="note">
          <b>DEV / MOCK DATA</b>
          <span>Placeholder numbers generated for interface development. They are not experiment results and must not be quoted. Cells marked NOT RUN have no result at all.</span>
        </div>
      )}

      {report.status === 'not_run' ? (
        <div className="lab__none">
          <b>NOT RUN</b>
          <span>No benchmark results exist yet.</span>
          <span className="faint">{report.provenance.label}</span>
        </div>
      ) : (
        <>
          <div className="lab__filters" role="group" aria-label="Scenario filter">
            <span className="hdr__label">Worlds</span>
            <button className={`chip ${family === ALL_FAMILIES ? 'chip--accent' : ''}`} onClick={() => setFamily(ALL_FAMILIES)} aria-pressed={family === ALL_FAMILIES}>All worlds</button>
            {worlds.map((f) => (
              <button key={f.id} className={`chip ${family === f.id ? 'chip--accent' : ''}`} onClick={() => setFamily(f.id)} aria-pressed={family === f.id}>
                {f.label}
              </button>
            ))}
            {slices.length > 0 && <span className="hdr__label lab__sl">Slices</span>}
            {slices.map((f) => (
              <button key={f.id} className={`chip ${family === f.id ? 'chip--accent' : ''}`} onClick={() => setFamily(f.id)} aria-pressed={family === f.id}>
                {f.label}
              </button>
            ))}
          </div>

          <div className={`lab__table ${isMock ? 'is-mock' : ''}`}>
            <table>
              <thead>
                <tr>
                  <th className="lab__metric">Metric</th>
                  {report.policies.map((p) => (
                    <th key={p.name}>
                      {p.label}
                      {!ran.has(p.name) && <span className="lab__nrh mono">NOT RUN</span>}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map(({ m, cells, oks, best }) => (
                  <tr key={m.id}>
                    <td className="lab__metric">
                      {m.label} <span className="lab__dir mono">{m.direction === 'higher' ? '↑ better' : '↓ better'}</span>
                    </td>
                    {cells.map((c, i) => {
                      const v = oks[i]
                      return (
                        <td key={i} className={best !== null && v === best ? 'is-best' : ''}>
                          {c.cell.status === 'ok' ? (
                            <div className="lab__cell">
                              <span className="lab__v mono">{fmt(m, c.cell.value)}</span>
                              <span className="lab__bar">
                                <span style={{ width: `${Math.min(1, c.cell.value / m.max) * 100}%` }} />
                                {c.cell.ci && <i style={{ left: `${(c.cell.ci[0] / m.max) * 100}%`, width: `${((c.cell.ci[1] - c.cell.ci[0]) / m.max) * 100}%` }} />}
                              </span>
                              <span className="lab__n mono faint">
                                n={c.cell.n}
                                {c.total > 1 && c.of < c.total ? ` · ${c.of}/${c.total} worlds` : ''}
                              </span>
                            </div>
                          ) : c.cell.status === 'not_run' ? (
                            <span className="lab__nr mono">NOT RUN</span>
                          ) : (
                            <span className="lab__na mono">n/a</span>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            {isMock && <div className="lab__wm" aria-hidden>{Array.from({ length: 24 }, (_, i) => <span key={i}>MOCK · DEV</span>)}</div>}
          </div>
          <p className="lab__foot">
            No policy is assumed to win by default; greedy EIG is expected to stay competitive on myopic worlds. “All worlds” averages over the worlds that were run, weighted by episodes, and reports coverage when a policy was not run on every world. Slices overlap the world classes and are excluded from the average.
          </p>
        </>
      )}
    </div>
  )
}
