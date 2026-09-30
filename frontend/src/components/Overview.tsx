import { StatCard, StatCardSkeleton } from '@/components/StatCard'
import { useOverview } from '@/hooks/queries'
import { bloodPressureCard, METRICS, metricCard, previousLabelFor } from '@/lib/overviewStats'
import type { DateRange } from '@/lib/timeRange'
import { CONTENT_FADE_IN } from '@/lib/transitions'
import { cn } from '@/lib/utils'

// 8 cards: 2 columns on narrow screens, 4 from lg -- both divide 8 evenly, so no row ever
// ends in an orphan card.
const GRID_CLASS = 'grid grid-cols-2 gap-4 lg:grid-cols-4'

/** The overview row while it waits. Exported so the dashboard can show the same thing
 * before the range is even anchored: one definition of what this row looks like empty, and
 * one place for its height to stay in step with StatCard.
 */
export function OverviewSkeleton() {
  return (
    <section className={GRID_CLASS}>
      {Array.from({ length: 8 }, (_, i) => (
        <StatCardSkeleton key={i} />
      ))}
    </section>
  )
}

export function Overview({ range }: { range: DateRange }) {
  const { data, isLoading, error } = useOverview(range)

  if (isLoading) return <OverviewSkeleton />
  if (error) return <div className="text-destructive text-sm">Failed to load overview.</div>
  if (!data) return null

  const previousLabel = data.previous_range ? previousLabelFor(data.previous_range) : undefined
  const cards = [...METRICS.map((metric) => metricCard(metric, data)), bloodPressureCard(data)]

  return (
    <section className={cn(GRID_CLASS, CONTENT_FADE_IN)}>
      {cards.map((card) => (
        <StatCard key={card.label} {...card} previousLabel={previousLabel} />
      ))}
    </section>
  )
}
