import type { ActionType } from '../lib/wire'
import type { ManualChoice } from './sessionContext'

export function appendManualChoice(log: ManualChoice[], step: number, chosen: ActionType, recommended: ActionType | null): ManualChoice[] {
  return [...log, { step, chosen, recommended }]
}
