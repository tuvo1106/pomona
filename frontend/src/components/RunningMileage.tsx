import { useMemo } from 'react'
import { Bar, BarChart, Cell, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ChartTooltip } from '@/components/ChartTooltip'
import { DataCard } from '@/components/DataCard'
import { useRunningMileage } from '@/hooks/useWorkouts'
import {
  CHART_ANIMATION_DURATION,
  CHART_AXIS_STROKE,
  CHART_AXIS_TICK,
  CHART_GRID_PROPS,
  CHART_Y_AXIS_PROPS,
} from '@/lib/chartStyle'
import { makeDateLabelFormatter, makeDateTickFormatter } from '@/lib/formatDate'
import type { DateRange } from '@/lib/timeRange'

/** Running distance for the selected range: the total as a headline, and a bar per calendar
 * month under it. Follows the dashboard's range like every other card, so "This year" is
 * the year-to-date mileage.
 *
 * The API sums in one unit (converting a history that spans a km/mi settings change), so the
 * headline and the bars always agree with each other.
 *
 * A month cut short -- the one still in progress, or one the range or the export starts
 * partway into -- is drawn faded, the bar-chart form of the dashed tail the line charts use
 * (see lib/partialBuckets): its short bar is a partial count, not a slow month.
 */

// Opacity of a partial month's bar. Faded, not hidden: the miles are real, just incomplete.
const PARTIAL_BAR_OPACITY = 0.4
export function RunningMileage({ range }: { range: DateRange }) {
  const { data, isLoading, error } = useRunningMileage(range)
  const unit = data?.unit ?? ''
  const total = data?.total_distance
  const tickFormatter = useMemo(
    () => makeDateTickFormatter(data?.points.map((p) => p.date) ?? [], 'month'),
    [data],
  )

  return (
    <DataCard
      title="Running mileage"
      isLoading={isLoading}
      error={error}
      isEmpty={!data || data.runs === 0}
      errorMessage="Failed to load running mileage."
      emptyMessage="No runs in this range."
      skeletonHeight={260}
    >
      {data && (
        <div className="space-y-4">
          <div className="flex items-baseline gap-1.5">
            <span className="text-2xl font-semibold tabular-nums">
              {total != null
                ? total.toLocaleString('en-US', {
                    minimumFractionDigits: 1,
                    maximumFractionDigits: 1,
                  })
                : '—'}
            </span>
            {unit && <span className="text-muted-foreground text-sm">{unit}</span>}
            <span className="text-muted-foreground ml-2 text-sm">
              across {data.runs.toLocaleString('en-US')} {data.runs === 1 ? 'run' : 'runs'}
            </span>
          </div>
          {/* Said out loud: otherwise "12 mi across 8 runs" passes for all eight. */}
          {data.unmeasured_runs > 0 && (
            <p className="text-muted-foreground -mt-3 text-xs">
              {data.unmeasured_runs.toLocaleString('en-US')} of these{' '}
              {data.unmeasured_runs === 1 ? 'has' : 'have'} no recorded distance and{' '}
              {data.unmeasured_runs === 1 ? "isn't" : "aren't"} in the total.
            </p>
          )}
          <div style={{ height: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.points} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid {...CHART_GRID_PROPS} />
                <XAxis
                  dataKey="date"
                  tick={CHART_AXIS_TICK}
                  stroke={CHART_AXIS_STROKE}
                  axisLine={false}
                  tickLine={false}
                  minTickGap={16}
                  tickFormatter={tickFormatter}
                />
                <YAxis {...CHART_Y_AXIS_PROPS} width={40} />
                <Tooltip
                  cursor={{ fill: 'var(--muted)', opacity: 0.4 }}
                  content={ChartTooltip}
                  labelFormatter={makeDateLabelFormatter('month')}
                />
                <Bar
                  dataKey="distance"
                  name={unit ? `Distance (${unit})` : 'Distance'}
                  fill="var(--chart-1)"
                  radius={[3, 3, 0, 0]}
                  animationDuration={CHART_ANIMATION_DURATION}
                >
                  {data.points.map((point) => (
                    <Cell
                      key={point.date}
                      fillOpacity={point.partial ? PARTIAL_BAR_OPACITY : 1}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </DataCard>
  )
}
