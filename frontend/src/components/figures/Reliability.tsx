import type { ReliabilityBin } from '../../lib/growth/analysis'
import {} from './Plot'
import { INK } from './ink'

/** Reliability diagram: mean stated P(above reading) against observed frequency, marker area ∝ n. */
export function Reliability({ bins, title, size = 200 }: { bins: ReliabilityBin[]; title: string; size?: number }) {
  const m = { l: 34, r: 8, t: 8, b: 30 }
  const W = size
  const H = size
  const X = (v: number) => m.l + v * (W - m.l - m.r)
  const Y = (v: number) => H - m.b - v * (H - m.t - m.b)
  const total = bins.reduce((s, b) => s + b.n, 0) || 1
  const ticks = [0, 0.5, 1]
  return (
    <svg className="fig" viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: W }} role="img" aria-label={title}>
      <title>{title}</title>
      {ticks.map((v) => (
        <g key={v}>
          <line className="fig__grid" x1={X(0)} x2={X(1)} y1={Y(v)} y2={Y(v)} />
          <text x={m.l - 6} y={Y(v) + 4} textAnchor="end">
            {v}
          </text>
          <text x={X(v)} y={H - m.b + 15} textAnchor="middle">
            {v}
          </text>
        </g>
      ))}
      <line className="fig__axis" x1={X(0)} x2={X(1)} y1={Y(0)} y2={Y(0)} />
      <line className="fig__axis" x1={X(0)} x2={X(0)} y1={Y(1)} y2={Y(0)} />
      <line x1={X(0)} y1={Y(0)} x2={X(1)} y2={Y(1)} stroke={INK.mute} strokeDasharray="3 3" />
      <text x={(X(0) + X(1)) / 2} y={H - 3} textAnchor="middle">
        stated P(above reading)
      </text>
      {bins.map((b) =>
        b.n && b.meanP !== null && b.observed !== null ? (
          <circle key={b.lo} cx={X(b.meanP)} cy={Y(b.observed)} r={2.5 + 7 * Math.sqrt(b.n / total)} fill={INK.ink} fillOpacity={0.85} stroke={INK.paper}>
            <title>{`P in [${b.lo.toFixed(1)}, ${b.hi.toFixed(1)}${b.hi === 1 ? ']' : ')'}: n = ${b.n}, mean P = ${b.meanP.toFixed(2)}, observed saturation = ${b.observed.toFixed(2)}`}</title>
          </circle>
        ) : null,
      )}
    </svg>
  )
}
