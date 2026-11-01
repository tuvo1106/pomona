import { Footprints } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useWorkoutsSummary } from '@/hooks/useWorkouts'
import { formatDistance } from '@/lib/distance'
import { CONTENT_FADE_IN } from '@/lib/transitions'
import { cn } from '@/lib/utils'

const RUNNING = 'HKWorkoutActivityTypeRunning'

/** Year-to-date and the same stretch of last year, as ISO dates. Anchored to the newest date
 * with data rather than today, like every relative range here (see computeDateRange): with
 * a stale export "so far this year" should mean as far as the data goes, not a run of empty
 * days after it. String arithmetic, since the dates are already `YYYY-MM-DD` and a Date
 * round trip is only a chance to shift one by a timezone. A Feb 29 anchor gives last year a
 * Feb 29 that doesn't exist, which is harmless: the API compares dates as text, so it is
 * just an upper bound that includes everything through Feb 28.
 */
function yearToDate(latestDate: string) {
  const year = Number(latestDate.slice(0, 4))
  const monthDay = latestDate.slice(4)
  return {
    current: { start: `${year}-01-01`, end: latestDate },
    previous: { start: `${year - 1}-01-01`, end: `${year - 1}${monthDay}` },
  }
}

/** The comparison line, in one place. Rounded to the one decimal it is shown at *before*
 * comparing, so two totals that differ by 0.04 read "same as" rather than "▲ 0.0 mi".
 */
function comparisonText(delta: number, unit: string | null, previousYear: number): string {
  const rounded = Math.round(delta * 10) / 10
  if (rounded === 0) return `same as ${previousYear} to date`
  return `${rounded > 0 ? '▲' : '▼'} ${formatDistance(Math.abs(rounded), unit)} vs ${previousYear} to date`
}

/** Running distance since January 1, against the same days last year. Outside the date
 * range picker on purpose: "this year" is the question, whatever range the page is on.
 */
export function RunningYtd({ latestDate }: { latestDate: string | undefined }) {
  // Split so the date is never optional below: no placeholder date to build query keys from
  // while the anchor loads, and the queries need no `enabled` flag.
  if (latestDate == null) return null
  return <RunningYtdCard latestDate={latestDate} />
}

function RunningYtdCard({ latestDate }: { latestDate: string }) {
  const { current, previous } = yearToDate(latestDate)
  const now = useWorkoutsSummary(current)
  const before = useWorkoutsSummary(previous)

  const year = Number(latestDate.slice(0, 4))
  const run = now.data?.find((row) => row.activity_type === RUNNING)
  const prior = before.data?.find((row) => row.activity_type === RUNNING)

  const loading = now.isLoading || before.isLoading
  // Never ran in either year: nothing to show, and a permanent "—" card says nothing.
  if (!loading && !now.error && !before.error && !run && !prior) return null

  const unit = run?.distance_unit ?? prior?.distance_unit ?? null
  // A year with no running row ran zero miles, not an unknown number -- the comparison is
  // most interesting exactly when one side is a first or an absence.
  const distance = run?.total_distance ?? (now.data ? 0 : null)
  const priorDistance = prior?.total_distance ?? (before.data ? 0 : null)
  // Different units can't be subtracted -- same rule as the overview cards.
  const comparable = !run || !prior || run.distance_unit === prior.distance_unit
  const delta =
    distance != null && priorDistance != null && comparable ? distance - priorDistance : null

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
              {distance != null ? formatDistance(distance, unit) : '—'}
            </span>
            {run && (
              <span className="text-muted-foreground text-sm tabular-nums">
                {run.count.toLocaleString('en-US')} {run.count === 1 ? 'run' : 'runs'}
              </span>
            )}
            {before.error ? (
              <span className="text-destructive text-xs">Couldn't load {year - 1} to compare.</span>
            ) : (
              delta != null && (
                <span className="text-muted-foreground text-xs tabular-nums">
                  {comparisonText(delta, unit, year - 1)}
                </span>
              )
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
