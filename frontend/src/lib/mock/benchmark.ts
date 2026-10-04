import type { BenchmarkCell, BenchmarkReportDto } from '../wire'
import { BENCHMARK_METRICS } from '../fromApi'
import { MOCK_PROVENANCE } from './builder'

/**
 * DEV / MOCK benchmark matrix. Deterministic synthetic numbers so the Lab can be
 * built and reviewed. They are NOT results; the UI watermarks them.
 *
 * Only Random / Fixed / Greedy have mock numbers. Lookahead and PPO are absent, so the
 * Lab shows them as NOT RUN: no checkpoint or artifact exists, and none is invented here.
 * Metrics newer than the mock's "evaluator version" are likewise absent (NOT RUN).
 */
const policies = [{ name: 'RandomPolicy' }, { name: 'FixedPipelinePolicy' }, { name: 'GreedyEIGPolicy' }]

const families = [
  { id: 'class:SINGLE_FAILURE', label: 'Single failure' },
  { id: 'class:COMPOUND_FAILURE', label: 'Compound failure' },
  { id: 'class:ASSAY_FAILURE', label: 'Assay failure' },
  { id: 'class:MODEL_FAILURE', label: 'Model failure' },
  { id: 'class:MIXED', label: 'Mixed' },
  { id: 'regime:myopic', label: 'Myopic worlds', slice: true },
  { id: 'regime:path_dependent', label: 'Path-dependent worlds', slice: true },
]

/** The first 13 real metrics; the rest are "newer than this mock" and stay NOT RUN. */
const MOCKED = new Set(BENCHMARK_METRICS.slice(0, 14).map((m) => m.id))

const skill: Record<string, number> = { RandomPolicy: 0.12, FixedPipelinePolicy: 0.4, GreedyEIGPolicy: 0.56 }
const famMod: Record<string, Record<string, number>> = {
  RandomPolicy: { 'class:SINGLE_FAILURE': 0.1 },
  FixedPipelinePolicy: { 'class:SINGLE_FAILURE': 0.2, 'class:COMPOUND_FAILURE': -0.12, 'class:ASSAY_FAILURE': -0.22, 'regime:path_dependent': -0.1 },
  GreedyEIGPolicy: { 'class:SINGLE_FAILURE': 0.18, 'regime:myopic': 0.12, 'regime:path_dependent': -0.24, 'class:ASSAY_FAILURE': -0.08 },
}

function hash(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619)
  return ((h >>> 0) % 1000) / 1000
}
const clamp = (x: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, x))
const r = (x: number, d = 2) => +x.toFixed(d)

function cell(policy: string, fam: string, metric: string): BenchmarkCell {
  if (!MOCKED.has(metric)) return { status: 'not_run' }
  if (metric === 'assay_invalid_detected' && !['class:ASSAY_FAILURE', 'class:MIXED'].includes(fam)) return { status: 'na' }
  if (metric === 'model_invalid_detected' && !['class:MODEL_FAILURE', 'class:MIXED'].includes(fam)) return { status: 'na' }
  if (metric === 'compound_recognized' && !['class:COMPOUND_FAILURE', 'class:MIXED', 'regime:path_dependent'].includes(fam)) return { status: 'na' }

  const noise = (hash(`${policy}|${fam}|${metric}`) - 0.5) * 0.08
  const s = clamp(skill[policy] + (famMod[policy]?.[fam] ?? 0) + noise)
  const n = 24
  const ci = (v: number, w: number): [number, number] => [r(clamp(v - w)), r(clamp(v + w))]
  const ok = (value: number, c?: [number, number]): BenchmarkCell => ({ status: 'ok', value, ...(c ? { ci: c } : {}), n })
  switch (metric) {
    case 'correct': return ok(r(s), ci(s, 0.16))
    case 'justified': return ok(r(clamp(s - 0.08 - (1 - skill[policy]) * 0.1)), ci(s - 0.1, 0.16))
    case 'lucky_correct': return ok(r(clamp(0.12 + (1 - s) * 0.2 + noise)), ci(0.15, 0.1))
    case 'decision_calibration_error': return ok(r(clamp(0.34 - s * 0.26, 0.03, 0.5), 3))
    case 'budget_spent': return ok(r(clamp(11 - s * 4 + noise * 6, 2, 12), 1))
    case 'sample_used': return ok(r(clamp(7 - s * 2.5 + noise * 4, 1, 8), 1))
    case 'time_elapsed': return ok(r(clamp(9 - s * 3 + noise * 4, 2, 12), 1))
    case 'action_count': return ok(r(clamp(9 - s * 3 + noise * 8, 3, 12), 1))
    case 'compound_recognized':
    case 'assay_invalid_detected':
    case 'model_invalid_detected': return ok(r(clamp(s - 0.15 + noise)), ci(s - 0.15, 0.2))
    case 'unnecessary_redesign_episodes': return ok(r(clamp((1 - s) * 0.6 + noise)))
    case 'spr_health_lost': return ok(r(clamp((1 - s) * 0.6 + (policy === 'GreedyEIGPolicy' ? 0.15 : 0) + noise, 0, 1)))
    case 'premature_aggregated_spr': return ok(r(clamp((1 - s) * 0.8 + (policy === 'GreedyEIGPolicy' ? 0.2 : 0) + noise)))
  }
  return { status: 'not_run' }
}

const cells: BenchmarkReportDto['cells'] = {}
for (const f of families) {
  cells[f.id] = {}
  for (const p of policies) {
    cells[f.id][p.name] = {}
    for (const m of BENCHMARK_METRICS) cells[f.id][p.name][m.id] = cell(p.name, f.id, m.id)
  }
}

export const mockBenchmark: BenchmarkReportDto = {
  status: 'mock',
  provenance: MOCK_PROVENANCE,
  seed_set: 'mock-seed-set (not a held-out set)',
  policies,
  families,
  metrics: BENCHMARK_METRICS,
  cells,
}
