import type {
  Condition,
  DerivedMeasurement,
  DiagnosisLabel,
  GrowthEpisode,
  Reading,
} from './types'

export function hypothesisFor(condition: Condition): DiagnosisLabel {
  return condition === 'BIOLOGICAL_PLATEAU' ? 'BIOMASS_AS_READ' : 'BIOMASS_ABOVE_READING'
}

export function conditionFor(diagnosis: DiagnosisLabel): Condition {
  return diagnosis === 'BIOMASS_AS_READ' ? 'BIOLOGICAL_PLATEAU' : 'MEASUREMENT_ARTIFACT'
}

export function outcome(cell: {
  correct: boolean | null
  justified: boolean | null
  status: string
}): 'justified' | 'unjustified' | 'wrong' | 'none' {
  if (cell.correct === null) return 'none'
  if (!cell.correct) return 'wrong'
  return cell.justified ? 'justified' : 'unjustified'
}

export function passiveAt(passive: Reading[], time_h: number): number | null {
  return passive.find((reading) => reading.time_h === time_h)?.mean_reading ?? null
}

export function foldOverUndiluted(measurement: DerivedMeasurement, passive: Reading[]): number | null {
  const baseline = passiveAt(passive, measurement.time_h ?? Number.NaN)
  if (baseline === null || baseline === 0 || measurement.back_corrected === null) return null
  return measurement.back_corrected / baseline
}

export interface DilutionAgreement {
  time_h: number
  factors: number[]
  values: number[]
  relSpread: number
}

export function dilutionAgreement(measurements: DerivedMeasurement[]): DilutionAgreement[] {
  const byTime = new Map<number, DerivedMeasurement[]>()
  for (const measurement of measurements) {
    if (
      measurement.time_h === null ||
      measurement.dilution_factor === null ||
      measurement.back_corrected === null
    ) {
      continue
    }
    const group = byTime.get(measurement.time_h) ?? []
    group.push(measurement)
    byTime.set(measurement.time_h, group)
  }

  return [...byTime.entries()]
    .sort(([a], [b]) => a - b)
    .flatMap(([time_h, group]) => {
      if (new Set(group.map((measurement) => measurement.dilution_factor)).size < 2) return []
      const sorted = [...group].sort(
        (a, b) => (a.dilution_factor as number) - (b.dilution_factor as number),
      )
      const factors = sorted.map((measurement) => measurement.dilution_factor as number)
      const values = sorted.map((measurement) => measurement.back_corrected as number)
      const mean = values.reduce((sum, value) => sum + value, 0) / values.length
      const relSpread = (Math.max(...values) - Math.min(...values)) / mean
      return [{ time_h, factors, values, relSpread }]
    })
}

export interface ReliabilityRow {
  p: number | null
  condition: Condition
}

export interface ReliabilityBin {
  lo: number
  hi: number
  n: number
  meanP: number | null
  observed: number | null
}

export function reliability(rows: ReliabilityRow[], bins = 5): ReliabilityBin[] {
  if (!Number.isInteger(bins) || bins < 1) throw new RangeError('bins must be a positive integer')
  const groups = Array.from({ length: bins }, () => [] as ReliabilityRow[])
  for (const row of rows) {
    if (row.p === null || !Number.isFinite(row.p) || row.p < 0 || row.p > 1) continue
    const index = Math.min(Math.floor(row.p * bins), bins - 1)
    groups[index].push(row)
  }
  return groups.map((group, index) => ({
    lo: index / bins,
    hi: (index + 1) / bins,
    n: group.length,
    meanP: group.length ? group.reduce((sum, row) => sum + (row.p as number), 0) / group.length : null,
    observed: group.length
      ? group.filter((row) => row.condition === 'MEASUREMENT_ARTIFACT').length / group.length
      : null,
  }))
}

export function meanBrier(rows: Array<{ brier: number | null }>): number | null {
  const values = rows.flatMap((row) => (row.brier === null ? [] : [row.brier]))
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null
}

function csvValue(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value) ?? String(value)
}

function csvField(value: unknown): string {
  const text = csvValue(value)
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

export function toCsv(columns: string[], rows: Record<string, unknown>[]): string {
  return [columns.map(csvField).join(','), ...rows.map((row) => columns.map((column) => csvField(row[column])).join(','))].join(
    '\r\n',
  )
}

function backCorrected(reading: number, dilutionFactor: number): number {
  return Math.round(reading * dilutionFactor * 1e12) / 1e12
}

const READING_COLUMNS = [
  'source',
  'time_h',
  'dilution_factor',
  'replicate',
  'reading',
  'mean_reading',
  'back_corrected',
  'turn',
]

export function episodeReadingsCsv(episode: GrowthEpisode): string {
  const rows: Record<string, unknown>[] = episode.passive.map((reading) => {
    const value = reading.readings[0] ?? reading.mean_reading
    return {
      source: 'passive',
      time_h: reading.time_h,
      dilution_factor: reading.dilution_factor,
      replicate: 1,
      reading: value,
      mean_reading: reading.mean_reading,
      back_corrected: backCorrected(value, reading.dilution_factor),
      turn: null,
    }
  })

  for (const event of episode.events) {
    if (event.tool !== 'measure_od' || !event.ok || event.result === null) continue
    const readings = event.result.readings
    if (!Array.isArray(readings)) continue
    const time_h = event.result.time_h ?? event.arguments.time_h
    const dilution_factor = event.result.dilution_factor ?? event.arguments.dilution_factor ?? 1
    const mean_reading = event.result.mean_reading
    const back_corrected =
      typeof mean_reading === 'number' && typeof dilution_factor === 'number'
        ? backCorrected(mean_reading, dilution_factor)
        : null
    readings.forEach((reading, index) => {
      rows.push({
        source: 'measurement',
        time_h,
        dilution_factor,
        replicate: index + 1,
        reading,
        mean_reading,
        back_corrected,
        turn: event.turn,
      })
    })
  }

  return toCsv(READING_COLUMNS, rows)
}

export function downloadText(filename: string, text: string, mime: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: mime }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
