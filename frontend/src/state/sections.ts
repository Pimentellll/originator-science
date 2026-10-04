import type { Route } from './route'

export interface Section {
  label: string
  hint: string
  home: Route
  tabs: { id: Route; label: string }[]
}

export const SECTIONS: Section[] = [
  {
    label: 'Overview',
    hint: 'What MIRAGE is, in one page',
    home: 'overview',
    tabs: [],
  },
  {
    label: 'Growth benchmark',
    hint: 'Does an AI scientist run the dilution control? The headline result.',
    home: 'results',
    tabs: [
      { id: 'results', label: 'Results' },
      { id: 'lab', label: 'Try it yourself' },
      { id: 'method', label: 'Method' },
    ],
  },
  {
    label: 'Binder campaign',
    hint: 'Watch an agent work out why a protein binder failed',
    home: 'launch',
    tabs: [
      { id: 'launch', label: 'Start' },
      { id: 'cockpit', label: 'Cockpit' },
      { id: 'compare', label: 'Compare policies' },
    ],
  },
]

export const TOOLS: { id: Route; label: string; hint: string }[] = [
  {
    id: 'benchmark',
    label: 'Benchmark lab',
    hint: 'Aggregate scores over many binder campaigns',
  },
  {
    id: 'diagnostics',
    label: 'System check',
    hint: 'Is the API reachable and is everything wired up?',
  },
]

/** The section a route belongs to; the episode view is part of Results. */
export function sectionOf(route: Route): Section | null {
  const r = route === 'episode' ? 'results' : route
  return SECTIONS.find((s) => s.home === r || s.tabs.some((t) => t.id === r)) ?? null
}
