import { useMemo } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { BloodPressurePoint } from '@/api/client'
import { makeLineEndDot } from '@/components/ChartEndLabels'
import { ChartLegend, type LegendEntry } from '@/components/ChartLegend'
import { ChartStateWrapper } from '@/components/ChartStateWrapper'
import { ChartTooltip } from '@/components/ChartTooltip'
import { ExpandableChartCard } from '@/components/ExpandableChartCard'
import { useBloodPressure } from '@/hooks/useBloodPressure'
import { useChartDialog } from '@/hooks/useChartDialog'
import { axisScale } from '@/lib/axisScale'
import {
  CHART_ANIMATION_DURATION,
  CHART_GRID_PROPS,
  CHART_X_AXIS_PROPS,
  CHART_Y_AXIS_PROPS,
} from '@/lib/chartStyle'
import { formatBucketDate, makeDateLabelFormatter, makeDateTickFormatter } from '@/lib/formatDate'
import { formatAxisNumber } from '@/lib/formatNumber'
import { displayMean, seriesStats, type StatEntry } from '@/lib/seriesStats'
import type { DateRange } from '@/lib/timeRange'

// Stable fallback so the memos below don't recompute on every render while loading.
const NO_POINTS: BloodPressurePoint[] = []

// Systolic first: it's the number read first when a pressure is spoken or written ("120
// over 80"), and it's the upper line on the chart, so the legend matches both.
const LEGEND_ENTRIES: LegendEntry[] = [
  { name: 'Systolic', color: 'var(--bp-systolic)' },
  { name: 'Diastolic', color: 'var(--bp-diastolic)' },
]

export function BloodPressureChart({
  range: dashboardRange,
  bucket: dashboardBucket,
}: {
  range: DateRange
  bucket: 'day' | 'week' | 'month'
}) {
  const dialog = useChartDialog(dashboardRange, dashboardBucket)
  const { range, bucket } = dialog
  const { data, isLoading, error } = useBloodPressure(range, bucket)
  const points = data?.points ?? NO_POINTS
  const scale = useMemo(
    () =>
      axisScale(
        points.flatMap((p) => [p.systolic, p.diastolic]),
        { zeroBaseline: false },
      ),
    [points],
  )

  const systolicEndDot = useMemo(
    () => makeLineEndDot('var(--bp-systolic)', points.length - 1),
    [points.length],
  )
  const diastolicEndDot = useMemo(
    () => makeLineEndDot('var(--bp-diastolic)', points.length - 1),
    [points.length],
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
        systolic: p.systolic != null ? formatAxisNumber(p.systolic) : '—',
        diastolic: p.diastolic != null ? formatAxisNumber(p.diastolic) : '—',
      })),
    [points, bucket],
  )

  // Two series, so the strip reports each one's spread separately rather than pairing the
  // extremes. A "min" of 108/64 would read as a reading that was taken, and the lowest
  // systolic and the lowest diastolic are usually different days. Latest and mean are
  // honest as pairs -- latest is one real reading, and a mean pair is plainly a derived
  // number rather than an observation.
  const stats = useMemo<StatEntry[]>(() => {
    const systolic = seriesStats(points.map((p) => ({ value: p.systolic })))
    const diastolic = seriesStats(points.map((p) => ({ value: p.diastolic })))
    if (!systolic || !diastolic) return []
    const pair = (a: number | null, b: number | null) =>
      a != null && b != null ? `${formatAxisNumber(a)}/${formatAxisNumber(b)}` : '—'
    const spread = (lo: number | null, hi: number | null) =>
      lo != null && hi != null ? `${formatAxisNumber(lo)}–${formatAxisNumber(hi)}` : '—'
    // Not systolic.latest/diastolic.latest: those are each series' last non-null value,
    // found independently. The API averages each arm per bucket, so a bucket holding only
    // one of the pair returns null for the other -- and the two "latest" values can then be
    // weeks apart while being printed as one reading. That's the same fault the split above
    // exists to avoid, so Latest comes from the newest bucket that has both.
    const latest = [...points].reverse().find((p) => p.systolic != null && p.diastolic != null)
    return [
      { label: 'Latest', value: pair(latest?.systolic ?? null, latest?.diastolic ?? null) },
      { label: 'Mean', value: pair(displayMean(systolic), displayMean(diastolic)) },
      { label: 'Systolic range', value: spread(systolic.min, systolic.max) },
      { label: 'Diastolic range', value: spread(diastolic.min, diastolic.max) },
    ]
  }, [points])

  return (
    <ExpandableChartCard
      title="Blood pressure"
      unit="mmHg"
      dialog={dialog}
      stats={stats}
      tableColumns={[
        { key: 'date', header: 'Date' },
        { key: 'systolic', header: 'Systolic', numeric: true },
        { key: 'diastolic', header: 'Diastolic', numeric: true },
      ]}
      tableRows={tableRows}
      renderChart={(height) => (
        <ChartStateWrapper
          isLoading={isLoading}
          error={error}
          isEmpty={points.length === 0}
          height={height}
          errorMessage="Failed to load blood pressure data."
        >
          <ResponsiveContainer width="100%" height={height}>
            <LineChart data={points}>
              <CartesianGrid {...CHART_GRID_PROPS} />
              <XAxis {...CHART_X_AXIS_PROPS} tickFormatter={tickFormatter} />
              <YAxis
                {...CHART_Y_AXIS_PROPS}
                width={36}
                domain={scale?.domain}
                ticks={scale?.ticks}
                tickFormatter={scale?.format ?? formatAxisNumber}
              />
              <Tooltip content={ChartTooltip} labelFormatter={labelFormatter} />
              <Legend content={<ChartLegend entries={LEGEND_ENTRIES} />} />
              <Line
                type="monotone"
                dataKey="systolic"
                name="Systolic"
                stroke="var(--bp-systolic)"
                dot={systolicEndDot}
                activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--card)' }}
                strokeWidth={2}
                animationDuration={CHART_ANIMATION_DURATION}
              />
              <Line
                type="monotone"
                dataKey="diastolic"
                name="Diastolic"
                stroke="var(--bp-diastolic)"
                dot={diastolicEndDot}
                activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--card)' }}
                strokeWidth={2}
                animationDuration={CHART_ANIMATION_DURATION}
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartStateWrapper>
      )}
    />
  )
}
