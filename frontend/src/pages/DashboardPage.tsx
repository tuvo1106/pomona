import { useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { ChevronRight } from 'lucide-react'
import { api } from '@/api/client'
import { ActivityRings } from '@/components/ActivityRings'
import { AllCharts } from '@/components/AllCharts'
import { AllMetrics } from '@/components/AllMetrics'
import { BucketSelect } from '@/components/BucketSelect'
import { DataFreshness } from '@/components/DataFreshness'
import { Overview, OverviewSkeleton } from '@/components/Overview'
import { SectionNav } from '@/components/SectionNav'
import { TimeRangeSelect } from '@/components/TimeRangeSelect'
import { WorkoutsList } from '@/components/WorkoutsList'
import { WorkoutsSummary } from '@/components/WorkoutsSummary'
import { Button } from '@/components/ui/button'
import { useAnchoredRange } from '@/hooks/useAnchoredRange'
import { useExpandedGroups } from '@/hooks/useExpandedGroups'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { useStickyHeaderOffset } from '@/hooks/useStickyHeaderOffset'
import { groupSectionId, presentGroups, PREVIEW_COUNT } from '@/lib/metricGroups'
import { isBucketOption, resolveBucket } from '@/lib/timeRange'
import { cn } from '@/lib/utils'

/** Breathing room between the sticky section nav and a heading it scrolls to. Passed to
 * SectionNav as well as applied here, so the bar sets its current-section line from the
 * same number rather than the two being tuned independently. */
const SCROLL_GAP = 12

export function DashboardPage() {
  const {
    rangeOption,
    setRangeOption,
    customRange,
    setCustomRange,
    range,
    ready,
    latestDate,
    ingestedAt,
  } = useAnchoredRange('30d')
  const [bucketOption, setBucketOption] = useSearchParamState('bucket', 'auto', isBucketOption)
  const bucket = useMemo(() => resolveBucket(range, bucketOption), [range, bucketOption])
  const headerOffset = useStickyHeaderOffset()
  // Reported by SectionNav once it has measured itself: a section jumped to has to clear
  // the app header *and* the nav bar stuck under it, and the nav wraps to two rows narrow.
  const [navHeight, setNavHeight] = useState(0)
  const { expandedGroups, toggleGroup, expandGroups, collapseAll } = useExpandedGroups()

  // Owned here rather than inside AllCharts: the section nav and the chart grid have to
  // agree on which groups exist, and deriving both from one response is the only way they
  // can't disagree (a nav entry with no heading to scroll to, or the reverse).
  const {
    data: metricTypes,
    isLoading: groupsLoading,
    error: groupsError,
  } = useQuery({
    queryKey: ['metric-types', range],
    queryFn: () => api.metricTypes(range),
    enabled: ready,
    // Keep the previous range's groups on screen while the new ones load. Without this,
    // every range change tore the whole Trends region down to six skeletons and rebuilt it
    // -- forty cards and their section headings, a several-thousand-pixel collapse and
    // re-expansion -- which no amount of fading the individual cards back in can soften.
    // Safe to show stale here in a way it wouldn't be for the overview: this query returns
    // which metric types exist, not any of their values, so the worst case is a card that
    // appears and then goes away because the new range has no data for it. Each chart's own
    // query still reloads underneath, with its own skeleton.
    placeholderData: keepPreviousData,
  })

  const groups = useMemo(
    () => (metricTypes ? presentGroups(metricTypes.map((metric) => metric.type)) : []),
    [metricTypes],
  )
  const sections = useMemo(
    () =>
      groups.map((group) => ({
        id: groupSectionId(group.id),
        label: group.label,
        color: group.color,
        count: group.charts.length,
      })),
    [groups],
  )

  // Only groups with something hidden can be expanded, so "show all" can't claim to do
  // anything for a dashboard whose groups are all small.
  const expandableIds = useMemo(
    () => groups.filter((group) => group.charts.length > PREVIEW_COUNT).map((group) => group.id),
    [groups],
  )
  const allExpanded =
    expandableIds.length > 0 && expandableIds.every((id) => expandedGroups.has(id))

  const [showAllMetrics, setShowAllMetrics] = useState(false)

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-foreground text-base font-semibold">Dashboard</h2>
          <p className="text-muted-foreground text-xs">
            Everything your devices recorded, by section.
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-x-4 gap-y-2">
          <DataFreshness latestDate={latestDate} ingestedAt={ingestedAt} />
          <div className="flex flex-wrap items-center gap-2">
            <BucketSelect value={bucketOption} onChange={setBucketOption} />
            <TimeRangeSelect
              value={rangeOption}
              onChange={setRangeOption}
              custom={customRange}
              onCustomChange={setCustomRange}
            />
          </div>
        </div>
      </div>

      {/* Nothing below mounts until the range is anchored -- see useAnchoredRange. */}
      {!ready ? (
        <OverviewSkeleton />
      ) : (
        <>
          <Overview range={range} />

          {/* Full width and above Trends: the rings + calendar are the most recognizable
              view of this data, and the calendar needs the width at long ranges. */}
          <section>
            <ActivityRings range={range} />
          </section>

          <section className="space-y-3">
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <h2 className="text-foreground text-base font-semibold">Trends</h2>
                {/* "Click any chart to expand it" is gone: each card now carries an expand
                    icon, so the affordance is on the thing it applies to rather than in a
                    line of prose above forty of them. Nothing is left to say once every
                    section is showing everything. */}
                {!allExpanded && (
                  <p className="text-muted-foreground text-xs">
                    Top {PREVIEW_COUNT} per section.
                  </p>
                )}
              </div>
              {expandableIds.length > 0 && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  aria-expanded={allExpanded}
                  onClick={() => (allExpanded ? collapseAll() : expandGroups(expandableIds))}
                >
                  {allExpanded ? 'Show fewer charts' : 'Show all charts'}
                </Button>
              )}
            </div>

            <SectionNav
              sections={sections}
              offset={headerOffset}
              scrollGap={SCROLL_GAP}
              onStickyHeightChange={setNavHeight}
            />

            <AllCharts
              groups={groups}
              isLoading={groupsLoading}
              error={groupsError}
              range={range}
              bucket={bucket}
              expandedGroups={expandedGroups}
              onToggleGroup={toggleGroup}
              // Clears the app header and the section nav sitting under it.
              scrollOffset={headerOffset + navHeight + SCROLL_GAP}
            />
          </section>

          <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <WorkoutsList range={range} />
            <WorkoutsSummary range={range} />
          </section>

          {/* Diagnostics, not dashboard: a record count and date span per type, for checking
              what an export actually contains. Kept here as a closed drawer rather than
              promoted to its own route -- it would need a fifth nav item, and the header
              already scrolls sideways on a phone. Mounted only once opened, so its all-time
              query doesn't run on every page load. */}
          <section className="border-border border-t pt-6">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="-ml-2.5"
              aria-expanded={showAllMetrics}
              aria-controls="all-tracked-metrics"
              onClick={() => setShowAllMetrics((open) => !open)}
            >
              <ChevronRight
                aria-hidden
                className={cn('transition-transform', showAllMetrics && 'rotate-90')}
              />
              All tracked metrics
            </Button>
            {/* Always rendered so the button's aria-controls points at something even while
                closed, but kept empty until opened so the query still waits. */}
            <div id="all-tracked-metrics" hidden={!showAllMetrics} className="mt-3">
              {showAllMetrics && <AllMetrics />}
            </div>
          </section>
        </>
      )}
    </main>
  )
}
