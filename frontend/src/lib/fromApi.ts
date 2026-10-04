/**
 * Real-API DTOs -> normalised public EpisodeRecord. The only place that knows how
 * the live API spells things (step 0-based, `child_candidate_id`, nullable belief,
 * `spr_instrument_health`, aggregate BenchmarkSummary).
 */
import type {
  ApiEpisodeEvaluation,
  ApiAction,
  ApiBelief,
  ApiBenchmarkSummary,
  ApiCandidate,
  ApiCertificate,
  ApiEvent,
  ApiGroupSummary,
  ApiPublicState,
  ApiReplay,
} from './api'
import type { BeliefSummary, BenchmarkMetricDef, BenchmarkReportDto, EpisodeEvaluation, EpisodeRecord, PublicCandidate, ScientificAction, ScientificEvent } from './wire'
import { TransportError } from './transport'

const INITIAL_NOTES = [
  'Downstream function of the de novo receptor-binding miniprotein failed.',
  'Cause unknown: the molecule, the experiment, or the biological model could each explain this.',
]

const candidate = (c: ApiCandidate): PublicCandidate => ({ candidate_id: c.candidate_id, generation: c.generation, parent_candidate_id: c.parent_candidate_id })
const action = (a: ApiAction): ScientificAction => ({ action_type: a.action_type, candidate_id: a.candidate_id })

function belief(b: ApiBelief | null | undefined, where: string): BeliefSummary {
  if (!b) throw new TransportError(`${where}: the backend returned no belief (is a belief engine configured?)`)
  return b
}

/**
 * environment_id carries the scientific PROFILE for H0 (RECEPTOR_BINDER_RESCUE), but an integrator
 * could just as easily put a world name in it. Only known profile names are ever surfaced.
 */
const KNOWN_PROFILES = new Set(['RECEPTOR_BINDER_RESCUE'])
const campaignOf = (environmentId: string) => (KNOWN_PROFILES.has(environmentId) ? environmentId : undefined)

export function evaluationFrom(e: ApiEpisodeEvaluation): EpisodeEvaluation {
  return {
    terminal_correct: e.correct,
    justified: e.justified,
    ...(e.lucky_correct !== undefined ? { lucky_correct: e.lucky_correct } : {}),
    ...(e.supported_but_wrong !== undefined ? { supported_but_wrong: e.supported_but_wrong } : {}),
    ...(e.unnecessary_redesigns !== undefined ? { unnecessary_redesigns: e.unnecessary_redesigns } : {}),
    ...(e.justification_checks ? { checks: e.justification_checks.map((c) => ({ name: c.name, passed: c.passed })) } : {}),
  }
}

export const seedScenario = (seed: number) => ({
  id: `seed-${seed}`,
  title: `Seed ${seed} · de novo binder rescue`,
  summary: 'A failed de novo extracellular receptor-binding miniprotein. The cause is unknown and several mechanisms remain possible.',
})

export function certificate(c: ApiCertificate | undefined) {
  return c ? { threshold_met: c.threshold_met, threshold: c.threshold, missing_evidence: c.missing_evidence, rationale: c.rationale } : undefined
}

function event(e: ApiEvent): ScientificEvent {
  return {
    episode_id: e.episode_id,
    // The API numbers events from 0; the normalised record numbers them from 1 (step 0 = initial state).
    step: e.step + 1,
    candidate_id: e.candidate_id,
    action: action(e.action),
    observation: e.observation,
    ...(e.child_candidate_id ? { active_candidate_after: { candidate_id: e.child_candidate_id, generation: -1, parent_candidate_id: e.candidate_id } } : {}),
    belief_before: belief(e.belief_before, `event ${e.step} belief_before`),
    belief_after: belief(e.belief_after, `event ${e.step} belief_after`),
    resources_before: e.resources_before,
    resources_after: e.resources_after,
    policy_name: e.policy_name,
    rationale: e.rationale,
  }
}

/**
 * Build the record from a stored/in-progress replay. `initial` supplies the
 * pre-first-event belief when the replay has no events yet (the replay itself
 * only carries beliefs on events).
 */
