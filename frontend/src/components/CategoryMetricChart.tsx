import { useMemo } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { CategoryMetricMode } from '@/api/client'
import { barEndLabel } from '@/components/ChartEndLabels'
import { ChartStateWrapper } from '@/components/ChartStateWrapper'
import { ChartTooltip } from '@/components/ChartTooltip'
import { ExpandableChartCard } from '@/components/ExpandableChartCard'
import { useCategoryMetricTimeseries } from '@/hooks/queries'
import { DATE_COLUMN, timeseriesCells, useBucketedChart } from '@/hooks/useBucketedChart'
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
import { formatAxisNumber } from '@/lib/formatNumber'
import { seriesStats, statEntries } from '@/lib/seriesStats'
import { labelIndex, partialBarShape } from '@/lib/partialBuckets'
import type { Bucket, DateRange } from '@/lib/timeRange'
import { displayUnit, valueColumnHeader } from '@/lib/units'

interface CategoryMetricChartProps {
  metricType: string
  mode: CategoryMetricMode
  title: string
  range: DateRange
  bucket: Bucket
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
  const { data, isLoading, error } = useCategoryMetricTimeseries(metricType, mode, range, {
    bucket,
    valuePrefix,
  })
  const { points, tickFormatter, labelFormatter, tableRows } = useBucketedChart(
    data?.points,
    bucket,
    timeseriesCells,
  )
  // The end label sits on the last complete bucket; partial bars are faded (see
  // lib/partialBuckets and `partialBarShape`).
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
        DATE_COLUMN,
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
