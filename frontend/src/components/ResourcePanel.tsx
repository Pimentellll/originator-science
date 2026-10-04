import { useSession } from '../state/sessionContext'
import { Meter, Panel } from './ui'
import { fmtMoney, fmtT } from '../lib/format'

export function ResourcePanel() {
  const { frame } = useSession()
  if (!frame) return <Panel index="05" title="Resources">{null}</Panel>
  const r = frame.resources
  const next = frame.recommendation?.cost
  const budgetUsed = r.budget.total - r.budget.remaining
  const sampleUsed = r.sample.total - r.sample.remaining
  const left = r.budget.remaining / r.budget.total
  const spr = r.spr_health
  const sprState = spr >= 0.8 ? 'good' : spr >= 0.5 ? 'accent' : 'warn'

  return (
    <Panel index="05" title="Resources" className="res">
      <div className="res__meters">
        <Meter
          label="BUDGET USED"
          value={<>{fmtMoney(budgetUsed)} <small>/ {fmtMoney(r.budget.total)}</small></>}
          fraction={budgetUsed / r.budget.total}
          ghost={next?.budget !== undefined ? next.budget / r.budget.total : 0}
          tone={left < 0.15 ? 'warn' : 'default'}
        />
        <Meter label="SAMPLE USED" value={<>{sampleUsed} <small>/ {r.sample.total} µg</small></>} fraction={sampleUsed / r.sample.total} ghost={next?.sample !== undefined ? next.sample / r.sample.total : 0} />
        <div className="meter">
          <div className="meter__row">
            <span>SIMULATED TIME</span>
            <b>{fmtT(r.time.elapsed)}</b>
          </div>
        </div>
      </div>
      <div className="res__spr">
        <Meter
          label="SPR INSTRUMENT HEALTH"
          value={<span className={spr < 0.5 ? 'res__bad' : ''}>{spr.toFixed(2)}</span>}
          fraction={spr}
          tone={sprState}
        />
        <p className="res__hint">
          {spr >= 0.9
            ? 'Instrument nominal. Later SPR readings are reliable.'
            : spr >= 0.5
              ? 'Degraded. Later SPR readings are less reliable.'
              : 'Damaged. Later SPR readings cannot be trusted; kinetic evidence is compromised.'}
        </p>
      </div>
      <p className="res__ghost">
        <i /> hatched = projected cost of the recommended action
      </p>
    </Panel>
  )
}