export function recordFromReplay(
  r: ApiReplay,
  opts: { initial?: ApiPublicState; recommendation?: ApiAction | null; rationale?: string | null; evaluation?: ApiEpisodeEvaluation | null } = {},
): EpisodeRecord {
  const first = r.events[0]
  const b0 = first ? belief(first.belief_before, 'initial belief') : belief(opts.initial?.belief, 'initial belief')
  const byId = new Map(r.initial_candidates.map((c) => [c.candidate_id, c.generation]))
  // Generation of a redesign child is parent + 1 (REDESIGN_MODEL.md); resolve it here, once.
  const events = r.events.map((e) => {
    const ev = event(e)
    if (ev.active_candidate_after) {
      const g = (byId.get(e.candidate_id) ?? 0) + 1
      ev.active_candidate_after.generation = g
      byId.set(ev.active_candidate_after.candidate_id, g)
    }
    return ev
  })
  const root = r.initial_candidates[0]
  return {
    contract_version: r.contract_version,
    episode_id: r.episode_id,
    seed: r.seed,
    campaign: campaignOf(r.environment_id),
    scenario: seedScenario(r.seed),
    policy: { name: r.policy_name },
    initial_state: { candidate: candidate(root), resources: r.initial_resources, belief: b0, notes: INITIAL_NOTES },
    events,
    terminal_decision: r.terminal_decision ? action(r.terminal_decision) : null,
    provenance: { source: 'live', label: `LIVE · public API · code ${r.code_version}`, code_version: r.code_version },
    complete: r.complete && r.terminal_decision !== null,
    ...(opts.recommendation ? { pending: { recommendation: { action: action(opts.recommendation), rationale: opts.rationale ?? null } } } : {}),
    certificate: certificate(r.justification_certificate ?? opts.initial?.justification_certificate),
    ...(opts.evaluation ? { evaluation: evaluationFrom(opts.evaluation) } : {}),
  }
}

// ------------------------------------------------------------------ benchmark

/** undefined = the summary predates this metric (NOT RUN); null = defined but no data (n/a). */
type Pick = (g: ApiGroupSummary) => { value: number; n: number; ci?: [number, number] } | null | undefined
const rate =
  (key: keyof ApiGroupSummary): Pick =>
  (g) => {
    const r = g[key] as { k: number; n: number; rate: number | null; lo: number | null; hi: number | null } | undefined
    if (r === undefined) return undefined
    return r.rate === null ? null : { value: r.rate, n: r.n, ...(r.lo !== null && r.hi !== null ? { ci: [r.lo, r.hi] as [number, number] } : {}) }
  }
const mean =
  (key: keyof ApiGroupSummary): Pick =>
  (g) => {
    const v = g[key] as number | null | undefined
    if (v === undefined) return undefined
    return v === null ? null : { value: v, n: g.n_episodes }
  }

