import { useCallback, useEffect, useState } from 'react'
import { useSession } from '../state/sessionContext'
import { Panel } from '../components/ui'
import type { SystemCheck, SystemReport } from '../lib/types'

const frontend = typeof __MIRAGE_FRONTEND__ === 'undefined' ? { version: 'unknown', sha: 'unknown' } : __MIRAGE_FRONTEND__

const MARK = { pass: '✓', fail: '✗', skip: '–' } as const
const TONE = { pass: 'pill--ok', fail: 'pill--bad', skip: '' } as const

function Row({ c }: { c: SystemCheck }) {
  return (
    <li className="diag__row">
      <span className={`pill ${TONE[c.status]}`} aria-label={c.status}>
        {MARK[c.status]} {c.status.toUpperCase()}
      </span>
      <b>{c.name}</b>
      <span className="dim mono">{c.detail}</span>
    </li>
  )
}

/**
 * System check for teammates and demo setup. It reads only the public/system routes
 * (/health, /version, /policies, /diagnostics); it never touches episode or hidden state.
 */
export function Diagnostics() {
  const s = useSession()
  const [report, setReport] = useState<SystemReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(true)
  const load = useCallback(() => {
    s.transport
      .diagnostics?.()
      .then((r) => {
        setReport(r)
        setError(null)
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false))
  }, [s.transport])
  const run = () => {
    setBusy(true)
    load()
  }
  useEffect(() => load(), [load])

  if (!s.transport.diagnostics)
    return (
      <div className="diag">
        <div className="state" role="status">
          <b>System check needs the live API</b>
          <span>
            This session uses <b>{s.transport.label}</b> data. Open <span className="mono">?transport=live</span> against a running API.
          </span>
        </div>
      </div>
    )

  const v = report?.catalogue.version
  const policies = report?.catalogue.policies
  const checks: SystemCheck[] = report ? [...report.checks] : []
  if (report && policies) {
    const ok = policies.filter((p) => p.available)
    checks.push({ name: 'Policies wired', status: ok.length ? 'pass' : 'fail', detail: `${ok.length} available: ${ok.map((p) => p.name).join(', ')}` })
  }
  const failed = checks.some((c) => c.status === 'fail')

  return (
    <div className="diag">
      <div className="diag__grid">
        <Panel index="S1" title="System check" aside={<button className="btn" onClick={run} disabled={busy}>{busy ? 'CHECKING…' : '↻ RE-RUN'}</button>}>
          <div className="diag__body">
            {error && (
              <div className="state" role="alert">
                <b>Cannot reach the API</b>
                <pre>{error}</pre>
                <span>Run <span className="mono">./mirage doctor</span> in a terminal for exact fixes.</span>
              </div>
            )}
            {!report && !error && <p className="dim" role="status">Running checks…</p>}
            {report && (
              <>
                <p className={`diag__verdict ${failed ? 'is-bad' : 'is-ok'}`} role="status">
                  {failed ? 'SOMETHING IS WRONG' : 'ALL CHECKS PASSED'}
                </p>
                <ul className="diag__list">
                  <li className="diag__row">
                    <span className="pill pill--ok">✓ PASS</span>
                    <b>Frontend → API</b>
                    <span className="dim mono">the browser reached the API through the Vite proxy ({s.transport.label})</span>
                  </li>
                  {checks.map((c) => (
                    <Row key={c.name} c={c} />
                  ))}
                </ul>
                {report.note && <p className="dim diag__note">{report.note}</p>}
              </>
            )}
          </div>
        </Panel>

        <Panel index="S2" title="Versions">
          <dl className="diag__kv">
            <div>
              <dt>Frontend build</dt>
              <dd className="mono">
                {frontend.version} · {frontend.sha}
              </dd>
            </div>
            <div>
              <dt>Backend</dt>
              <dd className="mono">{v ? `mirage ${v.mirage_version} · ${v.api_version}` : 'unknown'}</dd>
            </div>
            <div>
              <dt>Git SHA</dt>
              <dd className="mono">
                {v ? v.git_sha : 'unknown'}
                {v?.git_dirty ? <span className="pill pill--warn diag__dirty" title="Uncommitted changes in the backend checkout">DIRTY</span> : null}
              </dd>
            </div>
            <div>
              <dt>Commit date</dt>
              <dd className="mono">{v?.commit_date ?? 'unknown'}</dd>
            </div>
            <div>
              <dt>Scenario semantics default</dt>
              <dd className="mono">{v ? v.semantics_default : 'unknown'}</dd>
            </div>
            <div>
              <dt>Semantics available</dt>
              <dd className="mono">{v ? v.semantics_available.join(' · ') : 'unknown'}</dd>
            </div>
            <div>
              <dt>Contract</dt>
              <dd className="mono">{v?.contract_version ?? 'unknown'}</dd>
            </div>
            <div>
              <dt>Python</dt>
              <dd className="mono">{v?.python_version ?? 'unknown'}</dd>
            </div>
          </dl>
          <p className="dim diag__note">Quote the Git SHA and semantics version with any screenshot so the run can be reproduced.</p>
        </Panel>

        <Panel index="S3" title="Policy catalogue">
          <ul className="diag__list diag__list--tight">
            {(policies ?? []).map((p) => (
              <li key={p.name} className="diag__row">
                <span className={`pill ${p.available ? 'pill--ok' : ''}`}>{p.available ? 'AVAILABLE' : 'NOT AVAILABLE'}</span>
                <b>{p.label}</b>
                <span className="dim">{p.available ? p.kind.replace(/_/g, ' ') : (p.reason ?? '')}</span>
              </li>
            ))}
            {!policies && <li className="dim">This server has no /policies route.</li>}
          </ul>
        </Panel>
      </div>
    </div>
  )
}
