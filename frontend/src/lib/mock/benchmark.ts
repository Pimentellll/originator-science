import type { BenchmarkCell, BenchmarkMetricDef, BenchmarkReportDto } from '../wire'
import { MOCK_PROVENANCE } from './builder'

/**
 * DEV / MOCK benchmark matrix. Deterministic synthetic numbers so the Lab can
 * be built and reviewed. They are NOT results; the UI watermarks them. Some
 * cells are deliberately `not_run` / `na` to exercise those states.
 */
const policies = [
  { name: 'RandomPolicy' },
  { name: 'FixedPipelinePolicy' },
  { name: 'GreedyEIGPolicy' },
  { name: 'PPOPolicy' },
]

const families = [
  { id: 'SINGLE_FAILURE', label: 'Single failure' },
  { id: 'COMPOUND_FAILURE', label: 'Compound failure' },
  { id: 'ASSAY_FAILURE', label: 'Assay failure' },
  { id: 'MODEL_FAILURE', label: 'Model failure' },
  { id: 'MIXED', label: 'Mixed' },
  { id: 'MYOPIC', label: 'Myopic worlds', slice: true },
  { id: 'PATH_DEPENDENT', label: 'Path-dependent worlds', slice: true },
]

const metrics: BenchmarkMetricDef[] = [
  { id: 'terminal_correct', label: 'Terminal correctness', direction: 'higher', max: 1 },
  { id: 'justified', label: 'Justified correctness', direction: 'higher', max: 1 },
  { id: 'decision_calibration_error', label: 'Decision calibration error', direction: 'lower', max: 0.5 },
  { id: 'resource_cost', label: 'Resource cost', direction: 'lower', unit: 'USD', max: 6000 },
  { id: 'sample_use', label: 'Sample use', direction: 'lower', unit: 'µg', max: 520 },
  { id: 'sim_time', label: 'Simulated time', direction: 'lower', unit: 'h', max: 240 },
  { id: 'action_count', label: 'Action count', direction: 'lower', max: 12 },
  { id: 'compound_recognition', label: 'Compound-failure recognition', direction: 'higher', max: 1 },
  { id: 'unnecessary_redesigns', label: 'Unnecessary redesigns', direction: 'lower', max: 3 },
  { id: 'assay_invalid_detection', label: 'Assay-invalid detection', direction: 'higher', max: 1 },
  { id: 'model_invalid_detection', label: 'Model-invalid detection', direction: 'higher', max: 1 },
  { id: 'spr_damage', label: 'SPR damage incurred', direction: 'lower', max: 1 },
  { id: 'proxy_exploitation', label: 'Proxy exploitation (reward-hacking suite)', direction: 'lower', max: 1 },
]

const skill: Record<string, number> = { RandomPolicy: 0.12, FixedPipelinePolicy: 0.4, GreedyEIGPolicy: 0.56, PPOPolicy: 0.7 }
const famMod: Record<string, Record<string, number>> = {
  RandomPolicy: { SINGLE_FAILURE: 0.1 },
  FixedPipelinePolicy: { SINGLE_FAILURE: 0.2, COMPOUND_FAILURE: -0.12, ASSAY_FAILURE: -0.22, PATH_DEPENDENT: -0.1 },
  GreedyEIGPolicy: { SINGLE_FAILURE: 0.18, MYOPIC: 0.12, PATH_DEPENDENT: -0.24, ASSAY_FAILURE: -0.08 },
  PPOPolicy: { SINGLE_FAILURE: 0.1, MYOPIC: -0.06, PATH_DEPENDENT: 0.06 },
}

function hash(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619)
  return ((h >>> 0) % 1000) / 1000
}
const clamp = (x: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, x))
const r = (x: number, d = 2) => +x.toFixed(d)

function cell(policy: string, fam: string, metric: string): BenchmarkCell {
  if (metric === 'proxy_exploitation') return { status: 'not_run' }
  if (policy === 'PPOPolicy' && fam === 'MODEL_FAILURE') return { status: 'not_run' }
  if (metric === 'assay_invalid_detection' && !['ASSAY_FAILURE', 'MIXED'].includes(fam)) return { status: 'na' }
  if (metric === 'model_invalid_detection' && !['MODEL_FAILURE', 'MIXED'].includes(fam)) return { status: 'na' }
  if (metric === 'compound_recognition' && !['COMPOUND_FAILURE', 'MIXED', 'PATH_DEPENDENT'].includes(fam)) return { status: 'na' }

  const noise = (hash(`${policy}|${fam}|${metric}`) - 0.5) * 0.08
  const s = clamp(skill[policy] + (famMod[policy]?.[fam] ?? 0) + noise)
  const n = 24
  const ci = (v: number, w: number): [number, number] => [r(clamp(v - w)), r(clamp(v + w))]
  const ok = (value: number, c?: [number, number]): BenchmarkCell => ({ status: 'ok', value, ...(c ? { ci: c } : {}), n })
  switch (metric) {
    case 'terminal_correct': return ok(r(s), ci(s, 0.16))
    case 'justified': return ok(r(clamp(s - 0.08 - (1 - skill[policy]) * 0.1)), ci(s - 0.1, 0.16))
    case 'decision_calibration_error': return ok(r(clamp(0.34 - s * 0.26, 0.03, 0.5), 3))
    case 'resource_cost': return ok(Math.round(5200 - s * 1500 + noise * 4000))
    case 'sample_use': return ok(Math.round(470 - s * 120 + noise * 600))
    case 'sim_time': return ok(Math.round(210 - s * 60 + noise * 200))
    case 'action_count': return ok(r(clamp(9 - s * 3 + noise * 8, 3, 12), 1))
    case 'compound_recognition':
    case 'assay_invalid_detection':
    case 'model_invalid_detection': return ok(r(clamp(s - 0.15 + noise)), ci(s - 0.15, 0.2))
    case 'unnecessary_redesigns': return ok(r(clamp((1 - s) * 2.2 + noise * 2, 0, 3), 1))
    case 'spr_damage': return ok(r(clamp((1 - s) * 0.8 + (policy === 'GreedyEIGPolicy' ? 0.15 : 0) + noise, 0, 1)))
  }
  return { status: 'not_run' }
}

const cells: BenchmarkReportDto['cells'] = {}
for (const f of families) {
  cells[f.id] = {}
  for (const p of policies) {
    cells[f.id][p.name] = {}
    for (const m of metrics) cells[f.id][p.name][m.id] = cell(p.name, f.id, m.id)
  }
}

export const mockBenchmark: BenchmarkReportDto = {
  status: 'mock',
  provenance: MOCK_PROVENANCE,
  seed_set: 'mock-seed-set (not a held-out set)',
  policies,
  families,
  metrics,
  cells,
}
