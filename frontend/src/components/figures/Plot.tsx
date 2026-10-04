import { INK } from './ink'
import type { ReactNode } from 'react'


export type Scale = { x: (v: number) => number; y: (v: number) => number; x0: number; x1: number; y0: number; y1: number }

export function Plot({
  width = 560,
  height = 300,
  xmax = 18,
  ymax,
  yticks,
  xticks,
  ydigits = 1,
  xlabel = 'time (h)',
  ylabel = 'OD600',
  right = 100,
  title,
  children,
}: {
  width?: number
  height?: number
  xmax?: number
  ymax: number
  yticks: number[]
  xticks?: number[]
  ydigits?: number
  xlabel?: string
  ylabel?: string
  right?: number
  title: string
  children: (s: Scale) => ReactNode
}) {
  const m = { l: 46, r: right, t: 12, b: 36 }
  const s: Scale = {
    x: (v) => m.l + (v / xmax) * (width - m.l - m.r),
    y: (v) => height - m.b - (v / ymax) * (height - m.t - m.b),
    x0: m.l,
    x1: width - m.r,
    y0: height - m.b,
    y1: m.t,
  }
  const xt = xticks ?? Array.from({ length: Math.floor(xmax / 3) + 1 }, (_, i) => i * 3)
  return (
    <svg className="fig" viewBox={`0 0 ${width} ${height}`} width="100%" style={{ maxWidth: width }} role="img" aria-label={title}>
      <title>{title}</title>
      {yticks.map((v) => (
        <g key={`y${v}`}>
          <line className="fig__grid" x1={s.x0} x2={s.x1} y1={s.y(v)} y2={s.y(v)} />
          <text x={s.x0 - 8} y={s.y(v) + 4} textAnchor="end">
            {v.toFixed(ydigits)}
          </text>
        </g>
      ))}
      {xt.map((t) => (
        <g key={`x${t}`}>
          <line className="fig__axis" x1={s.x(t)} x2={s.x(t)} y1={s.y0} y2={s.y0 + 4} />
          <text x={s.x(t)} y={s.y0 + 17} textAnchor="middle">
            {t}
          </text>
        </g>
      ))}
      <line className="fig__axis" x1={s.x0} x2={s.x1} y1={s.y0} y2={s.y0} />
      <line className="fig__axis" x1={s.x0} x2={s.x0} y1={s.y1} y2={s.y0} />
      <text x={(s.x0 + s.x1) / 2} y={height - 3} textAnchor="middle">
        {xlabel}
      </text>
      <text transform={`translate(11 ${(s.y1 + s.y0) / 2}) rotate(-90)`} textAnchor="middle">
        {ylabel}
      </text>
      {children(s)}
    </svg>
  )
}

export function Dots({ s, points, fill, stroke = fill, r = 3, tip }: { s: Scale; points: [number, number][]; fill: string; stroke?: string; r?: number; tip?: (p: [number, number]) => string }) {
  return (
    <g>
      {points.map((p, i) => (
        <circle key={i} cx={s.x(p[0])} cy={s.y(p[1])} r={r} fill={fill} stroke={stroke} strokeWidth={1}>
          {tip && <title>{tip(p)}</title>}
        </circle>
      ))}
    </g>
  )
}

export function Line({ s, points, stroke, width = 1.4, dash }: { s: Scale; points: [number, number][]; stroke: string; width?: number; dash?: string }) {
  return <polyline fill="none" stroke={stroke} strokeWidth={width} strokeDasharray={dash} points={points.map(([t, v]) => `${s.x(t)},${s.y(v)}`).join(' ')} />
}

export function HLine({ s, y, stroke, dash = '2 3' }: { s: Scale; y: number; stroke: string; dash?: string }) {
  return <line x1={s.x0} x2={s.x1} y1={s.y(y)} y2={s.y(y)} stroke={stroke} strokeDasharray={dash} />
}

/** Diamonds mark dilution-corrected measurements; `offset` separates points that share a time. */
export function Diamonds({ s, points, fill, stroke = fill, offset, tip }: { s: Scale; points: { t: number; v: number; key: string; tip: string; dx?: number }[]; fill: string; stroke?: string; offset?: number; tip?: boolean }) {
  return (
    <g>
      {points.map((p) => {
        const x = s.x(p.t) + (p.dx ?? 0) * (offset ?? 6)
        const y = s.y(p.v)
        const r = 5
        return (
          <path key={p.key} d={`M${x} ${y - r}L${x + r} ${y}L${x} ${y + r}L${x - r} ${y}Z`} fill={fill} stroke={stroke} strokeWidth={1.2}>
            {tip !== false && <title>{p.tip}</title>}
          </path>
        )
      })}
    </g>
  )
}

export function Label({ s, at, color = INK.ink2, children, anchor = 'start', size = 11.5 }: { s: Scale; at: [number, number]; color?: string; children: ReactNode; anchor?: 'start' | 'middle' | 'end'; size?: number }) {
  return (
    <text className="fig__lab" x={s.x(at[0])} y={s.y(at[1])} textAnchor={anchor} style={{ fill: color, fontSize: size }}>
      {children}
    </text>
  )
}

/** Wilson 95% interval drawn as a horizontal bar on [0, 1] with the point estimate. */
export function CiBar({ k, n, lo, hi }: { k: number; n: number; lo: number | null; hi: number | null }) {
  const w = 70
  const x = (v: number) => 2 + v * (w - 4)
  return (
    <svg className="ci" width={w} height={12} aria-hidden="true">
      <line x1={2} x2={w - 2} y1={6} y2={6} stroke="#b9b09c" strokeWidth={1} />
      {lo !== null && hi !== null && <line x1={x(lo)} x2={x(hi)} y1={6} y2={6} stroke={INK.ink} strokeWidth={2} />}
      {n > 0 && <circle cx={x(k / n)} cy={6} r={2.6} fill={INK.ink} />}
    </svg>
  )
}
