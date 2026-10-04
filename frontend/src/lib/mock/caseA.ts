import type { PolicyComparisonRecord } from '../wire'
import { buildRecord, decision, MOCK_PROVENANCE } from './builder'
import type { Continuous } from './builder'

/**
 * DEV / MOCK case 1. Neutral public title: nothing here names the world class.
 * Authored for UI development; the numbers are not simulator output.
 */
export const SCENARIO_1 = {
  id: 'mock-seed-417417',
  title: 'Seed 417417 · binder MB-0417 rescue',
  summary: 'A de novo binder shows no downstream function. Several causes remain possible; the order of experiments changes what later measurements can tell you.',
}

const NOTES = [
  'Downstream functional assay shows no neutralisation.',
  'The design-stage prediction did not anticipate this.',
  'Cause unknown: more than one mechanism may be contributing.',
]

const C0: Continuous = {
  means: { monomer_fraction: 0.75, log_kd: -7.2, log_koff: -2.5 },
  variances: { monomer_fraction: 0.06, log_kd: 1.4, log_koff: 1.2 },
}
const c = (m: number, v: number, kd: number, vkd: number, ko: number, vko: number): Continuous => ({
  means: { monomer_fraction: m, log_kd: kd, log_koff: ko },
  variances: { monomer_fraction: v, log_kd: vkd, log_koff: vko },
})

const P0: [number, number, number, number, number, number, number, number] = [0.3, 0.45, 0.5, 0.35, 0.25, 0.35, 0.2, 0.25]

const G1 = 'MB-0417-g1'
const G2 = 'MB-0417-g2'
const R = 'MB-0417'

