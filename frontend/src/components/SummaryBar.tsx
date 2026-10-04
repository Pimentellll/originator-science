import { useState } from 'react'
import { useSession } from '../state/sessionContext'
import { ModePill, ProvenancePill } from './ui'
import { fmtBudget, fmtSample } from '../lib/format'
import { actionShort, canonicalPolicyKey, policyInfo } from '../lib/actions'

/** One labelled cell of the summary bar. */
function Cell({ label, hint, children, warn }: { label: string; hint?: string; children: React.ReactNode; warn?: boolean }) {
  return (
    <div className={`sum__cell ${warn ? 'sum__cell--warn' : ''}`} title={hint}>
      <span className="hdr__label">{label}</span>
      <b>{children}</b>
    </div>
  )
}

/**
 * Campaign summary for the binder routes. Scenario identity is shown to the HUMAN running the demo
 * as orchestration metadata (the policy never sees it); in guided and manual runs it stays masked
 * until the decision so it cannot spoil the diagnosis.
 */
export function SummaryBar() {
  const s = useSession()
  const f = s.frame
  const live = s.transport.kind === 'live'
  const [seedText, setSeedText] = useState<string | null>(null)
  const [revealed, setRevealed] = useState(false)
  const [open, setOpen] = useState(false)

  const scenarioMap = new Map(s.episodes.map((e) => [e.scenario.id, e.scenario]))
  if (s.scenarioId && !scenarioMap.has(s.scenarioId) && f) scenarioMap.set(s.scenarioId, f.scenario)
  const scenarios = Array.from(scenarioMap.values())
  const forScenario = s.episodes.filter((e) => e.scenario.id === s.scenarioId)
  const policies = Array.from(new Map((forScenario.length ? forScenario : s.episodes).map((e) => [e.policy.name, e.policy])).values())
  const requestedPolicy = s.launch.policy
  const requestedPolicyUnavailable =
    requestedPolicy !== null && s.policyName !== null && !policies.some((p) => canonicalPolicyKey(p.name) === canonicalPolicyKey(requestedPolicy))
  const selectedPolicyLabel = s.policyName
    ? policyInfo(s.policyName).label.toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase())
    : 'Rescue Planner'

  const showSettings = open || requestedPolicyUnavailable || s.phase === 'error'

  const seedValue = seedText ?? String(f?.seed ?? s.launch.seed)
  const seedNum = /^\d+$/.test(seedValue) ? Number(seedValue) : null
  const r = f?.resources
  const terminal = f?.status === 'terminal'
  const masked = (s.launch.control === 'manual' || s.launch.guided) && !terminal && !revealed
  const scenarioName = s.scenarioEntry?.title ?? (s.launch.scenario ? s.launch.scenario.replace(/_/g, ' ').toLowerCase() : 'server default')
  const semantics = f?.semantics ?? s.launch.semantics ?? s.catalogue?.version?.semantics_default ?? null

  const status = s.phase === 'error' ? ['ERROR', 'pill--bad'] : s.phase === 'loading' ? ['LOADING', ''] : s.phase === 'running' ? ['RUNNING', 'pill--warn'] : terminal && f?.terminal ? [`DECIDED · ${actionShort(f.terminal.decision)}`, 'pill--ok'] : ['AWAITING ACTION', 'pill--live']

  return (
    <div className="sum" role="region" aria-label="Campaign summary">
      <Cell label="Status">
        <span className={`pill ${status[1]}`}>{status[0]}</span>
      </Cell>

      {f && r && (
        <>
          <Cell label="Budget" warn={r.budget.remaining / r.budget.total < 0.15} hint="Abstract simulator budget units, not currency.">
            <span className="mono">
              {fmtBudget(r.budget.total - r.budget.remaining)} <small>/ {fmtBudget(r.budget.total)}</small>
            </span>
          </Cell>
        </>
      )}
      {s.launch.control === 'manual' && <span className="pill pill--warn" title="You pick each action; MIRAGE only recommends.">MANUAL SCIENTIST</span>}
      <div className="hdr__spacer" />
      <button type="button" className="sum__toggle" aria-expanded={showSettings} aria-controls="run-settings" onClick={() => setOpen(!open)} title="Policy, scenario, seed and provenance of this run">
        Run settings {showSettings ? '▴' : '▾'}
      </button>
      {showSettings && (
        <div className="sum__settings" id="run-settings">
      <Cell label="Campaign" hint="Scientific profile of the campaign (public).">
        <span className="mono">{f?.campaign ?? '—'}</span>
      </Cell>

      <label className="sum__cell">
        <span className="hdr__label">Policy</span>
        {policies.length > 1 ? (
          <select className="hdr__select" value={s.policyName ?? ''} onChange={(e) => s.selectPolicy(e.target.value)} aria-label="Policy">
            {policies.map((p) => (
              <option key={p.name} value={p.name}>
                {p.label}
              </option>
            ))}
          </select>
        ) : (
          <b>{f?.policy.label ?? '—'}</b>
        )}
      </label>

      {live ? (
        <Cell label="Scenario" hint="Orchestration metadata chosen by the person running the demo. It is NOT policy input and never appears in the public record or replay.">
          {masked ? (
            <span className="sum__masked">
              <span className="mono faint">hidden until decision</span>{' '}
              <button className="sum__link" onClick={() => setRevealed(true)} aria-label="Reveal the scenario (orchestration metadata, not policy input)">
                reveal
              </button>
            </span>
          ) : (
            <>
              {scenarioName} <span className="sum__tag mono">ORCHESTRATION</span>
            </>
          )}
        </Cell>
      ) : (
        <label className="sum__cell">
          <span className="hdr__label">Scenario</span>
          <select className="hdr__select" value={s.scenarioId ?? ''} onChange={(e) => s.selectScenario(e.target.value)} aria-label="Scenario">
            {scenarios.map((sc) => (
              <option key={sc.id} value={sc.id}>
                {sc.title}
              </option>
            ))}
          </select>
        </label>
      )}

      {live ? (
        <form
          className="sum__cell sum__seed"
          onSubmit={(e) => {
            e.preventDefault()
            if (seedNum !== null) {
              s.startCampaign(seedNum)
              setSeedText(null)
              setRevealed(false)
            }
          }}
        >
          <label>
            <span className="hdr__label">Seed</span>
            <input className="hdr__seed mono" inputMode="numeric" value={seedValue} onChange={(e) => setSeedText(e.target.value)} aria-label="Campaign seed" aria-invalid={seedNum === null} />
          </label>
          <button className="btn sum__reset" type="submit" disabled={seedNum === null || s.phase === 'loading'} title="Start a fresh campaign on this seed with the current settings">
            ↻ RESET
          </button>
        </form>
      ) : (
        <Cell label="Seed">
          <span className="mono">{f?.seed ?? '—'}</span>
        </Cell>
      )}

      <Cell label="Semantics" hint="Scenario-semantics version recorded with the episode. BASELINE_V1 is the frozen historical baseline.">
        <span className="mono">{semantics ?? '—'}</span>
      </Cell>

          {f && r && (
            <>
          <Cell label="Sample" hint="Abstract simulator sample units, not mass.">
            <span className="mono">
              {fmtSample(r.sample.total - r.sample.remaining)} <small>/ {fmtSample(r.sample.total)}</small>
            </span>
          </Cell>
          <Cell label="SPR health" warn={r.spr_health < 0.5} hint="SPR instrument health in [0, 1]. A badly behaved sample damages it, which degrades later kinetic readings.">
            <span className="mono">{r.spr_health.toFixed(2)}</span>
          </Cell>
            </>
          )}
      {s.session && <ModePill mode={s.session.mode} />}
      {f && <ProvenancePill provenance={f.provenance} />}
      {!f && s.transport.kind === 'mock' && <span className="pill pill--mock">DEV / MOCK</span>}
        </div>
      )}
      {requestedPolicyUnavailable && (
        <div className="sum__notice" role="status">
          Policy "{requestedPolicy}" isn&apos;t offered by this server; showing {selectedPolicyLabel}.
        </div>
      )}
      {s.phase === 'error' && s.error && (
        <div className="sum__notice" role="alert">
          {s.error}
          {policies.length > 1 && ' Choose another policy from the Policy menu above.'}
        </div>
      )}
    </div>
  )
}
