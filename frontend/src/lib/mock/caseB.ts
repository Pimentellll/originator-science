import { buildRecord, decision } from './builder'
import type { Continuous } from './builder'

/** DEV / MOCK case 2. Neutral public title; authored for UI development. */
export const SCENARIO_2 = {
  id: 'mock-seed-231881',
  title: 'Seed 231881 · binder MB-0231 rescue',
  summary: 'A binder reads inactive downstream. The failure could lie in the molecule, the assay that reported it, or the biological model.',
}

const R = 'MB-0231'
const C0: Continuous = { means: { monomer_fraction: 0.78, log_kd: -7.4, log_koff: -2.6 }, variances: { monomer_fraction: 0.05, log_kd: 1.3, log_koff: 1.1 } }
const c = (m: number, v: number, kd: number, vkd: number, ko: number, vko: number): Continuous => ({
  means: { monomer_fraction: m, log_kd: kd, log_koff: ko },
  variances: { monomer_fraction: v, log_kd: vkd, log_koff: vko },
})

export const caseB = buildRecord({
  id: 'mock-231881-ppo',
  seed: 231881,
  scenario: SCENARIO_2,
  policy: { name: 'PPOPolicy', description: 'Campaign-level planner. Values information net of damage to later measurements.' },
  candidate: R,
  notes: ['Downstream functional assay shows no activity.', 'The molecule, the assay, or the biological model could each explain this.'],
  p0: [0.25, 0.3, 0.4, 0.25, 0.25, 0.25, 0.35, 0.25],
  continuous0: C0,
  steps: [
    {
      action: 'VALIDATE_ASSAY',
      measurements: { control_signal: 0.08 },
      quality: 'good',
      notes: ['Reference control reads far below its usual range.'],
      p: [0.22, 0.28, 0.3, 0.22, 0.22, 0.22, 0.9, 0.25],
      continuous: C0,
      rationale:
        'A known control run through the same assay separates "the molecule is inactive" from "the assay cannot report activity". It is cheap, and it gates how far any functional result can be trusted. A redesign now would be judged against a readout that may itself be broken.',
      decision: decision({
        candidate: R,
        score: 0.84,
        confidence: 0.76,
        eig: 0.88,
        risk: 'If the control passes, the assay is cleared and the molecule is implicated, at the cost of $260 and 10 h.',
        alts: [
          ['MEASURE_SPR', 0.71, 0.95, 'Assay-independent and informative, but the control is cheaper and tells you how far later functional results can be trusted.'],
          ['MEASURE_SEC', 0.35, 0.31, 'Aggregation alone cannot explain the readout.'],
          ['REDESIGN_INTERFACE', 0.22, undefined, 'Spends $1,400 and 72 h against a readout that may itself be broken.'],
        ],
      }),
    },
    {
      action: 'MEASURE_SPR',
      measurements: { log_kd: -8.05, log_koff: -2.66 },
      quality: 'good',
      notes: ['Clean 1:1 fit.'],
      spr: 0.98,
      p: [0.05, 0.25, 0.05, 0.06, 0.08, 0.2, 0.9, 0.1],
      continuous: c(0.78, 0.05, -8.05, 0.03, -2.66, 0.03),
      rationale: 'The functional readout cannot be relied on. Measure binding directly on an instrument that does not share the failing assay.',
      decision: decision({
        candidate: R,
        score: 0.86,
        confidence: 0.82,
        eig: 0.91,
        risk: 'If SPR also shows weak binding, the molecule is implicated independently of the assay.',
        alts: [
          ['REDESIGN_INTERFACE', 0.15, undefined, 'No valid evidence yet that the molecule is at fault.'],
          ['MEASURE_SEC', 0.4, 0.34, 'A reasonable follow-up, but binding is the more direct question.'],
        ],
      }),
    },
    {
      action: 'MEASURE_SEC',
      measurements: { monomer_fraction: 0.97 },
      quality: 'good',
      notes: ['Single symmetric monomer peak.'],
      p: [0.04, 0.04, 0.05, 0.06, 0.08, 0.06, 0.9, 0.1],
      continuous: c(0.97, 0.002, -8.05, 0.03, -2.66, 0.03),
      rationale: 'Binding is strong. Before treating the molecule as sound, exclude aggregation, the one molecular cause that could degrade activity while leaving monomer binding intact.',
      decision: decision({
        candidate: R,
        score: 0.6,
        confidence: 0.72,
        eig: 0.31,
        risk: 'A clean SEC adds reassurance rather than a new finding; a messy one would change the plan.',
        alts: [
          ['SELECT', 0.45, undefined, 'Possible now, but aggregation is unexcluded and the assay invalidity is not independently confirmed.'],
          ['REDESIGN_INTERFACE', 0.04, undefined, 'SPR shows strong binding.'],
        ],
      }),
    },
    {
      action: 'ORTHOGONAL_FUNCTION',
      measurements: { orthogonal_function_signal: 0.88 },
      quality: 'good',
      notes: ['Activity recovered on an independent readout.'],
      p: [0.03, 0.04, 0.04, 0.05, 0.06, 0.05, 0.97, 0.04],
      continuous: c(0.97, 0.002, -8.05, 0.03, -2.66, 0.03),
      rationale: 'The molecule binds and is monomeric. An orthogonal function readout separates an invalid assay from an invalid biological model: if activity appears elsewhere, the first readout was the problem.',
      decision: decision({
        candidate: R,
        score: 0.88,
        confidence: 0.85,
        eig: 0.66,
        risk: 'If the orthogonal readout also fails, the biological model becomes the leading explanation instead.',
        alts: [['SELECT', 0.55, undefined, 'The assay explanation has not yet been confirmed by an independent readout.']],
      }),
    },
    {
      action: 'SELECT',
      measurements: undefined,
      p: [0.03, 0.04, 0.04, 0.05, 0.06, 0.05, 0.97, 0.04],
      continuous: c(0.97, 0.002, -8.05, 0.03, -2.66, 0.03),
      rationale: 'The molecule binds, is monomeric, and is active on an independent readout; the only explanation consistent with all four measurements is the first assay. No redesign is warranted.',
      decision: decision({
        candidate: R,
        score: 0.93,
        confidence: 0.9,
        risk: 'The cause of the assay problem (reagent vs plate) was not separated. This does not change the decision.',
        alts: [['REDESIGN_INTERFACE', 0.02, undefined, 'No evidence the molecule is at fault.']],
      }),
    },
  ],
  evaluation: { terminal_correct: true, justified: true, compound_recognised: null, assay_invalid_detected: true, model_invalid_detected: false, unnecessary_redesigns: 0, decision_calibration_error: 0.04 },
})
