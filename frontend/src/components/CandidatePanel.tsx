import { useSession } from '../state/sessionContext'
import { Panel } from './ui'
import { LineageTrail } from './LineageTrail'
import { dossier } from '../lib/derive'
import { actionShort, formatMeasurement, isPoorQuality, measurementLabel } from '../lib/actions'
import type { CandidateStatus } from '../lib/types'

const STATUS: Record<CandidateStatus, { label: string; cls: string }> = {
  current: { label: 'ACTIVE', cls: 'pill--warn' },
  superseded: { label: 'SUPERSEDED', cls: '' },
  selected: { label: 'SELECTED', cls: 'pill--ok' },
  rejected: { label: 'REJECTED', cls: 'pill--bad' },
  abstained: { label: 'ABSTAINED', cls: '' },
}

export function CandidatePanel() {
  const { frame, select, selection } = useSession()
  if (!frame) return <Panel index="01" title="Candidate">{null}</Panel>
  const c = frame.candidate
  const st = STATUS[c.status]
  // Newest candidate first, so what the policy knows about the active molecule leads.
  const ids = [...frame.lineage].reverse().map((l) => l.id)
  const hasAny = ids.some((id) => dossier(frame, id).length > 0)

  return (
    <Panel index="01" title="Candidate" aside={<span className={`pill ${st.cls}`}>{st.label}</span>} className="cand">
      <div className="cand__id">
        <div className="cand__name mono">{c.id}</div>
        <div className="cand__sub mono">
          GEN {c.generation} · {c.parent_id ? `parent ${c.parent_id}` : 'original design'}
          {c.created_by && ` · ${c.created_by.replace('REDESIGN_', 'redesign ').toLowerCase()}`}
        </div>
      </div>

      <div className="cand__sec">
        <h3>Lineage</h3>
        <LineageTrail frame={frame} />
      </div>

      <div className="cand__sec">
        <h3>
          Measurements <span className="faint">· public assay readouts per candidate</span>
        </h3>
        {!hasAny && <p className="cand__empty">Nothing measured yet. The only evidence is the observed downstream failure.</p>}
        {ids.map((id) => {
          const rows = dossier(frame, id)
          if (rows.length === 0) return null
          return (
            <div key={id} className="dos">
              <div className={`dos__id mono ${id === c.id ? 'is-active' : ''}`}>{id}</div>
              {rows.map((r) => (
                <button key={r.step} className={`dos__row ${selection === `s${r.step}:obs` ? 'is-selected' : ''}`} onClick={() => select(selection === `s${r.step}:obs` ? null : `s${r.step}:obs`)}>
                  <span className="dos__act mono">{actionShort(r.action_type)}</span>
                  <span className="dos__m">
                    {r.measurements.map((m) => (
                      <span key={m.name} className="dos__kv">
                        <span className="dim">{measurementLabel(m.name)}</span> <b className="mono">{formatMeasurement(m.name, m.value)}</b>
                      </span>
                    ))}
                  </span>
                  <span className={`dos__q ${isPoorQuality(r.quality) ? 'is-poor' : ''}`}>{r.quality}</span>
                </button>
              ))}
            </div>
          )
        })}
      </div>

      <div className="cand__sec cand__note">
        Synthetic benchmark candidate. Identifiers and lineage are public; sequence, structure and molecular parameters are not part of the contract, and nothing here is a validated binder or a therapeutic claim.
      </div>
    </Panel>
  )
}
