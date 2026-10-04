import { useSession } from '../state/sessionContext'
import { Panel } from './ui'
import { justification, validity } from '../lib/derive'
import { VerdictBanner } from './Verdict'
import { actionLabel, actionShort } from '../lib/actions'
import { fmtP, MECH_LABEL } from '../lib/format'
import { MECHANISM_GROUPS } from '../lib/types'

/**
 * "Is this conclusion justified?" from public data only. The first four rows describe the
 * belief and the measurement log. The evidence-threshold verdict is taken from the backend's
 * JustificationCertificate and is shown as NOT AVAILABLE until one is supplied: this panel
 * never decides it.
 */
export function JustificationPanel() {
  const { frame, frames } = useSession()
  if (!frame) return <Panel index="02" title="Is this conclusion justified?">{null}</Panel>
  const j = justification(frame, frames[0])
  const cert = j.certificate
  const dH = j.entropy.now - j.entropy.start
  const v = validity(frame)
  const ev = frame.terminal?.evaluation ?? null
  const checks = ev?.checks ?? []

  return (
    <Panel
      index="02"
      title="Is this conclusion justified?"
      className="just"
      aside={cert ? <span className={`pill ${cert.threshold_met ? 'pill--ok' : 'pill--bad'}`}>{cert.threshold_met ? 'THRESHOLD MET' : 'NOT MET'}</span> : <span className="pill">NO CERTIFICATE</span>}
    >
      {frame.terminal ? (
        <VerdictBanner evaluation={ev} decision={frame.terminal.decision} compact />
      ) : (
        <p className="just__pending">No decision yet. The verdict (correct? justified?) is scored by the evaluator only after MIRAGE decides.</p>
      )}
      <dl className="just__list">
        <div>
          <dt>Leading explanation</dt>
          <dd>
            {j.leading ? (
              <>
                <b>{MECH_LABEL[j.leading.mechanism]}</b> <span className="mono">{fmtP(j.leading.p)}</span>
                <span className="faint"> · {MECHANISM_GROUPS.find((g) => g.id === j.leading!.group)!.label.toLowerCase()}</span>
              </>
            ) : (
              <span className="dim">None at or above 0.5</span>
            )}
          </dd>
        </div>
        <div>
          <dt>Posterior entropy</dt>
          <dd className="mono">
            {j.entropy.now.toFixed(2)} <span className="faint">from {j.entropy.start.toFixed(2)}</span>{' '}
            <span className={dH < 0 ? 'is-down' : 'is-up'}>
              {dH < 0 ? '−' : '+'}
              {Math.abs(dH).toFixed(2)}
            </span>
          </dd>
        </div>
        <div>
          <dt>Major unresolved alternative</dt>
          <dd>
            {j.alternative ? (
              <>
                <b>{MECH_LABEL[j.alternative.mechanism]}</b> <span className="mono">{fmtP(j.alternative.p)}</span>
              </>
            ) : (
              <span className="dim">None between 0.1 and 0.9</span>
            )}
          </dd>
        </div>
        <div>
          <dt>Evidence still required</dt>
          <dd>
            {j.required.length === 0 ? (
              <span className="dim">No assay would move an unresolved mechanism.</span>
            ) : (
              <ul className="just__req">
                {j.required.map((r) => (
                  <li key={r.action} title={r.reason}>
                    <span className="chip">{actionShort(r.action)}</span>
                    <span>
                      {actionLabel(r.action)} <span className="faint">→ {r.resolves.map((x) => MECH_LABEL[x.mechanism]).join(', ')}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </dd>
        </div>
        <div>
          <dt>Assay resolved?</dt>
          <dd>
            {v.assay.tested && v.assay.settled ? (
              <>
                <b>Yes</b> <span className="faint">· control run, p(assay invalid) <span className="mono">{fmtP(v.assay.p)}</span></span>
              </>
            ) : v.assay.tested ? (
              <>
                <b>Tested, still open</b> <span className="faint">· p <span className="mono">{fmtP(v.assay.p)}</span></span>
              </>
            ) : (
              <>
                <b>Not tested</b> <span className="faint">· no assay-validity control run yet (p <span className="mono">{fmtP(v.assay.p)}</span>)</span>
              </>
            )}
          </dd>
        </div>
        <div>
          <dt>Model separable?</dt>
          <dd>
            {v.model.settled ? (
              <>
                <b>Yes</b> <span className="faint">· p(model invalid) settled at <span className="mono">{fmtP(v.model.p)}</span></span>
              </>
            ) : (
              <>
                <b>Not yet</b> <span className="faint">· p(model invalid) <span className="mono">{fmtP(v.model.p)}</span> {v.model.tested ? 'after an orthogonal assay' : 'and no orthogonal assay run'}</span>
              </>
            )}
          </dd>
        </div>
        {checks.length > 0 && (
          <>
            <div>
              <dt>Supporting evidence</dt>
              <dd className="just__chips">
                {checks.filter((c) => c.passed).length === 0 ? <span className="dim">None of the evaluator's checks passed.</span> : checks.filter((c) => c.passed).map((c) => <span key={c.name} className="chip chip--support" title={c.detail}>✓ {c.name.replace(/_/g, ' ')}</span>)}
              </dd>
            </div>
            <div>
              <dt>Missing evidence</dt>
              <dd className="just__chips">
                {checks.filter((c) => !c.passed).length === 0 ? <span className="dim">Every check passed.</span> : checks.filter((c) => !c.passed).map((c) => <span key={c.name} className="chip chip--contra" title={c.detail}>✗ {c.name.replace(/_/g, ' ')}</span>)}
              </dd>
            </div>
          </>
        )}
        <div>
          <dt>Terminal evidence threshold</dt>
          <dd>
            {cert ? (
              <span>
                <b>{cert.threshold_met ? 'Met' : 'Not met'}</b>
                {cert.threshold !== undefined && <span className="mono faint"> · threshold {cert.threshold}</span>}
                {cert.rationale && <span className="dim"> · {cert.rationale}</span>}
              </span>
            ) : checks.length > 0 ? (
              <span>
                <b>{checks.filter((c) => c.passed).length} of {checks.length}</b> evaluator checks passed
                <span className="faint"> · evaluator read-out, not a JustificationCertificate</span>
              </span>
            ) : (
              <span className="just__na mono">NOT AVAILABLE · no JustificationCertificate</span>
            )}
          </dd>
        </div>
      </dl>
    </Panel>
  )
}
