import { useSession } from '../state/sessionContext'
import { Meter, Panel } from './ui'
import { fmtBudget, fmtSample, fmtT } from '../lib/format'
import { canonicalPolicyKey } from '../lib/actions'
import type { CockpitState, PolicyComparison } from '../lib/types'

/** The fixed pipeline's real, completed run on this seed, only when this run is complete too. */
function fixedPipelineComparison(frame: CockpitState, cmp: PolicyComparison | null | undefined) {
  if (!cmp || frame.status !== 'terminal' || canonicalPolicyKey(frame.policy.name) === 'fixed_pipeline') return null
  const track = cmp.tracks.find((t) => canonicalPolicyKey(t.policy.name) === 'fixed_pipeline')
  const last = track?.frames.at(-1)
  if (!last || last.status !== 'terminal' || last.seed !== frame.seed) return null
  return { budget: last.resources.budget.total - last.resources.budget.remaining, experiments: last.events.filter((e) => e.kind === 'measurement').length }
}

export function ResourcePanel() {
  const { frame, comparison } = useSession()
  if (!frame) return <Panel index="05" title="Resources">{null}</Panel>
  const r = frame.resources
  const next = frame.recommendation?.cost
  const budgetUsed = r.budget.total - r.budget.remaining
  const sampleUsed = r.sample.total - r.sample.remaining
  const left = r.budget.remaining / r.budget.total
  const spr = r.spr_health
  const experiments = frame.events.filter((e) => e.kind === 'measurement').length
  const redesigns = frame.events.filter((e) => e.kind === 'redesign').length
  const fixed = fixedPipelineComparison(frame, comparison)
  const sprState = spr >= 0.8 ? 'good' : spr >= 0.5 ? 'accent' : 'warn'

  return (
    <Panel index="05" title="Resources" className="res">
      <div className="res__meters">
        <Meter
          label="BUDGET USED"
          value={<>{fmtBudget(budgetUsed)} <small>/ {fmtBudget(r.budget.total)}</small></>}
          fraction={budgetUsed / r.budget.total}
          ghost={next?.budget !== undefined ? next.budget / r.budget.total : 0}
          tone={left < 0.15 ? 'warn' : 'default'}
        />
        <Meter label="SAMPLE USED" value={<>{fmtSample(sampleUsed)} <small>/ {fmtSample(r.sample.total)}</small></>} fraction={sampleUsed / r.sample.total} ghost={next?.sample !== undefined ? next.sample / r.sample.total : 0} />
        <div className="res__counts">
          <div className="meter" title="Simulated campaign time in model units. It is not laboratory hours.">
            <div className="meter__row">
              <span>SIMULATED CAMPAIGN TIME</span>
              <b>{fmtT(r.time.elapsed)}</b>
            </div>
          </div>
          <div className="meter">
            <div className="meter__row">
              <span>EXPERIMENTS</span>
              <b>{experiments}</b>
            </div>
          </div>
          <div className="meter">
            <div className="meter__row">
              <span>REDESIGNS</span>
              <b>{redesigns}</b>
            </div>
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
      {fixed && (
        <p className="res__cmp" title="From the real fixed-pipeline run on this exact seed, played through the same public API.">
          vs <b>FIXED PIPELINE</b> (same seed, real run):{' '}
          <span className="mono">
            budget {fmtBudget(fixed.budget)} · {fixed.experiments} experiments
          </span>
          . This run: <span className="mono">{fmtBudget(budgetUsed)} · {experiments}</span>.
        </p>
      )}
      <p className="res__ghost">
        <i /> hatched = projected cost of the recommended action
      </p>
    </Panel>
  )
}
