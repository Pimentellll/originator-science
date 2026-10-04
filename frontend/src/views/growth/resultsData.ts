import type { GrowthEpisode, GrowthGrid, GrowthRun, GrowthRunEntry } from '../../lib/growth/types'
import { growthClient } from './data'

export type Loaded = {
  runs: GrowthRunEntry[]
  grid: GrowthGrid
  details: GrowthRun[]
  demo: { runId: string; bp: GrowthEpisode; ma: GrowthEpisode } | null
}

export async function load(): Promise<Loaded> {
  const c = growthClient()
  const [runs, grid] = await Promise.all([c.listRuns(), c.getGrid('strong')])
  const details = await Promise.all(grid.columns.map((col) => c.getRun(col.run_id)))
  const demoRun = runs.find((r) => r.matrix === 'demo')
  let demo: Loaded['demo'] = null
  if (demoRun) {
    const [bp, ma] = await Promise.all([c.getEpisode(demoRun.run_id, 'demo-BP'), c.getEpisode(demoRun.run_id, 'demo-MA')])
    demo = { runId: demoRun.run_id, bp, ma }
  }
  return { runs, grid, details, demo }
}
