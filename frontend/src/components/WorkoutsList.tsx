import type { Workout } from '@/api/client'
import { DataCard } from '@/components/DataCard'
import { ShowAllRows } from '@/components/ShowAllRows'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useRowPreview } from '@/hooks/useRowPreview'
import { useWorkouts } from '@/hooks/useWorkouts'
import { activityIcon, formatActivityType } from '@/lib/activityType'
import { formatDuration } from '@/lib/duration'
import { formatFullDate } from '@/lib/formatDate'
import type { DateRange } from '@/lib/timeRange'

/** Stable empty array: a fresh `[]` each render would re-slice the preview every time. */
const NO_WORKOUTS: Workout[] = []

/** Enough rows to see the recent pattern without the card taking over the page. */
const PREVIEW_ROWS = 8

/** How many workouts the card asks for. `/api/workouts` pages, ordered newest first, so a
 * range with more than this has rows the card never receives -- which is why the expand
 * control says "most recent" rather than "all" (see ShowAllRows' `expandLabel`).
 */
const WORKOUT_LIMIT = 50

export function WorkoutsList({ range }: { range: DateRange }) {
  const { data, isLoading, error } = useWorkouts(range, { limit: WORKOUT_LIMIT })
  const workouts = data ?? NO_WORKOUTS
  const { visibleRows, hiddenCount, totalCount, isExpanded, toggle } = useRowPreview(
    workouts,
    PREVIEW_ROWS,
  )

  return (
    <DataCard
      title="Recent workouts"
      isLoading={isLoading}
      error={error}
      isEmpty={workouts.length === 0}
      errorMessage="Failed to load workouts."
      emptyMessage="No workouts in this range."
    >
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Date</TableHead>
            <TableHead>Type</TableHead>
            <TableHead numeric>Duration</TableHead>
            <TableHead numeric>Energy</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {visibleRows.map((w) => {
            const Icon = activityIcon(w.activity_type)
            return (
              <TableRow key={w.id}>
                <TableCell className="whitespace-nowrap">
                  {formatFullDate(w.start_local_date)}
                </TableCell>
                <TableCell>
                  <span className="flex items-center gap-2">
                    {/* Decorative: the activity is named right beside it, so a screen
                        reader would only hear the same thing twice. */}
                    <Icon className="text-muted-foreground size-4 shrink-0" aria-hidden />
                    {formatActivityType(w.activity_type)}
                  </span>
                </TableCell>
                <TableCell numeric>{formatDuration(w.duration, w.duration_unit)}</TableCell>
                <TableCell numeric>
                  {w.total_energy_burned != null
                    ? `${Math.round(w.total_energy_burned).toLocaleString('en-US')} ${w.total_energy_burned_unit ?? ''}`.trim()
                    : '—'}
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
      <ShowAllRows
        hiddenCount={hiddenCount}
        totalCount={totalCount}
        isExpanded={isExpanded}
        onToggle={toggle}
        noun="workouts"
        // Not "all": the query is capped at WORKOUT_LIMIT, so a range with more workouts
        // than that has rows this card never received. "Most recent" is true either way --
        // the endpoint orders by date descending -- and the card is titled to match.
        expandLabel={`Show ${totalCount.toLocaleString('en-US')} most recent`}
      />
    </DataCard>
  )
}
