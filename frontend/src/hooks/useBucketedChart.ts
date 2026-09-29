import { useMemo } from 'react'
import type { TableColumn } from '@/components/ExpandableChartCard'
import { formatBucketDate, makeDateLabelFormatter, makeDateTickFormatter } from '@/lib/formatDate'
import type { Bucket } from '@/lib/timeRange'

// Stable fallback so the memos below don't recompute on every render while loading.
const NO_POINTS: never[] = []

/** The table's first column. Every bucketed chart's `tableRows` carry it (see below). */
export const DATE_COLUMN: TableColumn = { key: 'date', header: 'Date' }

/** What every date-bucketed chart builds from its points: the x-axis tick formatter, the
 * tooltip's date label, and the rows behind the card's table view, each dated the way its
 * bucket reads ("Week of ...").
 *
 * `cells` supplies a row's value columns. Keep it stable -- defined at module scope, or
 * memoised -- or the rows are rebuilt on every render.
 */
export function useBucketedChart<P extends { date: string }>(
  data: P[] | undefined,
  bucket: Bucket,
  cells: (point: P) => Record<string, string | number>,
) {
  const points: P[] = data ?? NO_POINTS
  const tickFormatter = useMemo(
    () => makeDateTickFormatter(points.map((p) => p.date), bucket),
    [points, bucket],
  )
  const labelFormatter = useMemo(() => makeDateLabelFormatter(bucket), [bucket])
  const tableRows = useMemo(
    () => points.map((p) => ({ date: formatBucketDate(p.date, bucket), ...cells(p) })),
    [points, bucket, cells],
  )
  return { points, tickFormatter, labelFormatter, tableRows }
}
