import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { ActivityHeatmap } from '@/components/ActivityHeatmap'
import { ActivityRingsGlyph, ActivityRingsLegend } from '@/components/ActivityRingsGlyph'
import { ShowAllRows } from '@/components/ShowAllRows'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useContentFade } from '@/lib/transitions'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useRowPreview } from '@/hooks/useRowPreview'
import {
  closedDayCounts,
  formatCompletion,
  formatDayLabel,
  isClosed,
  latestDayWithData,
  ringsForDay,
} from '@/lib/activityRings'
import { formatFullDate } from '@/lib/formatDate'
import type { DateRange } from '@/lib/timeRange'

/** A year range is 365 rows and "All time" is thousands, so the table shows a fortnight
 * and offers the rest -- it used to scroll inside the card, which swallowed the page's own
 * scrolling whenever the cursor crossed it.
 */
const PREVIEW_ROWS = 14

export function ActivityRings({ range }: { range: DateRange }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['activity-summary', range],
    queryFn: () => api.activitySummary(range),
  })
  const [view, setView] = useState<'rings' | 'table'>('rings')

  const rows = useMemo(() => data ?? [], [data])
  const latest = useMemo(() => latestDayWithData(rows), [rows])
  const counts = useMemo(() => closedDayCounts(rows), [rows])
  const rings = useMemo(() => ringsForDay(latest), [latest])
  // The API returns oldest-first, which buries the interesting end of a long range under
  // months of scrolling; the table reads newest-first.
  const tableRows = useMemo(() => [...rows].reverse(), [rows])
  const table = useRowPreview(tableRows, PREVIEW_ROWS)

  const isEmpty = rows.length === 0
  const showContent = !isLoading && !error && !isEmpty
  const fade = useContentFade(isLoading)

  return (
    <Card>
      {/* CardAction, not flex classes on CardHeader: this CardHeader is a grid, and it grows
          the second column only when a card-action slot is present (see ui/card.tsx). */}
      <CardHeader>
        <CardTitle className="text-sm font-medium">Daily activity</CardTitle>
        {!isLoading && !error && !isEmpty && (
          <CardAction className="flex gap-1">
            <Button
              type="button"
              variant={view === 'rings' ? 'secondary' : 'ghost'}
              size="sm"
              onClick={() => setView('rings')}
            >
              Rings
            </Button>
            <Button
              type="button"
              variant={view === 'table' ? 'secondary' : 'ghost'}
              size="sm"
              onClick={() => setView('table')}
            >
              Table
            </Button>
          </CardAction>
        )}
      </CardHeader>
      <CardContent>
        {isLoading && <Skeleton className="h-[260px] w-full" />}
        {!isLoading && error && (
          <div className="text-destructive text-sm">Failed to load activity summary.</div>
        )}
        {!isLoading && !error && isEmpty && (
          <div className="text-muted-foreground text-sm">No activity data in this range.</div>
        )}
        {showContent && (
          // One wrapper for both views, so the fade marks content arriving and not the
          // Rings/Table toggle: switching view re-renders inside this div rather than
          // remounting it, and a click gets no loading affordance it hasn't earned.
          <div className={fade}>
            {view === 'rings' ? (
            /* Summary and calendar sit side by side while both fit, and the calendar drops
               to its own row when it doesn't -- it reports its natural width as a flex
               basis (see ActivityHeatmap), so the wrap point follows the range rather than a
               guessed breakpoint. A month of days is a handful of columns that left barely a
               fifth of the card covered and the rest empty; a year's worth is wider than the
               summary leaves, and gets the full width by wrapping. */
            <div className="flex flex-wrap items-start gap-x-10 gap-y-6">
              {/* basis, not a min-width floor. Both of these grow, so the line-breaking above
                  uses this number while `min-w-0` still lets the column shrink under it --
                  a hard floor here instead squeezed the legend to a third of its content on
                  any range whose calendar is wide enough to share the line (a 90-day one at
                  full width), and overflowed a phone-width card outright. Capped at max-w-md
                  for the original reason: an uncapped legend stretches to the full card and
                  parks each percentage an inch from the value it belongs to. */}
              <div className="min-w-0 flex-1 basis-[22rem] space-y-4 sm:max-w-md">
                {/* Wraps: where the column does get narrow, the legend drops below the glyph
                    rather than compressing "115 / 450 Cal" into three lines. */}
                <div className="flex flex-wrap items-center gap-x-6 gap-y-4">
                  <ActivityRingsGlyph rings={rings} />
                  <div className="min-w-[12rem] flex-1 space-y-2">
                    <div className="text-muted-foreground text-xs">
                      {latest ? formatDayLabel(latest.date) : 'No day with data in this range'}
                    </div>
                    <ActivityRingsLegend rings={rings} />
                  </div>
                </div>
                <div className="text-muted-foreground text-sm">
                  <span className="text-foreground font-medium tabular-nums">
                    {counts.closed.toLocaleString('en-US')} of {counts.total.toLocaleString('en-US')}
                  </span>{' '}
                  {counts.total === 1 ? 'day' : 'days'} with all rings closed
                </div>
              </div>
              <ActivityHeatmap rows={rows} range={range} />
            </div>
            ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead numeric>Move</TableHead>
                    <TableHead numeric>Exercise</TableHead>
                    <TableHead numeric>Stand</TableHead>
                    <TableHead numeric>Rings closed</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {table.visibleRows.map((row) => {
                    const dayRings = ringsForDay(row)
                    return (
                      <TableRow key={row.date}>
                        <TableCell className="whitespace-nowrap">{formatFullDate(row.date)}</TableCell>
                        {dayRings.map((ring) => (
                          <TableCell key={ring.key} numeric>
                            {ring.value != null ? Math.round(ring.value).toLocaleString('en-US') : '—'}
                            {ring.goal != null &&
                              ` / ${Math.round(ring.goal).toLocaleString('en-US')}`}{' '}
                            {ring.unit}
                            <span className="text-muted-foreground">
                              {' '}
                              ({formatCompletion(ring.completion)})
                            </span>
                          </TableCell>
                        ))}
                        <TableCell numeric>{dayRings.filter(isClosed).length} of 3</TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
              <ShowAllRows
                hiddenCount={table.hiddenCount}
                totalCount={table.totalCount}
                isExpanded={table.isExpanded}
                onToggle={table.toggle}
                noun="days"
              />
            </>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
