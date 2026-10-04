import { useState } from 'react'
import { useSession } from '../state/sessionContext'
import type { Route } from '../state/route'
import { ModePill, ProvenancePill } from './ui'
import { fmtBudget, fmtSample, fmtT } from '../lib/format'

const TABS: { id: Route; label: string }[] = [
  { id: 'cockpit', label: 'COCKPIT' },
  { id: 'compare', label: 'COMPARE POLICIES' },
  { id: 'benchmark', label: 'BENCHMARK LAB' },
]

export function Header({ route, navigate }: { route: Route; navigate: (r: Route) => void }) {
  const s = useSession()
  const f = s.frame
  const scenarioMap = new Map(s.episodes.map((e) => [e.scenario.id, e.scenario]))
  // A campaign reset on a custom seed is not in the catalogue; keep it selectable.
  if (s.scenarioId && !scenarioMap.has(s.scenarioId) && f) scenarioMap.set(s.scenarioId, f.scenario)
  const scenarios = Array.from(scenarioMap.values())
  const forScenario = s.episodes.filter((e) => e.scenario.id === s.scenarioId)
  // Live servers register the same policies for every seed, so a custom seed reuses the shared list.
  const policies = Array.from(new Map((forScenario.length ? forScenario : s.episodes).map((e) => [e.policy.name, e.policy])).values())
  const r = f?.resources
  const [seedText, setSeedText] = useState<string | null>(null)
  const seedValue = seedText ?? String(f?.seed ?? s.episodes[0]?.seed ?? '')
  const seedNum = /^\d+$/.test(seedValue) ? Number(seedValue) : null
  const budgetUsed = r ? r.budget.total - r.budget.remaining : 0
  const sampleUsed = r ? r.sample.total - r.sample.remaining : 0

  return (
    <header className="hdr">
      <div className="hdr__brand">
        <span className="hdr__logo">
          MIRAG<i>E</i>
        </span>
        <div className="hdr__tags">
          <span className="hdr__tag1">
            <b>Causal rescue planning</b> for failed de novo extracellular receptor-binding miniproteins
          </span>
          <span className="hdr__tag2 mono">EGFR-inspired receptor-binding campaign · semi-mechanistic synthetic benchmark</span>
        </div>
      </div>
      <nav className="hdr__nav" aria-label="Views">
        {TABS.map((t) => (
          <button key={t.id} className="hdr__tab" aria-current={route === t.id ? 'page' : undefined} onClick={() => navigate(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>

      {s.transport.kind !== 'live' && (
      <label className="hdr__field">
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

      <label className="hdr__field hdr__field--policy">
        <span className="hdr__label">Active policy</span>
        {policies.length > 1 ? (
          <select className="hdr__select" value={s.policyName ?? ''} onChange={(e) => s.selectPolicy(e.target.value)} aria-label="Policy">
            {policies.map((p) => (
              <option key={p.name} value={p.name}>
                {p.label}
              </option>
            ))}
          </select>
        ) : (
          <span className="hdr__static">{f?.policy.label ?? '—'}</span>
        )}
      </label>

      {s.transport.kind === 'live' && (
        <form
          className="hdr__reset"
          onSubmit={(e) => {
            e.preventDefault()
            if (seedNum !== null) {
              s.startCampaign(seedNum)
              setSeedText(null)
            }
          }}
        >
          <label className="hdr__field">
            <span className="hdr__label">Seed</span>
            <input className="hdr__seed mono" inputMode="numeric" value={seedValue} onChange={(e) => setSeedText(e.target.value)} aria-label="Campaign seed" aria-invalid={seedNum === null} />
          </label>
          <button className="btn hdr__resetbtn" type="submit" disabled={seedNum === null || s.phase === 'loading'}>
            ↻ RESET CAMPAIGN
          </button>
        </form>
      )}

      {s.session && <ModePill mode={s.session.mode} />}
      {f?.campaign && (
        <span className="pill pill--campaign" title="Scientific profile">
          {f.campaign}
        </span>
      )}
      {f && <ProvenancePill provenance={f.provenance} />}
      {!f && s.transport.kind === 'mock' && <span className="pill pill--mock">DEV / MOCK</span>}

      <div className="hdr__spacer" />

      {f && r && (
        <div className="hdr__stats" aria-label="Campaign resources">
          <div className={`hdr__stat ${r.budget.remaining / r.budget.total < 0.15 ? 'hdr__stat--warn' : ''}`}>
            <span className="hdr__label">Budget</span>
            <b>
              {fmtBudget(budgetUsed)} <small>/ {fmtBudget(r.budget.total)}</small>
            </b>
          </div>
          <div className="hdr__stat">
            <span className="hdr__label">Sample</span>
            <b>
              {fmtSample(sampleUsed)} <small>/ {fmtSample(r.sample.total)}</small>
            </b>
          </div>
          <div className="hdr__stat">
            <span className="hdr__label">Sim. time</span>
            <b>{fmtT(r.time.elapsed)}</b>
          </div>
          <div className="hdr__stat">
            <span className="hdr__label">Step</span>
            <b>
              {f.step} {f.total_steps !== null && <small>/ {f.total_steps}</small>}
            </b>
          </div>
        </div>
      )}
    </header>
  )
}
