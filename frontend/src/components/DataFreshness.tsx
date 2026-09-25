import { formatFullDate } from '@/lib/formatDate'
import { parseLocalDate, todayLocalDateString } from '@/lib/timeRange'

// Past this, the data has fallen far enough behind that a re-export is worth suggesting.
const STALE_AFTER_DAYS = 7

function daysBetween(from: string, to: string): number {
  return Math.round((parseLocalDate(to).getTime() - parseLocalDate(from).getTime()) / 86_400_000)
}

/** "Data through Aug 20, 2026" beside a page's range picker. The relative ranges end on this
 * date rather than today (see computeDateRange), so it's shown rather than left implicit --
 * otherwise "Last 30 days" silently means something other than the last 30 days.
 */
export function DataFreshness({
  latestDate,
  ingestedAt,
}: {
  latestDate?: string
  ingestedAt?: number
}) {
  if (!latestDate) return null
  const daysOld = daysBetween(latestDate, todayLocalDateString())
  const importedTitle =
    ingestedAt != null
      ? `Last imported ${new Date(ingestedAt * 1000).toLocaleDateString('en-US', {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
        })}`
      : undefined

  return (
    <p className="text-muted-foreground text-right text-xs" title={importedTitle}>
      <span className="text-foreground font-medium">Data through {formatFullDate(latestDate)}</span>
      {daysOld > STALE_AFTER_DAYS && (
        <span className="block">
          Re-export from the Health app and run <code>pomona ingest</code> to update.
        </span>
      )}
    </p>
  )
}
