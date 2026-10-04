export const fmtP = (p: number) => p.toFixed(2)

export const fmtDelta = (d: number | null) => {
  if (d === null) return '—'
  if (Math.abs(d) < 0.005) return '±0.00'
  return `${d > 0 ? '+' : '−'}${Math.abs(d).toFixed(2)}`
}

export const fmtMoney = (n: number, currency = 'USD') => {
  const sym = currency === 'USD' ? '$' : ''
  return `${sym}${Math.round(n).toLocaleString('en-US')}`
}

export const fmtHours = (h: number) => `${Math.round(h)} h`

/** Simulated time stamp, e.g. T+078h */
export const fmtT = (h: number) => `T+${String(Math.round(h)).padStart(3, '0')}h`

export const fmtBits = (b: number | undefined) => (b === undefined ? '—' : `${b.toFixed(2)} bit`)

export const pct = (x: number) => `${Math.round(x * 100)}%`

export const MECH_LABEL: Record<string, string> = {
  folding: 'Folding',
  aggregation: 'Aggregation',
  affinity: 'Affinity',
  kinetic: 'Kinetics',
  epitope: 'Epitope',
  developability: 'Developability',
  assay_invalid: 'Assay invalid',
  model_invalid: 'Model invalid',
}
