import { ReplayTransport } from '../replayTransport'
import type { ReplaySource } from '../replayTransport'
import { mockBenchmark } from './benchmark'
import { caseAGreedy, caseAMirage, comparisonCase1 } from './caseA'
import { caseB } from './caseB'

/** In-memory source with the same shape as files fetched from `{replayBase}/…`. */
export const mockSource: ReplaySource = {
  // Order matters: the first record per scenario is its featured policy.
  records: async () => [caseAMirage, caseB, caseAGreedy],
  comparisons: async () => [comparisonCase1],
  benchmark: async () => mockBenchmark,
}

export function createMockTransport() {
  return new ReplayTransport(mockSource, { kind: 'mock', label: 'MOCK' })
}

export { caseAMirage, caseAGreedy, caseB, comparisonCase1, mockBenchmark }
