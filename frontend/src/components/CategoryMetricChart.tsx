import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Rectangle,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type BarShapeProps,
} from 'recharts'
import { api, type CategoryMetricMode, type TimeseriesPoint } from '@/api/client'
import { barEndLabel } from '@/components/ChartEndLabels'
import { ChartStateWrapper } from '@/components/ChartStateWrapper'
import { ChartTooltip } from '@/components/ChartTooltip'
import { ExpandableChartCard } from '@/components/ExpandableChartCard'
import { useChartDialog } from '@/hooks/useChartDialog'
import { axisScale } from '@/lib/axisScale'
import {
  CHART_ANIMATION_DURATION,
  CHART_BAR_RADIUS,
  CHART_GRID_PROPS,
  CHART_MAX_BAR_SIZE,
  CHART_X_AXIS_PROPS,
  CHART_Y_AXIS_PROPS,
} from '@/lib/chartStyle'
import { formatBucketDate, makeDateLabelFormatter, makeDateTickFormatter } from '@/lib/formatDate'
import { formatAxisNumber } from '@/lib/formatNumber'
import { seriesStats, statEntries } from '@/lib/seriesStats'
import { labelIndex, withPartialSuffix } from '@/lib/partialBuckets'
import type { DateRange } from '@/lib/timeRange'
import { displayUnit, valueColumnHeader } from '@/lib/units'

// Stable fallback so the memos below don't recompute on every render while loading.
const NO_POINTS: TimeseriesPoint[] = []

/** A partial bucket's bar at reduced opacity, so it doesn't read as a real drop. A `shape`
 * rather than per-bar `<Cell>`s, which recharts 3 deprecates.
 */
function partialBarShape(props: BarShapeProps) {
  const partial = (props.payload as TimeseriesPoint | undefined)?.partial
  return <Rectangle {...props} fillOpacity={partial ? 0.4 : 1} />
}

interface CategoryMetricChartProps {
  metricType: string
  mode: CategoryMetricMode
  title: string
  range: DateRange
  bucket: 'day' | 'week' | 'month'
  valuePrefix?: string
  /** The metric group's hue (see MetricGroup.color). Defaults to the generic chart
   * color for a chart rendered outside a group. */
  color?: string
}

export function CategoryMetricChart({
  metricType,
  mode,
  title,
  range: dashboardRange,
  bucket: dashboardBucket,
  valuePrefix,
  color = 'var(--chart-2)',
}: CategoryMetricChartProps) {
  const dialog = useChartDialog(dashboardRange, dashboardBucket)
  const { range, bucket } = dialog
  const params = { ...range, bucket, value_prefix: valuePrefix }
  const { data, isLoading, error } = useQuery({
    queryKey: ['category-metric-timeseries', metricType, mode, params],
    queryFn: () => api.categoryMetricTimeseries(metricType, mode, params),
  })
  const points = data?.points ?? NO_POINTS
  // The end label sits on the last complete bucket; partial bars are faded (see
  // lib/partialBuckets.ts and `partialBarShape` below).
  const endIndex = useMemo(() => labelIndex(points), [points])
  const endLabel = useMemo(() => barEndLabel(endIndex), [endIndex])
  const scale = useMemo(
    () =>
      axisScale(
        points.map((p) => p.value),
        { zeroBaseline: true, integer: mode === 'count' },
      ),
    [points, mode],
  )
  const tickFormatter = useMemo(
    () => makeDateTickFormatter(points.map((p) => p.date), bucket),
    [points, bucket],
  )
  const labelFormatter = useMemo(() => makeDateLabelFormatter(bucket), [bucket])
  const tableRows = useMemo(
    () =>
      points.map((p) => ({
        date: formatBucketDate(p.date, bucket),
        value: p.value != null ? withPartialSuffix(formatAxisNumber(p.value), p.partial) : '—',
      })),
    [points, bucket],
  )

  // Both modes total their bucket -- count sums events, duration sums minutes -- so both
  // take the per-bucket suffix (see lib/units.ts). Claimed only once the response is in:
  // asserting "per week" while the unit is still unknown would caption a loading (or
  // failed) card as a weekly count, and a duration card would then flip to "min/wk".
  const unitContext = { type: metricType, unit: data?.unit, mode: data && ('sum' as const), bucket }

  const stats = useMemo(() => statEntries(seriesStats(points), formatAxisNumber), [points])

  return (
    <ExpandableChartCard
      title={title}
      unit={displayUnit(unitContext)}
      dialog={dialog}
      stats={stats}
      tableColumns={[
        { key: 'date', header: 'Date' },
        { key: 'value', header: valueColumnHeader(unitContext), numeric: true },
      ]}
      tableRows={tableRows}
      renderChart={(height) => (
        <ChartStateWrapper
          isLoading={isLoading}
          error={error}
          isEmpty={points.length === 0}
          height={height}
          errorMessage={`Failed to load ${title}.`}
        >
          <ResponsiveContainer width="100%" height={height}>
            <BarChart data={points}>
              <CartesianGrid {...CHART_GRID_PROPS} />
              <XAxis {...CHART_X_AXIS_PROPS} tickFormatter={tickFormatter} />
              <YAxis
                {...CHART_Y_AXIS_PROPS}
                width={36}
                domain={scale?.domain}
                ticks={scale?.ticks}
                tickFormatter={scale?.format ?? formatAxisNumber}
                allowDecimals={mode !== 'count'}
              />
              <Tooltip content={ChartTooltip} labelFormatter={labelFormatter} />
              <Bar
                dataKey="value"
                fill={color}
                radius={CHART_BAR_RADIUS}
                maxBarSize={CHART_MAX_BAR_SIZE}
                shape={partialBarShape}
                label={endLabel}
                animationDuration={CHART_ANIMATION_DURATION}
              />
            </BarChart>
          </ResponsiveContainer>
        </ChartStateWrapper>
      )}
    />
  )
}
