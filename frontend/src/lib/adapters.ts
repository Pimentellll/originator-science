/**
 * Wire -> frontend adapters. The single reconciliation point with the backend:
 * validate the public payload, then project it. When the API's real endpoint
 * shapes land, translate them here and in the transport; components never change.
 */
import type { BenchmarkReport, EpisodeSummary, PolicyComparison } from './types'
import type { BenchmarkReportDto, EpisodeRecord, EpisodeSummaryDto } from './wire'
import { assertComparison, assertPublic, assertRecord } from './validate'
import { projectBenchmark, projectComparison, projectSummary } from './project'
import { TransportError } from './transport'

export const adaptRecord = (raw: unknown): EpisodeRecord => assertRecord(raw)

export function adaptSummaries(raw: unknown): EpisodeSummary[] {
  assertPublic(raw, 'episodes')
  if (!Array.isArray(raw)) throw new TransportError('episodes: expected an array')
  return (raw as EpisodeSummaryDto[]).map(projectSummary)
}

export function adaptComparison(raw: unknown): PolicyComparison | null {
  if (raw === null || raw === undefined) return null
  return projectComparison(assertComparison(raw))
}

export function adaptBenchmark(raw: unknown): BenchmarkReport {
  assertPublic(raw, 'benchmark')
  const r = raw as BenchmarkReportDto
  if (!r || !['real', 'mock', 'not_run'].includes(r.status)) throw new TransportError('benchmark: bad status')
  return projectBenchmark(r)
}
