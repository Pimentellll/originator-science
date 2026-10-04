import type { ActionType, TerminalView } from './types'

export type TerminalEvaluation = NonNullable<TerminalView['evaluation']>

export type VerdictKind = 'correct_justified' | 'correct_unjustified' | 'justified_abstention' | 'incorrect' | 'no_verdict'

export interface Verdict {
  kind: VerdictKind
  label: string
  /** One short sentence, never more than the evaluator's own fields support. */
  explain: string
}

const LABEL: Record<VerdictKind, string> = {
  correct_justified: 'CORRECT + JUSTIFIED',
  correct_unjustified: 'CORRECT BUT UNJUSTIFIED',
  justified_abstention: 'JUSTIFIED ABSTENTION',
  incorrect: 'INCORRECT',
  no_verdict: 'NO VERDICT',
}

const EXPLAIN: Record<VerdictKind, string> = {
  correct_justified: 'The decision matches the hidden truth and the evidence MIRAGE actually collected supports it.',
  correct_unjustified: 'The decision happens to match the hidden truth, but the collected evidence does not support it: right answer, wrong reason.',
  justified_abstention: 'Declining to decide was the supportable call: the evidence collected does not settle the question.',
  incorrect: 'The decision does not match the hidden truth.',
  no_verdict: 'The evaluator assigns neither correct nor justified here (for example an abstention the evidence does not support), or no verdict is attached.',
}

/**
 * Map the privileged evaluator's fields (served only after the episode is terminal) onto the five
 * display verdicts. Nothing is inferred: with no evaluation attached the answer is NO VERDICT.
 */
export function verdictOf(ev: TerminalEvaluation | null, decision: ActionType): Verdict {
  const make = (kind: VerdictKind): Verdict => ({ kind, label: LABEL[kind], explain: EXPLAIN[kind] })
  if (!ev) return { ...make('no_verdict'), explain: 'No evaluator verdict is attached to this record: it is served only after the decision, behind an access token.' }
  if (decision === 'ABSTAIN') {
    if (ev.justified_abstention) return make('justified_abstention')
    if (ev.terminal_correct === false) return make('incorrect')
    if (ev.terminal_correct === true) return make(ev.justified ? 'correct_justified' : 'correct_unjustified')
    return make('no_verdict')
  }
  if (ev.terminal_correct === true) return make(ev.justified ? 'correct_justified' : 'correct_unjustified')
  if (ev.terminal_correct === false) return make('incorrect')
  return make('no_verdict')
}
