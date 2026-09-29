import { useMemo } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { SleepPoint } from '@/api/client'
import { barEndLabel } from '@/components/ChartEndLabels'
import { ChartStateWrapper } from '@/components/ChartStateWrapper'
import { ChartTooltip } from '@/components/ChartTooltip'
import { ExpandableChartCard } from '@/components/ExpandableChartCard'
import { DATE_COLUMN, useBucketedChart } from '@/hooks/useBucketedChart'
import { useChartDialog } from '@/hooks/useChartDialog'
import { useSleep } from '@/hooks/useSleep'
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
import type { Bucket, DateRange } from '@/lib/timeRange'

function sleepCells(point: SleepPoint) {
  return { hours: point.hours != null ? formatAxisNumber(point.hours) : '—' }
}

export function SleepChart({
  range: dashboardRange,
  bucket: dashboardBucket,
  color = 'var(--chart-2)',
}: {
  range: DateRange
  bucket: Bucket
  /** The metric group's hue (see MetricGroup.color). Defaults to the generic chart
   * color for a chart rendered outside a group. */
  color?: string
}) {
  const dialog = useChartDialog(dashboardRange, dashboardBucket)
  const { range, bucket } = dialog
  const { data, isLoading, error } = useSleep(range, bucket)
  const { points, tickFormatter, labelFormatter, tableRows } = useBucketedChart(
    data?.points,
    bucket,
    sleepCells,
  )
  const endLabel = useMemo(() => barEndLabel(points.length - 1), [points.length])
  const scale = useMemo(
    () => axisScale(points.map((p) => p.hours), { zeroBaseline: true }),
    [points],
  )

  // The API returns no partial flag for sleep, so every night counts toward the spread.
  const stats = useMemo(
    () => statEntries(seriesStats(points.map((p) => ({ value: p.hours }))), formatAxisNumber),
    [points],
  )

  return (
    <ExpandableChartCard
      title="Sleep"
      dialog={dialog}
      stats={stats}
      // Week/month buckets are the average night in that bucket, not the bucket's total --
      // so this one spells its own unit rather than going through lib/units.ts, which would
      // read a bucketed total and suffix it "/wk".
      unit={bucket === 'day' ? 'hours' : 'avg hours/night'}
      tableColumns={[
        DATE_COLUMN,
        { key: 'hours', header: bucket === 'day' ? 'Hours' : 'Avg hours/night', numeric: true },
      ]}
      tableRows={tableRows}
      renderChart={(height) => (
        <ChartStateWrapper
          isLoading={isLoading}
          error={error}
          isEmpty={points.length === 0}
          height={height}
          errorMessage="Failed to load sleep data."
        >
          <ResponsiveContainer width="100%" height={height}>
            <BarChart data={points}>
              <CartesianGrid {...CHART_GRID_PROPS} />
              <XAxis {...CHART_X_AXIS_PROPS} tickFormatter={tickFormatter} />
              <YAxis
                {...CHART_Y_AXIS_PROPS}
                width={32}
                domain={scale?.domain}
                ticks={scale?.ticks}
                tickFormatter={scale?.format ?? formatAxisNumber}
              />
              <Tooltip content={ChartTooltip} labelFormatter={labelFormatter} />
              <Bar
                dataKey="hours"
                fill={color}
                radius={CHART_BAR_RADIUS}
                maxBarSize={CHART_MAX_BAR_SIZE}
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
