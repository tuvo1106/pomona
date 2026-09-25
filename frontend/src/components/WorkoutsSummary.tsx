import { DataCard } from '@/components/DataCard'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useWorkoutsSummary } from '@/hooks/useWorkouts'
import { activityIcon, formatActivityType } from '@/lib/activityType'
import { formatDuration } from '@/lib/duration'
import type { DateRange } from '@/lib/timeRange'

export function WorkoutsSummary({ range }: { range: DateRange }) {
  const { data, isLoading, error } = useWorkoutsSummary(range)

  return (
    <DataCard
      title="Workout summary"
      isLoading={isLoading}
      error={error}
      isEmpty={!data || data.length === 0}
      errorMessage="Failed to load summary."
      emptyMessage="No workouts in this range."
      skeletonHeight={180}
    >
      {/* No row preview here: this is one row per activity type, a handful at most, so
          there is nothing to hide and no scroll area to trap the wheel. */}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Type</TableHead>
            <TableHead numeric>Count</TableHead>
            <TableHead numeric>Distance</TableHead>
            <TableHead numeric>Duration</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data?.map((row) => {
            const Icon = activityIcon(row.activity_type)
            return (
              <TableRow key={row.activity_type}>
                <TableCell>
                  <span className="flex items-center gap-2">
                    <Icon className="text-muted-foreground size-4 shrink-0" aria-hidden />
                    {formatActivityType(row.activity_type)}
                  </span>
                </TableCell>
                <TableCell numeric>{row.count.toLocaleString('en-US')}</TableCell>
                <TableCell numeric>
                  {row.total_distance != null
                    ? `${row.total_distance.toFixed(1)} ${row.distance_unit ?? ''}`.trim()
                    : '—'}
                </TableCell>
                <TableCell numeric>
                  {formatDuration(row.total_duration, row.duration_unit)}
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </DataCard>
  )
}
