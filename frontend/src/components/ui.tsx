import { useEffect } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import type { Provenance, SessionMode } from '../lib/types'

export function Panel({
  index,
  title,
  aside,
  children,
  className = '',
  style,
  bodyClass = '',
}: {
  index: string
  title: string
  aside?: ReactNode
  children: ReactNode
  className?: string
  style?: CSSProperties
  bodyClass?: string
}) {
  return (
    <section className={`panel ${className}`} style={style} aria-label={title}>
      <header className="panel__hd">
        <span className="panel__idx">{index}</span>
        <span className="panel__title">{title}</span>
        {aside && <span className="panel__aside">{aside}</span>}
      </header>
      <div className={`panel__body ${bodyClass}`}>{children}</div>
    </section>
  )
}

export function ModePill({ mode }: { mode: SessionMode }) {
  return mode === 'live' ? (
    <span className="pill pill--live" title="Connected to a running episode">
      <i />
      LIVE
    </span>
  ) : (
    <span className="pill pill--replay" title="Playing back a recorded episode">
      REPLAY
    </span>
  )
}

/** Shown whenever data does not come from the real backend. */
export function ProvenancePill({ provenance }: { provenance: Provenance }) {
  if (provenance.source === 'live') return null
  if (provenance.source === 'mock')
    return (
      <span className="pill pill--mock" title={provenance.label}>
        DEV / MOCK
      </span>
    )
  return (
    <span className="pill" title={provenance.label}>
      RECORDED
    </span>
  )
}

export function Meter({
  label,
  value,
  fraction,
  ghost,
  tone = 'default',
}: {
  label: string
  value: ReactNode
  fraction: number
  /** Projected extra share (e.g. cost of the recommended action). */
  ghost?: number
  tone?: 'default' | 'warn' | 'accent' | 'good'
}) {
  const f = Math.max(0, Math.min(1, fraction))
  const g = ghost ? Math.min(ghost, 1 - f) : 0
  const cls = tone === 'default' ? '' : `meter--${tone}`
  return (
    <div className={`meter ${cls}`}>
      <div className="meter__row">
        <span>{label}</span>
        <b>{value}</b>
      </div>
      <div className="meter__track" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={1} aria-valuenow={+f.toFixed(3)}>
        <div className="meter__fill" style={{ width: `${f * 100}%` }} />
        {g > 0 && <div className="meter__ghost" style={{ left: `${f * 100}%`, width: `${g * 100}%` }} />}
      </div>
    </div>
  )
}

export function Modal({ title, onClose, children, badge }: { title: string; onClose: () => void; children: ReactNode; badge?: ReactNode }) {
  useEffect(() => {
    const on = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', on)
    return () => window.removeEventListener('keydown', on)
  }, [onClose])
  return (
    <div className="scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal__hd">
          <h2>{title}</h2>
          {badge}
          <button className="modal__x" onClick={onClose}>
            CLOSE · ESC
          </button>
        </div>
        <div className="modal__bd">{children}</div>
      </div>
    </div>
  )
}

export function Sparkline({
  values,
  width = 120,
  height = 28,
  max,
  marker,
  className,
}: {
  values: number[]
  width?: number
  height?: number
  max: number
  /** Index to ring. */
  marker?: number
  className?: string
}) {
  if (values.length === 0) return null
  const pad = 3
  const x = (i: number) => pad + (values.length === 1 ? 0 : (i / (values.length - 1)) * (width - 2 * pad))
  const y = (v: number) => height - pad - (Math.min(v, max) / max) * (height - 2 * pad)
  const d = values.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  const m = marker ?? values.length - 1
  return (
    <svg className={className} width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="trend">
      <line x1={pad} x2={width - pad} y1={height - pad} y2={height - pad} stroke="var(--line-2)" />
      <path d={d} fill="none" stroke="var(--fg-1)" strokeWidth="1.25" />
      {values[m] !== undefined && <circle cx={x(m)} cy={y(values[m])} r="2.6" fill="var(--bg-1)" stroke="var(--accent)" strokeWidth="1.4" />}
    </svg>
  )
}
