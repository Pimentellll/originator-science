import type { CandidateStatus, CockpitState } from '../lib/types'

const STATUS_COLOR: Record<CandidateStatus, string> = {
  current: 'var(--accent)',
  superseded: 'var(--fg-3)',
  selected: 'var(--support)',
  rejected: 'var(--contra)',
  abstained: 'var(--unres)',
}

/** Root → current, left to right. Edge labels name the redesign that created the child. */
export function LineageTrail({ frame }: { frame: CockpitState }) {
  const nodes = frame.lineage
  const W = 300
  const H = 70
  const pad = 30
  const x = (i: number) => (nodes.length === 1 ? W / 2 : pad + (i * (W - 2 * pad)) / (nodes.length - 1))
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img" aria-label={`Lineage: ${nodes.map((n) => n.id).join(' then ')}`} style={{ display: 'block', overflow: 'visible' }}>
      {nodes.slice(1).map((n, i) => (
        <g key={n.id}>
          <line x1={x(i)} x2={x(i + 1)} y1={26} y2={26} stroke="var(--line-3)" strokeWidth="1.2" />
          <text x={(x(i) + x(i + 1)) / 2} y={44} textAnchor="middle" className="lineage__mut">
            {(n.created_by ?? '').replace('REDESIGN_', '').toLowerCase()}
          </text>
          <text x={(x(i) + x(i + 1)) / 2} y={56} textAnchor="middle" className="lineage__sub">
            step {n.step}
          </text>
        </g>
      ))}
      {nodes.map((n, i) => {
        const current = n.id === frame.candidate.id
        return (
          <g key={n.id} transform={`translate(${x(i)},26)`}>
            <circle r={current ? 7 : 5} fill={current ? 'var(--bg-1)' : STATUS_COLOR[n.status]} stroke={STATUS_COLOR[n.status]} strokeWidth={current ? 2 : 1} />
            {current && <circle r="2.4" fill={STATUS_COLOR[n.status]} />}
            <text y={-13} textAnchor="middle" className={`lineage__gen ${current ? 'is-current' : ''}`}>
              g{n.generation}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
