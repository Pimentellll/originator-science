import { verdictOf } from '../lib/verdict'
import type { TerminalEvaluation, VerdictKind } from '../lib/verdict'
import type { ActionType } from '../lib/types'

const TONE: Record<VerdictKind, string> = {
  correct_justified: 'verdict--ok',
  correct_unjustified: 'verdict--warn',
  justified_abstention: 'verdict--ok',
  incorrect: 'verdict--bad',
  no_verdict: 'verdict--none',
}

/**
 * The correct-vs-justified read-out. It renders only what the privileged evaluator reported after
 * the decision; with no evaluation attached it says NO VERDICT and why.
 */
export function VerdictBanner({ evaluation, decision, compact = false }: { evaluation: TerminalEvaluation | null; decision: ActionType; compact?: boolean }) {
  const v = verdictOf(evaluation, decision)
  return (
    <div className={`verdict ${TONE[v.kind]} ${compact ? 'verdict--compact' : ''}`} role="status">
      <span className="verdict__label mono">{v.label}</span>
      <span className="verdict__why">{v.explain}</span>
      {evaluation?.lucky_correct && <span className="pill pill--warn">LUCKY-CORRECT</span>}
      {evaluation?.supported_but_wrong && <span className="pill pill--warn">SUPPORTED BUT WRONG</span>}
    </div>
  )
}