// ----------------------------------------------- long-horizon (illustrative MOCK)
export const caseAMirage = buildRecord({
  id: 'mock-417417-ppo',
  seed: 417417,
  scenario: SCENARIO_1,
  policy: { name: 'MockLongHorizon', description: 'Illustrative authored trace of campaign-level planning. Not produced by PPO, Lookahead or any trained policy.' },
  candidate: R,
  notes: NOTES,
  p0: P0,
  continuous0: C0,
  steps: [
    {
      action: 'MEASURE_SEC',
      measurements: { monomer_fraction: 0.62 },
      quality: 'good',
      notes: ['High-molecular-weight shoulder at the void volume.'],
      p: [0.22, 0.94, 0.38, 0.35, 0.2, 0.58, 0.18, 0.22],
      continuous: c(0.62, 0.01, -7.2, 1.4, -2.5, 1.2),
      rationale:
        'Aggregation is the cheapest cause to confirm or exclude, and the one most likely to corrupt later binding data. SEC does not touch the SPR instrument. Running SPR on an aggregated sample would reduce its quality and could damage the instrument for every later run.',
      decision: decision({
        candidate: R,
        score: 0.81,
        confidence: 0.78,
        eig: 0.74,
        risk: 'A clean SEC result leaves binding questions open, for the price of one low-cost assay.',
        alts: [
          ['MEASURE_SPR', 0.52, 1.12, 'Highest immediate information, but an aggregated sample gives an unreliable sensorgram and can foul the chip, which poisons every later SPR run.'],
          ['VALIDATE_ASSAY', 0.4, 0.52, 'Assay invalidity has a low prior and the control cannot localise a molecular cause.'],
          ['MEASURE_EPITOPE', 0.18, 0.61, 'Premature before sample quality is known.'],
          ['MEASURE_STABILITY', 0.21, 0.38, 'Cheap, but folding is one of several candidates and this does not detect aggregation reliably.'],
        ],
      }),
    },
    {
      action: 'REDESIGN_SOLUBILITY',
      newCandidate: G1,
      p: [0.24, 0.3, 0.38, 0.35, 0.2, 0.33, 0.18, 0.22],
      continuous: c(0.85, 0.05, -7.0, 1.2, -2.4, 1.1),
      rationale:
        'SEC shows a large aggregate fraction, so any binding measurement on this lot is confounded. A solubility redesign targets aggregation and developability first, so later SPR measures the molecule rather than its aggregates.',
      decision: decision({
        candidate: R,
        score: 0.77,
        confidence: 0.74,
        risk: 'A redesign is a synthetic transition with a small possible stability or interface cost. It must be verified, not assumed.',
        alts: [
          ['MEASURE_SPR', 0.33, 1.08, 'Still confounded by aggregates and risks the instrument.'],
          ['REJECT', 0.2, undefined, 'Rejecting stops the campaign with a repairable defect unaddressed.'],
          ['VALIDATE_ASSAY', 0.27, 0.41, 'Aggregation already explains part of the functional failure; lower value now.'],
        ],
      }),
    },
    {
      action: 'MEASURE_SEC',
      candidate: G1,
      measurements: { monomer_fraction: 0.96 },
      quality: 'good',
      notes: ['Single symmetric monomer peak.'],
      p: [0.15, 0.05, 0.38, 0.37, 0.2, 0.15, 0.18, 0.22],
      continuous: c(0.96, 0.002, -7.0, 1.2, -2.4, 1.1),
      rationale: 'Confirm the repair before spending SPR sample. A clean trace also tells the policy SPR is now safe to run.',
      decision: decision({
        candidate: G1,
        score: 0.7,
        confidence: 0.8,
        eig: 0.33,
        risk: 'If the repair is partial, SPR would again be compromised and a second redesign would be needed.',
        alts: [['MEASURE_SPR', 0.58, 1.01, 'Efficient, but unsafe if the repair is incomplete.']],
      }),
    },
    {
      action: 'MEASURE_SPR',
      candidate: G1,
      measurements: { log_kd: -6.64, log_koff: -1.39 },
      quality: 'good',
      notes: ['Clean 1:1 fit.', 'Dissociation is fast relative to association.'],
      spr: 0.97,
      p: [0.08, 0.04, 0.46, 0.91, 0.12, 0.14, 0.17, 0.3],
      continuous: c(0.96, 0.002, -6.64, 0.03, -1.39, 0.03),
      rationale: 'The sample is now monomeric, so SPR has both the highest information value and a reliable readout. It separates affinity, kinetics and epitope engagement in one run, with the instrument preserved.',
      decision: decision({
        candidate: G1,
        score: 0.86,
        confidence: 0.83,
        eig: 1.05,
        risk: 'If kinetics is the remaining defect a second redesign follows; budget keeps room for one more cycle.',
        alts: [
          ['MEASURE_EPITOPE', 0.41, 0.63, 'Narrower question at higher cost.'],
          ['VALIDATE_ASSAY', 0.39, 0.4, 'Assay invalidity is unlikely, and SPR bears on it too.'],
        ],
      }),
    },
    {
      action: 'VALIDATE_ASSAY',
      candidate: G1,
      measurements: { control_signal: 0.97 },
      quality: 'good',
      notes: ['Reference control within its usual range.'],
      p: [0.08, 0.04, 0.3, 0.92, 0.12, 0.14, 0.04, 0.2],
      continuous: c(0.96, 0.002, -6.64, 0.03, -1.39, 0.03),
      rationale: 'The failed functional readout was the only evidence of the original failure. Confirm the assay reports a known control before redesigning again and before asserting a molecular cause.',
      decision: decision({
        candidate: G1,
        score: 0.64,
        confidence: 0.69,
        eig: 0.29,
        risk: 'If the control fails, the functional readout is untrustworthy and the kinetic finding needs independent confirmation.',
        alts: [
          ['REDESIGN_INTERFACE', 0.6, undefined, 'Valid, but skips a cheap check that the assay can be trusted.'],
          ['SELECT', 0.35, undefined, 'Premature: kinetics is unresolved and the assay is unvalidated.'],
        ],
      }),
    },
    {
      action: 'REDESIGN_INTERFACE',
      candidate: G1,
      newCandidate: G2,
      p: [0.12, 0.08, 0.22, 0.4, 0.14, 0.16, 0.04, 0.2],
      continuous: c(0.9, 0.02, -7.1, 0.5, -2.1, 0.5),
      rationale: 'The assay is validated and SPR shows fast dissociation with a clean fit. An interface redesign targets affinity and kinetics, with a small possible stability or aggregation cost to be re-checked.',
      decision: decision({
        candidate: G1,
        score: 0.83,
        confidence: 0.81,
        risk: 'The interface change could shift association; SPR on the new candidate is required.',
        alts: [
          ['SELECT', 0.3, undefined, 'Would leave a diagnosed, repairable kinetic defect unaddressed.'],
          ['MEASURE_EPITOPE', 0.22, 0.31, 'SPR already shows engagement.'],
        ],
      }),
    },
    {
      action: 'MEASURE_SPR',
      candidate: G2,
      measurements: { log_kd: -7.85, log_koff: -2.58 },
      quality: 'good',
      notes: ['Clean 1:1 fit.'],
      spr: 0.95,
      p: [0.08, 0.05, 0.08, 0.07, 0.09, 0.14, 0.04, 0.12],
      continuous: c(0.95, 0.003, -7.85, 0.03, -2.58, 0.03),
      rationale: 'Test the repair directly on the same instrument, which is still healthy.',
      decision: decision({
        candidate: G2,
        score: 0.88,
        confidence: 0.86,
        eig: 0.96,
        risk: 'None beyond cost. SPR health is 0.97.',
        alts: [['SELECT', 0.25, undefined, 'The interface repair is unverified.']],
      }),
    },
    {
      action: 'SELECT',
      candidate: G2,
      p: [0.08, 0.05, 0.08, 0.07, 0.09, 0.14, 0.04, 0.12],
      continuous: c(0.95, 0.003, -7.85, 0.03, -2.58, 0.03),
      rationale: 'Every failure mode on the current candidate is now improbable, with direct evidence on aggregation, binding and kinetics, and a validated assay. More experiments add little.',
      decision: decision({
        candidate: G2,
        score: 0.91,
        confidence: 0.88,
        risk: 'Epitope and developability were not measured directly; both are low in belief but not independently confirmed.',
        alts: [['MEASURE_EPITOPE', 0.12, 0.18, 'Low expected information for its cost.']],
      }),
    },
  ],
  evaluation: { terminal_correct: true, justified: true, unnecessary_redesigns: 0 },
})

