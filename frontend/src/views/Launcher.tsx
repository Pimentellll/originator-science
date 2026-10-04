import { useState } from 'react'
import { useSession } from '../state/sessionContext'
import { GUIDED_PRESET } from '../state/sessionContext'
import type { Route } from '../state/route'
import { CANONICAL_POLICIES, policyInfo } from '../lib/actions'
import type { Control, PolicyEntry } from '../lib/types'

const FLOW = [
  ['FAILURE', 'A de novo binder fails downstream. The cause is unknown.'],
  ['EVIDENCE', 'MIRAGE chooses cheap, informative assays before costly ones.'],
  ['BELIEF', 'A causal belief over molecule, experiment and biological model updates after every result.'],
  ['ACTION', 'It measures, redesigns the molecule, or stops, under a budget.'],
  ['DECISION', 'Select, reject, declare the model invalid, or abstain, and be judged on whether the evidence justified it.'],
] as const

/** Policies as the launcher shows them: wired ones selectable, the rest labelled, never faked. */
function policyRows(catalogue: PolicyEntry[] | null, offered: string[]): PolicyEntry[] {
  if (catalogue) return catalogue
  const rows: PolicyEntry[] = offered.map((name) => ({ name, label: policyInfo(name).label, kind: 'unspecified', available: true, description: policyInfo(name).description ?? '', reason: null }))
  for (const p of CANONICAL_POLICIES) {
    if (p.family === 'mock' || offered.some((o) => policyInfo(o).label === p.label)) continue
    rows.push({ name: p.key, label: p.label, kind: 'unspecified', available: false, description: '', reason: 'Not served by this backend.' })
  }
  return rows
}

