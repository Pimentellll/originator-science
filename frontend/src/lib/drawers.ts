/** Side panels of the step-by-step cockpit, in tab order. */
export type DrawerId = 'evidence' | 'timeline' | 'belief' | 'action' | 'candidate' | 'resources'

export const DRAWERS: {
  id: DrawerId
  label: string
  title: string
  hint: string
}[] = [
  {
    id: 'evidence',
    label: 'Evidence',
    title: 'Evidence graph',
    hint: 'Every measurement so far, and which explanations it supports or rules out.',
  },
  {
    id: 'timeline',
    label: 'Timeline',
    title: 'Timeline',
    hint: 'Each step of the campaign in order. Pick one to go back to it.',
  },
  {
    id: 'belief',
    label: 'Beliefs',
    title: 'What MIRAGE believes',
    hint: "The model's belief in every failure explanation. Several can be high at once.",
  },
  {
    id: 'action',
    label: 'Next action',
    title: 'The next action in detail',
    hint: 'The recommended experiment, the alternatives it was weighed against, and what it is expected to reveal.',
  },
  {
    id: 'candidate',
    label: 'Candidate',
    title: 'Candidate and justification',
    hint: 'The molecule under test, its redesign history, and the evidence behind a decision.',
  },
  {
    id: 'resources',
    label: 'Budget',
    title: 'Resources',
    hint: 'Budget, sample and SPR instrument health in detail.',
  },
]
