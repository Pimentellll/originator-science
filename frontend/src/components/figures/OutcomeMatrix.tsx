import { outcome } from '../../lib/growth/analysis'
import type { GrowthGrid } from '../../lib/growth/types'
import {} from './Plot'
import { INK } from './ink'

/** Episodes × agents; fill encodes outcome without relying on colour alone. */
export function OutcomeMatrix({
  grid,
  labels,
  onOpen,
}: {
  grid: GrowthGrid
  labels: string[]
  onOpen: (runId: string, episodeId: string) => void
}) {
  const cs = 22
  const L = 168
  const W = L + grid.rows.length * cs + 10
  const H = 26 + grid.columns.length * cs + 4
  return (
    <svg className="fig" viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: W }} role="img" aria-label="Outcome of every scored episode for every agent">
      <defs>
        <pattern id="om-hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="4" height="4" fill={INK.paper} />
          <line x1="0" y1="0" x2="0" y2="4" stroke={INK.red} strokeWidth="2" />
        </pattern>
      </defs>
      {grid.columns.map((c, a) => (
        <text key={c.run_id} x={0} y={22 + a * cs + cs / 2 + 2} style={{ fontSize: 12, fill: INK.ink }}>
          {labels[a]}
        </text>
      ))}
      {grid.rows.map((r, i) => {
        const x = L + i * cs
        return (
          <g key={r.episode_id}>
            <text x={x + cs / 2 - 1} y={14} textAnchor="middle" style={{ fill: INK.mute }}>
              {r.condition === 'BIOLOGICAL_PLATEAU' ? 'P' : 'S'}
            </text>
            {grid.columns.map((c, a) => {
              const cell = r.cells[c.run_id]
              const o = cell ? outcome(cell) : 'none'
              const q = cs - 6
              const xx = x + 2
              const yy = 22 + a * cs + 2
              const label = `${r.episode_id} · ${labels[a]} · ${o === 'none' ? 'no diagnosis' : o === 'wrong' ? 'wrong' : o === 'justified' ? 'correct and justified' : 'correct, not justified'}`
              return (
                <g
                  key={c.run_id}
                  role="button"
                  tabIndex={0}
                  aria-label={label}
                  onClick={() => onOpen(c.run_id, r.episode_id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      onOpen(c.run_id, r.episode_id)
                    }
                  }}
                >
                  <title>{label}</title>
                  <rect x={x} y={yy - 2} width={cs} height={cs} fill="transparent" />
                  {o === 'justified' && <rect x={xx} y={yy} width={q} height={q} fill={INK.ink} />}
                  {o === 'unjustified' && <rect x={xx} y={yy} width={q} height={q} fill="url(#om-hatch)" stroke={INK.red} />}
                  {o === 'wrong' && <rect x={xx + 0.75} y={yy + 0.75} width={q - 1.5} height={q - 1.5} fill={INK.paper} stroke={INK.red} strokeWidth={1.5} />}
                  {o === 'none' && <rect x={xx} y={yy} width={q} height={q} fill="none" stroke={INK.mute} strokeDasharray="2 2" />}
                </g>
              )
            })}
          </g>
        )
      })}
    </svg>
  )
}
