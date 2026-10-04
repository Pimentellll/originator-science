import { useSession } from '../state/sessionContext'
import { Panel } from './ui'
import { justification } from '../lib/derive'
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

  return (
    <Panel
      index="02"
      title="Is this conclusion justified?"
      className="just"
      aside={cert ? <span className={`pill ${cert.threshold_met ? 'pill--ok' : 'pill--bad'}`}>{cert.threshold_met ? 'THRESHOLD MET' : 'NOT MET'}</span> : <span className="pill">NO CERTIFICATE</span>}
    >
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
          <dt>Terminal evidence threshold</dt>
          <dd>
            {cert ? (
              <span>
                <b>{cert.threshold_met ? 'Met' : 'Not met'}</b>
                {cert.threshold !== undefined && <span className="mono faint"> · threshold {cert.threshold}</span>}
                {cert.rationale && <span className="dim"> · {cert.rationale}</span>}
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