export function Launcher({ navigate }: { navigate: (r: Route, ...p: string[]) => void }) {
  const s = useSession()
  const live = s.transport.kind === 'live'
  const scenarios = s.catalogue?.scenarios ?? null
  const offered = [...new Set(s.episodes.map((e) => e.policy.name))]
  const policies = policyRows(s.catalogue?.policies ?? null, offered)
  const semanticsOptions = s.catalogue?.version?.semantics_available ?? ['SEMANTICS_V2', 'BASELINE_V1']

  const defaultScenario = scenarios?.find((x) => x.is_default)?.id ?? null
  const [scenario, setScenario] = useState<string | null>(() => s.launch.scenario)
  const [policy, setPolicy] = useState<string | null>(() => s.launch.policy)
  const [semantics, setSemantics] = useState<string>(() => s.launch.semantics ?? s.catalogue?.version?.semantics_default ?? 'SEMANTICS_V2')
  const [seedText, setSeedText] = useState(String(s.launch.seed))
  const [control, setControl] = useState<Control>(s.launch.control)

  const seed = /^\d+$/.test(seedText) ? Number(seedText) : null
  const chosenScenario = scenarios?.find((x) => x.id === scenario || x.cli_name === scenario)?.id ?? scenario ?? defaultScenario
  const chosenPolicy = policy ?? (policies.find((p) => p.available && p.name === 'rescue_planner') ?? policies.find((p) => p.available))?.name ?? null
  const ready = live && s.phase !== 'error' && seed !== null && chosenPolicy !== null

  const start = (guided: boolean) => {
    if (guided) s.launchCampaign({ ...GUIDED_PRESET, guided: true })
    else s.launchCampaign({ scenario: chosenScenario, semantics, policy: chosenPolicy, seed: seed ?? 9, control, guided: false })
    navigate('cockpit')
  }

  return (
    <div className="launch">
      <div className="launch__scroll">
        <section className="launch__hero" aria-labelledby="launch-h">
          <p className="launch__eyebrow mono">EGFR-INSPIRED RECEPTOR-BINDER CAMPAIGN · SYNTHETIC, SEMI-MECHANISTIC BENCHMARK</p>
          <h1 id="launch-h">A binder failed. Is the molecule broken, the assay, or the biology?</h1>
          <p className="launch__lead">
            MIRAGE chooses experiments, keeps a causal belief about <b>why</b> the campaign failed, and is scored on whether its final call was not just <b>correct</b> but <b>justified</b> by the evidence it collected.
          </p>
          <ol className="launch__flow" aria-label="How a campaign runs">
            {FLOW.map(([k, text], i) => (
              <li key={k}>
                <span className="launch__fidx mono">{i + 1}</span>
                <b>{k}</b>
                <span>{text}</span>
              </li>
            ))}
          </ol>
          <div className="launch__cta">
            <button className="btn btn--primary launch__guided" onClick={() => start(true)} disabled={!live || s.phase === 'error'}>
              ▶ START GUIDED DEMO
            </button>
            <span className="dim">About 30 seconds · fixed seed 9 · a real simulated run, explained step by step. Nothing is scripted.</span>
          </div>
        </section>

        {!live && (
          <p className="launch__note" role="status">
            This session is using <b>{s.transport.label}</b> data, which has no live launcher. Open <span className="mono">?transport=live</span> against a running API to start campaigns, or use the Cockpit tab to browse the recorded episodes.
          </p>
        )}
        {s.phase === 'error' && (
          <div className="state launch__err" role="alert">
            <b>Cannot reach the MIRAGE API</b>
            <pre>{s.error}</pre>
            <span>
              Start everything with <span className="mono">./mirage demo</span>, or check <a href="#/diagnostics">System check</a>.
            </span>
          </div>
        )}

        <section className="launch__form" aria-label="Campaign setup">
          <fieldset className="launch__fs">
            <legend>1 · Scenario</legend>
            {scenarios ? (
              <div className="launch__cards" role="radiogroup" aria-label="Scenario">
                {scenarios.map((sc) => {
                  const on = chosenScenario === sc.id
                  return (
                    <label key={sc.id} className={`lcard ${on ? 'is-on' : ''}`}>
                      <input type="radio" name="scenario" value={sc.id} checked={on} onChange={() => setScenario(sc.id)} />
                      <b>{sc.title}</b>
                      <span>{sc.summary}</span>
                    </label>
                  )
                })}
              </div>
            ) : (
              <p className="dim launch__empty">{s.catalogueState === 'loading' ? 'Loading scenarios…' : 'This server offers no scenario catalogue; it runs its own default scenario.'}</p>
            )}
            <p className="launch__hint">The scenario is chosen by <b>you</b> and is orchestration metadata. It is never shown to the policy and never stored in the public record. Guided and manual runs hide it until the decision.</p>
          </fieldset>

          <fieldset className="launch__fs">
            <legend>2 · Policy</legend>
            <div className="launch__policies" role="radiogroup" aria-label="Policy">
              {policies.map((p) => {
                const on = chosenPolicy === p.name && p.available
                return (
                  <label key={p.name} className={`lpol ${on ? 'is-on' : ''} ${p.available ? '' : 'is-off'}`} title={p.available ? p.description : (p.reason ?? 'Not available')}>
                    <input type="radio" name="policy" value={p.name} checked={on} disabled={!p.available} onChange={() => setPolicy(p.name)} />
                    <b>{p.label}</b>
                    {p.available ? <span>{p.description}</span> : <span className="pill lpol__na">NOT AVAILABLE</span>}
                    {!p.available && p.reason && <span className="lpol__why">{p.reason}</span>}
                  </label>
                )
              })}
            </div>
          </fieldset>

          <fieldset className="launch__fs launch__fs--row">
            <legend>3 · Run</legend>
            <label className="launch__field">
              <span className="hdr__label">Seed</span>
              <input className="hdr__seed mono" inputMode="numeric" value={seedText} onChange={(e) => setSeedText(e.target.value)} aria-invalid={seed === null} aria-label="Campaign seed" />
            </label>
            <label className="launch__field">
              <span className="hdr__label">Scenario semantics</span>
              <select className="hdr__select" value={semantics} onChange={(e) => setSemantics(e.target.value)} aria-label="Scenario semantics version">
                {semanticsOptions.map((v) => (
                  <option key={v} value={v}>
                    {v}
                    {v === 'BASELINE_V1' ? ' (frozen baseline)' : ''}
                  </option>
                ))}
              </select>
            </label>
            <div className="launch__field" role="radiogroup" aria-label="Who decides">
              <span className="hdr__label">Who decides</span>
              <div className="seg">
                <label className={control === 'auto' ? 'is-on' : ''}>
                  <input type="radio" name="control" checked={control === 'auto'} onChange={() => setControl('auto')} />
                  AUTO POLICY
                </label>
                <label className={control === 'manual' ? 'is-on' : ''}>
                  <input type="radio" name="control" checked={control === 'manual'} onChange={() => setControl('manual')} />
                  MANUAL SCIENTIST
                </label>
              </div>
            </div>
          </fieldset>

          <div className="launch__actions">
            <button className="btn btn--primary" onClick={() => start(false)} disabled={!ready}>
              START CAMPAIGN
            </button>
            <button className="btn" onClick={() => start(true)} disabled={!live || s.phase === 'error'}>
              GUIDED DEMO
            </button>
            <span className="dim">
              {control === 'manual' ? 'You choose every action; MIRAGE only recommends. Then compare.' : 'The selected policy runs the campaign; step through it in the cockpit.'}
            </span>
          </div>
        </section>
      </div>
    </div>
  )
}