// ---------------------------------------------------------------- GREEDY EIG
const noModel = 'Greedy EIG has no state for sample quality or instrument degradation, so neither is priced in.'
const FOUL = ['Biphasic, non-saturating sensorgram.', 'Baseline drift after injection.']

export const caseAGreedy = buildRecord({
  id: 'mock-417417-greedy',
  seed: 417417,
  scenario: SCENARIO_1,
  policy: { name: 'GreedyEIGPolicy', description: 'Chooses the experiment with the highest one-step expected information gain.' },
  candidate: R,
  notes: NOTES,
  p0: P0,
  continuous0: C0,
  steps: [
    {
      action: 'MEASURE_SPR',
      measurements: { log_kd: -5.4, log_koff: -1.05 },
      quality: 'degraded',
      notes: FOUL,
      spr: 0.35,
      p: [0.33, 0.47, 0.62, 0.48, 0.27, 0.38, 0.19, 0.26],
      continuous: c(0.75, 0.06, -5.4, 0.9, -1.05, 0.8),
      rationale: 'Maximises expected information gain: one SPR run can separate affinity, kinetics and epitope engagement.',
      decision: decision({
        candidate: R,
        score: 1.12,
        confidence: 0.62,
        eig: 1.12,
        risk: noModel,
        alts: [
          ['MEASURE_SEC', 0.74, 0.74, 'Lower immediate EIG than SPR.'],
          ['MEASURE_EPITOPE', 0.61, 0.61, 'Lower immediate EIG than SPR.'],
          ['VALIDATE_ASSAY', 0.52, 0.52, 'Lower immediate EIG than SPR.'],
        ],
      }),
    },
    {
      action: 'MEASURE_SPR',
      measurements: { log_kd: -5.1, log_koff: -0.95 },
      quality: 'degraded',
      notes: ['Fit quality worse than the first run.', 'Surface does not regenerate.'],
      spr: 0.2,
      p: [0.33, 0.46, 0.67, 0.5, 0.28, 0.38, 0.18, 0.27],
      continuous: c(0.75, 0.06, -5.1, 0.8, -0.95, 0.7),
      rationale: 'The biphasic trace is ambiguous between a heterogeneous interaction and weak affinity. A second concentration series has the highest expected information.',
      decision: decision({
        candidate: R,
        score: 0.78,
        confidence: 0.55,
        eig: 0.78,
        risk: noModel,
        alts: [
          ['MEASURE_SEC', 0.66, 0.66, 'Lower immediate EIG than a repeat SPR.'],
          ['REDESIGN_INTERFACE', 0.42, undefined, 'Not informative by itself.'],
        ],
      }),
    },
    {
      action: 'REDESIGN_INTERFACE',
      newCandidate: 'MB-0417-g1',
      p: [0.35, 0.46, 0.45, 0.4, 0.28, 0.38, 0.18, 0.27],
      continuous: c(0.75, 0.06, -5.6, 1, -1.3, 0.9),
      rationale: 'A third SPR has low expected information after two poor fits. The leading hypothesis is weak affinity, so the best remaining move is to improve the interface.',
      decision: decision({
        candidate: R,
        score: 0.55,
        confidence: 0.5,
        risk: noModel,
        alts: [
          ['MEASURE_SPR', 0.31, 0.31, 'Expected information has collapsed after two poor fits.'],
          ['MEASURE_SEC', 0.29, 0.29, 'Lower EIG than redesigning for the leading hypothesis.'],
        ],
      }),
    },
    {
      action: 'MEASURE_SPR',
      candidate: 'MB-0417-g1',
      measurements: { log_kd: -5.9, log_koff: -1.2 },
      quality: 'degraded',
      notes: ['Binding not resolvable on this surface.'],
      spr: 0.12,
      p: [0.35, 0.47, 0.6, 0.5, 0.38, 0.39, 0.2, 0.34],
      continuous: c(0.75, 0.06, -5.9, 0.9, -1.2, 0.8),
      rationale: 'Measure whether the redesigned variant binds better.',
      decision: decision({ candidate: 'MB-0417-g1', score: 0.7, confidence: 0.52, eig: 0.7, risk: noModel, alts: [['MEASURE_SEC', 0.35, 0.35, 'Lower EIG than SPR.']] }),
    },
    {
      action: 'MEASURE_SPR',
      candidate: 'MB-0417-g1',
      measurements: { log_kd: -5.7, log_koff: -1.1 },
      quality: 'degraded',
      notes: ['Still not resolvable.'],
      spr: 0.12,
      p: [0.35, 0.47, 0.58, 0.51, 0.41, 0.4, 0.2, 0.38],
      continuous: c(0.75, 0.06, -5.7, 0.9, -1.1, 0.8),
      rationale: 'The redesigned binder is still unresolved. Retry at a higher analyte concentration.',
      decision: decision({ candidate: 'MB-0417-g1', score: 0.48, confidence: 0.46, eig: 0.48, risk: noModel, alts: [['REDESIGN_INTERFACE', 0.4, undefined, 'A second redesign would be a guess without a resolved measurement.']] }),
    },
    {
      action: 'REDESIGN_INTERFACE',
      candidate: 'MB-0417-g1',
      newCandidate: 'MB-0417-g2',
      p: [0.36, 0.48, 0.42, 0.45, 0.41, 0.4, 0.2, 0.38],
      continuous: c(0.75, 0.06, -5.9, 0.9, -1.3, 0.9),
      rationale: 'Four unresolved SPR readouts. The leading hypothesis is still weak affinity, so redesign once more.',
      decision: decision({ candidate: 'MB-0417-g1', score: 0.41, confidence: 0.4, risk: noModel, alts: [['SELECT', 0.3, undefined, 'Budget would still allow another cycle.']] }),
    },
    {
      action: 'SELECT',
      candidate: 'MB-0417-g2',
      p: [0.36, 0.48, 0.42, 0.45, 0.41, 0.4, 0.2, 0.38],
      continuous: c(0.75, 0.06, -5.9, 0.9, -1.3, 0.9),
      rationale: 'The budget is exhausted, so no experiment is affordable. Select the most recent candidate.',
      decision: decision({ candidate: 'MB-0417-g2', score: 0.3, confidence: 0.35, risk: 'The decision rests on measurements the policy had degraded, with no direct evidence on this candidate.', alts: [] }),
    },
  ],
  evaluation: { terminal_correct: false, justified: false, unnecessary_redesigns: 2 },
})

export const comparisonCase1: PolicyComparisonRecord = {
  scenario: SCENARIO_1,
  seed: 417417,
  records: [caseAGreedy, caseAMirage],
  divergence_note: 'Identical public state, different decision. SPR maximises immediate information. SEC protects the SPR instrument and preserves later kinetic evidence.',
  provenance: MOCK_PROVENANCE,
}