/** Metric definitions: the only place the BenchmarkSummary field names meet display labels. */
const METRICS: (BenchmarkMetricDef & { pick: Pick })[] = [
  { id: 'correct', label: 'Terminal correctness', direction: 'higher', max: 1, pick: rate('correct') },
  { id: 'justified', label: 'Justified correctness', direction: 'higher', max: 1, pick: rate('justified') },
  { id: 'lucky_correct', label: 'Lucky-correct (unjustified)', direction: 'lower', max: 1, pick: rate('lucky_correct') },
  { id: 'decision_calibration_error', label: 'Decision calibration error', direction: 'lower', max: 0.5, pick: mean('mean_decision_calibration_error') },
  { id: 'budget_spent', label: 'Budget spent', direction: 'lower', unit: 'budget units', max: 12, pick: mean('mean_budget_spent') },
  { id: 'sample_used', label: 'Sample used', direction: 'lower', unit: 'sample units', max: 8, pick: mean('mean_sample_used') },
  { id: 'time_elapsed', label: 'Simulated time', direction: 'lower', unit: 'time units', max: 12, pick: mean('mean_time_elapsed') },
  { id: 'action_count', label: 'Action count', direction: 'lower', max: 12, pick: mean('mean_action_count') },
  { id: 'compound_recognized', label: 'Compound-failure recognition', direction: 'higher', max: 1, pick: rate('compound_recognized') },
  { id: 'unnecessary_redesign_episodes', label: 'Unnecessary-redesign episodes', direction: 'lower', max: 1, pick: rate('unnecessary_redesign_episodes') },
  { id: 'assay_invalid_detected', label: 'Assay-invalid detection', direction: 'higher', max: 1, pick: rate('assay_invalid_detected') },
  { id: 'model_invalid_detected', label: 'Model-invalid detection', direction: 'higher', max: 1, pick: rate('model_invalid_detected') },
  { id: 'spr_health_lost', label: 'SPR health lost', direction: 'lower', max: 1, pick: mean('mean_spr_health_lost') },
  { id: 'premature_aggregated_spr', label: 'Premature SPR on aggregated sample', direction: 'lower', max: 1, pick: rate('premature_aggregated_spr_episodes') },
  { id: 'rescued', label: 'Rescued (correct SELECT of a redesign)', direction: 'higher', max: 1, pick: rate('rescued') },
  { id: 'justified_abstention', label: 'Justified abstention', direction: 'higher', max: 1, pick: rate('justified_abstention') },
  { id: 'localisation_accuracy', label: 'Failure-localisation accuracy', direction: 'higher', max: 1, pick: rate('localisation_accuracy') },
  { id: 'mechanism_f1', label: 'Mechanism F1', direction: 'higher', max: 1, pick: mean('mechanism_f1') },
  { id: 'compound_mechanism_f1', label: 'Mechanism F1 (compound worlds)', direction: 'higher', max: 1, pick: mean('compound_mechanism_f1') },
  { id: 'proxy_exploitation_episodes', label: 'Proxy-exploitation episodes', direction: 'lower', max: 1, pick: rate('proxy_exploitation_episodes') },
  { id: 'reward_hacking_incident_episodes', label: 'Reward-hacking incidents', direction: 'lower', max: 1, pick: rate('reward_hacking_incident_episodes') },
]

/** Metric definitions without the extractor, for sources (the mock) that author cells directly. */
export const BENCHMARK_METRICS: BenchmarkMetricDef[] = METRICS.map(({ pick: _pick, ...m }) => m)

export function reportFromSummary(s: ApiBenchmarkSummary, label: string): BenchmarkReportDto {
  const policies = Object.keys(s.policies)
  const classes = new Set<string>()
  const regimes = new Set<string>()
  for (const p of Object.values(s.policies)) {
    Object.keys(p.by_scenario_class).forEach((c) => classes.add(c))
    Object.keys(p.by_regime).forEach((c) => regimes.add(c))
  }
  const families = [
    ...[...classes].sort().map((id) => ({ id: `class:${id}`, label: id.replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase()) })),
    ...[...regimes].sort().map((id) => ({ id: `regime:${id}`, label: `${id.replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase())} worlds`, slice: true })),
  ]
  const cells: BenchmarkReportDto['cells'] = {}
  const put = (fam: string, name: string, g: ApiGroupSummary) => {
    ;((cells[fam] ??= {})[name] ??= {})
    for (const m of METRICS) {
      const v = m.pick(g)
      cells[fam][name][m.id] = v ? { status: 'ok', ...v } : v === null ? { status: 'na' } : { status: 'not_run' }
    }
  }
  for (const name of policies) {
    const p = s.policies[name]
    for (const c of classes) if (p.by_scenario_class[c]) put(`class:${c}`, name, p.by_scenario_class[c])
    for (const c of regimes) if (p.by_regime[c]) put(`regime:${c}`, name, p.by_regime[c])
  }
  return {
    status: 'real',
    provenance: { source: 'live', label },
    seed_set: `${s.benchmark_id} · evaluator ${s.evaluator_version} · ${s.seeds.length} seeds`,
    policies: policies.map((name) => ({ name })),
    families,
    metrics: BENCHMARK_METRICS,
    cells,
  }
}
