import { BloodPressureChart } from '@/components/BloodPressureChart'
import { CategoryMetricChart } from '@/components/CategoryMetricChart'
import { CardErrorFallback, ErrorBoundary } from '@/components/ErrorBoundary'
import { MetricChart } from '@/components/MetricChart'
import { SleepChart } from '@/components/SleepChart'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { CONTENT_FADE_IN } from '@/lib/transitions'
import { cn } from '@/lib/utils'
import { PREVIEW_COUNT, groupSectionId, specKey, specTitle, type MetricGroup } from '@/lib/metricGroups'
import type { DateRange } from '@/lib/timeRange'

interface AllChartsProps {
  groups: MetricGroup[]
  isLoading: boolean
  error: unknown
  range: DateRange
  bucket: 'day' | 'week' | 'month'
  /** Group ids showing all of their charts rather than the first PREVIEW_COUNT. */
  expandedGroups: ReadonlySet<string>
  onToggleGroup: (groupId: string) => void
  /** Where the sticky bars end, so a section jumped to lands below them. */
  scrollOffset: number
}

export function AllCharts({
  groups,
  isLoading,
  error,
  range,
  bucket,
  expandedGroups,
  onToggleGroup,
  scrollOffset,
}: AllChartsProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {/* 268px is what a chart card measures: header, then a CardContent holding the
            200px PREVIEW_HEIGHT the chart is always drawn at. Unlike the table cards, this
            doesn't move with the data, so the skeleton can match it exactly and the grid
            doesn't shift when the real cards arrive. */}
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-[268px] w-full" />
        ))}
      </div>
    )
  }
  if (error) {
    return <div className="text-destructive text-sm">Failed to load metrics.</div>
  }
  if (groups.length === 0) return null

  return (
    <div className={cn('space-y-8', CONTENT_FADE_IN)}>
      {groups.map((group) => {
        const isExpanded = expandedGroups.has(group.id)
        const hiddenCount = group.charts.length - PREVIEW_COUNT
        const charts = isExpanded ? group.charts : group.charts.slice(0, PREVIEW_COUNT)

        return (
          <section
            key={group.id}
            id={groupSectionId(group.id)}
            // Scroll-margin from the measured header rather than a utility class: two
            // sticky bars stack above this one, and the top one changes height at `sm`.
            style={{ scrollMarginTop: scrollOffset }}
            className="space-y-3"
            aria-labelledby={`${groupSectionId(group.id)}-heading`}
          >
            <div className="flex items-center justify-between gap-2">
              {/* The dot, not the text, carries the group's color: colored text would break
                  the app-wide rule that identity rides on a mark beside the words, never on
                  the words themselves (see ChartTooltip). */}
              <h3
                id={`${groupSectionId(group.id)}-heading`}
                className="text-muted-foreground flex items-center gap-2 text-xs font-semibold tracking-wide uppercase"
              >
                <span
                  aria-hidden
                  className="size-2 rounded-full"
                  style={{ backgroundColor: group.color }}
                />
                {group.label}
                <span className="text-muted-foreground/70 tabular-nums">
                  {group.charts.length}
                </span>
              </h3>
              {hiddenCount > 0 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => onToggleGroup(group.id)}
                  aria-expanded={isExpanded}
                  aria-controls={`${groupSectionId(group.id)}-charts`}
                >
                  {isExpanded ? 'Show fewer' : `Show all ${group.charts.length}`}
                </Button>
              )}
            </div>
            <div
              id={`${groupSectionId(group.id)}-charts`}
              className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3"
            >
              {charts.map((spec) => {
                const key = specKey(spec)
                // One boundary per card. ~40 of these render from the same export, and a
                // value that trips a formatter in one metric is unlikely to be present in
                // the others -- without this, that one card takes the page down and hides
                // the thirty-nine that would have rendered. resetKey on the range so
                // changing it retries a card that failed on the old data.
                return (
                  <ErrorBoundary
                    key={key}
                    resetKey={`${range.start}|${range.end}|${bucket}`}
                    fallback={(_error, reset) => (
                      <CardErrorFallback title={specTitle(spec)} reset={reset} />
                    )}
                  >
                    {spec.kind === 'blood-pressure' ? (
                      <BloodPressureChart range={range} bucket={bucket} />
                    ) : spec.kind === 'sleep' ? (
                      <SleepChart range={range} bucket={bucket} color={group.color} />
                    ) : spec.kind === 'category' ? (
                      <CategoryMetricChart
                        metricType={spec.type}
                        mode={spec.mode}
                        title={spec.title}
                        range={range}
                        bucket={bucket}
                        valuePrefix={spec.valuePrefix}
                        color={group.color}
                      />
                    ) : (
                      <MetricChart
                        metricType={spec.type}
                        title={spec.title}
                        range={range}
                        bucket={bucket}
                        color={group.color}
                      />
                    )}
                  </ErrorBoundary>
                )
              })}
            </div>
          </section>
        )
      })}
    </div>
  )
}
