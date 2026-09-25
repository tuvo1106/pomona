import { useId, useMemo } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { TimeseriesPoint } from '@/api/client'
import { makeLineEndDot, makePartialDot } from '@/components/ChartEndLabels'
import { ChartStateWrapper } from '@/components/ChartStateWrapper'
import { ChartTooltip } from '@/components/ChartTooltip'
import { ExpandableChartCard } from '@/components/ExpandableChartCard'
import { useChartDialog } from '@/hooks/useChartDialog'
import { useMetricTimeseries } from '@/hooks/useMetricTimeseries'
import { axisScale } from '@/lib/axisScale'
import {
  CHART_ANIMATION_DURATION,
  CHART_AREA_FILL_OPACITY,
  CHART_GRID_PROPS,
  CHART_X_AXIS_PROPS,
  CHART_Y_AXIS_PROPS,
} from '@/lib/chartStyle'
import { formatBucketDate, makeDateLabelFormatter, makeDateTickFormatter } from '@/lib/formatDate'
import { formatAxisNumber } from '@/lib/formatNumber'
import { friendlyName } from '@/lib/metricNames'
import { labelIndex, splitPartial, withPartialSuffix } from '@/lib/partialBuckets'
import { seriesStats, statEntries } from '@/lib/seriesStats'
import type { DateRange } from '@/lib/timeRange'
import { displayUnit, valueColumnHeader } from '@/lib/units'

// Stable fallback so the memos below don't recompute on every render while loading.
const NO_POINTS: TimeseriesPoint[] = []

/** Apple's export stores percentage types (SpO2, double support, walking asymmetry,
 * steadiness, ...) as 0-1 fractions while labelling the unit "%", so 97% arrives as 0.97.
 * Scaled x100 for display -- chart, end label, tooltip and table alike. Only when the whole
 * series is <= 1, so a source that already writes 0-100 under "%" isn't blown up x100.
 */
function toDisplayPoints(
  points: TimeseriesPoint[],
  unit: string | null | undefined,
): TimeseriesPoint[] {
  const isFraction = unit === '%' && points.every((p) => p.value == null || p.value <= 1)
  if (!isFraction) return points
  return points.map((p) => ({ ...p, value: p.value == null ? null : p.value * 100 }))
}

interface MetricChartProps {
  metricType: string
  title?: string
  range: DateRange
  bucket: 'day' | 'week' | 'month'
  /** The metric group's hue (see MetricGroup.color). Defaults to the generic chart
   * color for a chart rendered outside a group. */
  color?: string
}

export function MetricChart({
  metricType,
  title,
  range: dashboardRange,
  bucket: dashboardBucket,
  color = 'var(--chart-1)',
}: MetricChartProps) {
  // The expanded dialog can point this one chart at its own range without moving the
  // dashboard; while it's closed these are the dashboard's own (see useChartDialog).
  const dialog = useChartDialog(dashboardRange, dashboardBucket)
  const { range, bucket } = dialog
  const { data, isLoading, error } = useMetricTimeseries(metricType, { ...range, bucket })
  const label = title ?? friendlyName(metricType)

  const points = useMemo(
    () => toDisplayPoints(data?.points ?? NO_POINTS, data?.unit),
    [data?.points, data?.unit],
  )
  const scale = useMemo(
    () =>
      axisScale(
        points.map((p) => p.value),
        { zeroBaseline: data?.aggregation_mode !== 'avg' },
      ),
    [points, data?.aggregation_mode],
  )
  // Partial buckets (see lib/partialBuckets.ts) are drawn as a dashed segment off the solid
  // line, and the end label moves to the last complete bucket.
  const chartPoints = useMemo(() => splitPartial(points), [points])
  const endIndex = useMemo(() => labelIndex(points), [points])
  const lineEndDot = useMemo(() => makeLineEndDot(color, endIndex), [color, endIndex])
  const partialDot = useMemo(() => makePartialDot(color, endIndex), [color, endIndex])
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
  // formatAxisNumber, not the axis scale's own formatter: that one abbreviates to fit a
  // tick ("5K"), which is right for a label repeated up the side of a chart and wrong for a
  // figure quoted once. The strip is read against the end label on the chart below it, and
  // that one is written out in full.
  const stats = useMemo(() => statEntries(seriesStats(points), formatAxisNumber), [points])
  // A weekly or monthly total is a discrete quantity per bucket: `monotone` would round the
  // steps between them into humps that imply values the series never had. Point-in-time
  // (avg-mode) metrics do vary continuously between buckets, so those keep the smooth curve.
  const curve = data?.aggregation_mode === 'sum' ? 'linear' : 'monotone'
  // Unique per chart instance -- ~40 of these share one document, and a duplicate gradient id
  // would have them all paint with whichever definition rendered last. useId's colons are
  // stripped: they're legal in an id but hostile in anything that parses it as a selector.
  const gradientId = `metric-area-${useId().replace(/:/g, '')}`
  // A summed series is a total per bucket, so the bucket belongs in the unit (see lib/units).
  const unitContext = {
    type: metricType,
    unit: data?.unit,
    mode: data?.aggregation_mode,
    bucket,
  }

  return (
    <ExpandableChartCard
      title={label}
      unit={displayUnit(unitContext)}
      tableColumns={[
        { key: 'date', header: 'Date' },
        { key: 'value', header: valueColumnHeader(unitContext), numeric: true },
      ]}
      tableRows={tableRows}
      dialog={dialog}
      stats={stats}
      renderChart={(height) => (
        <ChartStateWrapper
          isLoading={isLoading}
          error={error}
          isEmpty={points.length === 0}
          height={height}
          errorMessage={`Failed to load ${label}.`}
        >
          <ResponsiveContainer width="100%" height={height}>
            <ComposedChart data={chartPoints}>
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop
                    offset="0%"
                    stopColor={color}
                    stopOpacity={CHART_AREA_FILL_OPACITY}
                  />
                  <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid {...CHART_GRID_PROPS} />
              <XAxis {...CHART_X_AXIS_PROPS} tickFormatter={tickFormatter} />
              <YAxis
                {...CHART_Y_AXIS_PROPS}
                width={44}
                domain={scale?.domain}
                ticks={scale?.ticks}
                tickFormatter={scale?.format ?? formatAxisNumber}
              />
              <Tooltip content={ChartTooltip} labelFormatter={labelFormatter} />
              {/* Area and line share `name` so ChartTooltip shows one row where they meet.
                  The partial tail stays an unfilled dashed line: the wash stopping at the
                  last complete bucket is itself the signal that the rest is incomplete. */}
              <Area
                type={curve}
                dataKey="solid"
                name="value"
                stroke={color}
                fill={`url(#${gradientId})`}
                // recharts defaults an Area to fillOpacity 0.6, which would multiply the
                // gradient's stops down to about 0.11 at the top. The gradient owns the
                // opacity here, so the mark itself stays fully opaque.
                fillOpacity={1}
                dot={lineEndDot}
                activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--card)' }}
                strokeWidth={2}
                animationDuration={CHART_ANIMATION_DURATION}
              />
              <Line
                type={curve}
                dataKey="dashed"
                name="value"
                stroke={color}
                strokeDasharray="4 4"
                strokeOpacity={0.6}
                dot={partialDot}
                activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--card)' }}
                strokeWidth={2}
                animationDuration={CHART_ANIMATION_DURATION}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartStateWrapper>
      )}
    />
  )
}
