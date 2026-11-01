import { Footprints } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useWorkoutsSummary } from '@/hooks/useWorkouts'
import { formatDistance } from '@/lib/distance'
import { cn } from '@/lib/utils'
import { CONTENT_FADE_IN } from '@/lib/transitions'

const RUNNING = 'HKWorkoutActivityTypeRunning'

/** Year-to-date and the same stretch of last year, as ISO dates. Anchored to the newest date
 * with data rather than today, like every relative range here (see computeDateRange): with
 * a stale export "so far this year" should mean as far as the data goes, not a run of empty
 * days after it. String arithmetic, since the dates are already `YYYY-MM-DD` and a Date
 * round trip is only a chance to shift one by a timezone. A Feb 29 anchor gives last year a
 * Feb 29 that doesn't exist, which is harmless as an upper bound compared as text.
 */
function yearToDate(latestDate: string) {
  const year = Number(latestDate.slice(0, 4))
  const monthDay = latestDate.slice(4)
  return {
    current: { start: `${year}-01-01`, end: latestDate },
    previous: { start: `${year - 1}-01-01`, end: `${year - 1}${monthDay}` },
  }
}

/** Running distance since January 1, against the same days last year. Outside the date
 * range picker on purpose: "this year" is the question, whatever range the page is on.
 */
export function RunningYtd({ latestDate }: { latestDate: string | undefined }) {
  const { current, previous } = yearToDate(latestDate ?? '0000-01-01')
  const now = useWorkoutsSummary(current, latestDate != null)
  const before = useWorkoutsSummary(previous, latestDate != null)

  if (latestDate == null) return null

  const year = latestDate.slice(0, 4)
  const loading = now.isLoading || before.isLoading
  const run = now.data?.find((row) => row.activity_type === RUNNING)
  const prior = before.data?.find((row) => row.activity_type === RUNNING)
  const unit = run?.distance_unit ?? null

  // Different units can't be subtracted -- same rule as the overview cards.
  const delta =
    run?.total_distance != null && prior?.total_distance != null && prior.distance_unit === unit
      ? run.total_distance - prior.total_distance
      : null

  return (
    <Card className="lg:col-span-2">
      <CardContent>
        <div className="text-muted-foreground flex items-center gap-1.5 text-xs font-medium tracking-wide uppercase">
          <Footprints className="size-3.5" aria-hidden />
          Running in {year}
        </div>
        {loading ? (
          <div className="mt-1 flex h-8 items-center">
            <Skeleton className="h-6 w-32" />
          </div>
        ) : now.error ? (
          <div className="text-destructive mt-1 text-sm">Failed to load running distance.</div>
        ) : (
          <div className={cn('mt-1 flex flex-wrap items-baseline gap-x-3', CONTENT_FADE_IN)}>
            <span className="text-2xl font-semibold tabular-nums">
              {run?.total_distance != null ? formatDistance(run.total_distance, unit) : '—'}
            </span>
            {run && (
              <span className="text-muted-foreground text-sm tabular-nums">
                {run.count.toLocaleString('en-US')} {run.count === 1 ? 'run' : 'runs'}
              </span>
            )}
            {delta != null && (
              <span className="text-muted-foreground text-xs tabular-nums">
                {delta === 0
                  ? 'same as'
                  : `${delta > 0 ? '▲ ' : '▼ '}${formatDistance(Math.abs(delta), unit)} vs`}{' '}
                {Number(year) - 1} to date
              </span>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
