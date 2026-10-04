export const fmtP = (p: number) => p.toFixed(2)

export const fmtDelta = (d: number | null) => {
  if (d === null) return '—'
  if (Math.abs(d) < 0.005) return '±0.00'
  return `${d > 0 ? '+' : '−'}${Math.abs(d).toFixed(2)}`
}

/** The API reports budget / sample / time in abstract simulator units, not currency or mass. */
export const fmtNum = (n: number) => (Math.abs(n - Math.round(n)) < 1e-9 ? n.toFixed(1) : n.toFixed(2).replace(/0$/, ''))
export const fmtBudget = fmtNum
export const fmtSample = fmtNum

/** Simulated time stamp, e.g. T+3.5 */
export const fmtT = (t: number) => `T+${fmtNum(t)}`

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
