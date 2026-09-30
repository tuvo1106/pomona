import { useMemo } from 'react'
import type { TimeseriesPoint } from '@/api/client'
import type { TableColumn } from '@/components/ExpandableChartCard'
import { formatBucketDate, makeDateLabelFormatter, makeDateTickFormatter } from '@/lib/formatDate'
import { formatAxisNumber } from '@/lib/formatNumber'
import { withPartialSuffix } from '@/lib/partialBuckets'
import type { Bucket } from '@/lib/timeRange'

// Stable fallback so the memos below don't recompute on every render while loading.
const NO_POINTS: never[] = []

/** The table's first column. Every bucketed chart's `tableRows` carry it (see below). */
export const DATE_COLUMN: TableColumn = { key: 'date', header: 'Date' }

/** A date-bucketed chart's x-axis tick formatter and tooltip date label, plus its points
 * with a stable empty fallback while loading. For a chart with no table view; one that has
 * a table wants `useBucketedChart`, which builds on this.
 */
export function useBucketDates<P extends { date: string }>(data: P[] | undefined, bucket: Bucket) {
  const points: P[] = data ?? NO_POINTS
  const tickFormatter = useMemo(
    () => makeDateTickFormatter(points.map((p) => p.date), bucket),
    [points, bucket],
  )
  const labelFormatter = useMemo(() => makeDateLabelFormatter(bucket), [bucket])
  return { points, tickFormatter, labelFormatter }
}

/** What a date-bucketed chart with a table view builds from its points: `useBucketDates`,
 * plus the rows behind the card's table, each dated the way its bucket reads ("Week of ...").
 *
 * `cells` supplies a row's value columns. Keep it stable -- defined at module scope, or
 * memoised -- or the rows are rebuilt on every render. The formatted date is written after
 * the cells, so a `date` key among them can't replace it.
 */
export function useBucketedChart<P extends { date: string }>(
  data: P[] | undefined,
  bucket: Bucket,
  cells: (point: P) => Record<string, string | number>,
) {
  const dates = useBucketDates(data, bucket)
  const { points } = dates
  const tableRows = useMemo(
    () => points.map((p) => ({ ...cells(p), date: formatBucketDate(p.date, bucket) })),
    [points, bucket, cells],
  )
  return { ...dates, tableRows }
}

/** A timeseries point's table cell: its value, noting a bucket still in progress. */
export function timeseriesCells(point: TimeseriesPoint): { value: string } {
  return {
    value:
      point.value != null ? withPartialSuffix(formatAxisNumber(point.value), point.partial) : '—',
  }
}
