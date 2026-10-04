import { GUIDED_PRESET } from './sessionContext'
import type { LaunchConfig } from '../lib/types'

/** Launch choices from the URL, e.g. `?seed=4&scenario=ASSAY_FAILURE&guided=1` (what `./mirage demo` opens). */
export function launchFromSearch(search: string): LaunchConfig {
  const q = new URLSearchParams(search)
  const guided = q.get('guided') === '1'
  const base: LaunchConfig = guided ? { ...GUIDED_PRESET, guided: true } : { scenario: null, semantics: null, policy: null, seed: 9, control: 'auto', guided: false }
  const seed = q.get('seed')
  const word = (v: string | null) => (v && /^[A-Za-z0-9_]{1,64}$/.test(v) ? v : null)
  return {
    ...base,
    seed: seed && /^\d+$/.test(seed) ? Number(seed) : base.seed,
    scenario: word(q.get('scenario')) ?? base.scenario,
    semantics: word(q.get('semantics')) ?? base.semantics,
    policy: word(q.get('policy')) ?? base.policy,
    control: q.get('control') === 'manual' ? 'manual' : base.control,
  }
}
