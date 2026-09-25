import type { PartialKind } from '@/api/client'

/** Latest, min, max and mean for one series, for the summary strip above an expanded chart.
 * Every field is null for a series with nothing finite in it.
 */
export interface SeriesStats {
  latest: number | null
  min: number | null
  max: number | null
  mean: number | null
  /** True when every value counted was a whole number, which makes the mean the only stat
   * that can invent precision the series never had -- see `displayMean`.
   */
  integral: boolean
}

interface StatPoint {
  value: number | null | undefined
  partial?: PartialKind | null
}

/** Summary numbers for a series, computed over its *complete* buckets only.
 *
 * A partial bucket is a period the range cut off part-way (see lib/partialBuckets.ts), and
 * for a summed series its total is a fraction of a real one -- three days into a week, a
 * step count is a third of what it will be. Averaging that in drags the mean down and hands
 * back a `min` that no week actually had. The chart already refuses to label those points
 * for the same reason, so the strip agrees with the end label sitting beside it rather than
 * quoting a different "latest" from the same series.
 *
 * Falls back to every point when they're *all* partial, the way labelIndex does -- a single
 * "Today" bucket should still report its own number rather than four dashes.
 */
export function seriesStats(points: readonly StatPoint[]): SeriesStats | null {
  const complete = points.filter((p) => !p.partial)
  const values = valuesOf(complete.length > 0 ? complete : points)
  if (values.length === 0) return null

  let min = Infinity
  let max = -Infinity
  let total = 0
  for (const value of values) {
    if (value < min) min = value
    if (value > max) max = value
    total += value
  }
  return {
    latest: values[values.length - 1],
    min,
    max,
    mean: total / values.length,
    integral: values.every(Number.isInteger),
  }
}

function valuesOf(points: readonly StatPoint[]): number[] {
  const values: number[] = []
  for (const point of points) {
    if (point.value != null && Number.isFinite(point.value)) values.push(point.value)
  }
  return values
}

export interface StatEntry {
  label: string
  value: string
}

/** The mean, rounded back to the precision of the series it came from.
 *
 * A mean is the one stat here that can be more precise than its inputs, and two decimals on
 * a step count read as a measurement rather than as an artefact of dividing -- they claim a
 * hundredth of a step was counted. Where the values themselves carry decimals -- a weight, a
 * heart-rate average -- the mean keeps them.
 */
export function displayMean(stats: SeriesStats): number | null {
  if (stats.mean == null) return null
  return stats.integral ? Math.round(stats.mean) : stats.mean
}

/** The four stats as display rows, formatted by the caller -- it's the one that knows the
 * metric's unit and how its numbers are written elsewhere on the card.
 */
export function statEntries(
  stats: SeriesStats | null,
  format: (value: number) => string,
): StatEntry[] {
  if (!stats) return []
  return [
    { label: 'Latest', value: stats.latest != null ? format(stats.latest) : '—' },
    { label: 'Min', value: stats.min != null ? format(stats.min) : '—' },
    { label: 'Max', value: stats.max != null ? format(stats.max) : '—' },
    { label: 'Mean', value: displayMean(stats) != null ? format(displayMean(stats)!) : '—' },
  ]
}
