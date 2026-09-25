import { memo, useMemo } from 'react'
import type { WorkoutRoute } from '@/api/client'
import { formatActivityType } from '@/lib/activityType'
import { formatFullDate } from '@/lib/formatDate'
import { routeColorVar } from '@/lib/routeActivity'
import { routeStatsLine } from '@/lib/routeStats'
import { selectableRowClass } from '@/lib/selectableRow'
import { cn } from '@/lib/utils'

interface RoutesListProps {
  routes: WorkoutRoute[]
  selectedId: number | null
  hoveredId: number | null
  onSelect: (id: number | null) => void
  onHoverChange: (id: number | null) => void
}

interface RouteRowData {
  id: number
  colorVar: string
  activity: string
  date: string
  stats: string | null
}

/** One row. Memoized on primitives for the same reason the map's tracks are: hovering a
 * track highlights its row, and without this every one of ~80 rows would re-render to move
 * one highlight.
 */
const RouteRow = memo(function RouteRow({
  route,
  selected,
  hovered,
  onSelect,
  onHoverChange,
}: {
  route: RouteRowData
  selected: boolean
  hovered: boolean
  onSelect: (id: number | null) => void
  onHoverChange: (id: number | null) => void
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(route.id)}
      // Pointer and keyboard drive the same highlight, so tabbing through the list shows
      // where each route is, exactly as hovering does.
      onMouseEnter={() => onHoverChange(route.id)}
      onMouseLeave={() => onHoverChange(null)}
      onFocus={() => onHoverChange(route.id)}
      onBlur={() => onHoverChange(null)}
      className={cn(
        'border-border flex w-full flex-col gap-0.5 border-b px-3 py-2 text-left text-sm',
        selectableRowClass(selected),
        // The map's own hover arrives here: the row of whichever track is under the cursor
        // lights up, so a line on the map can be named without clicking it.
        hovered && !selected && 'bg-accent/50',
      )}
    >
      <span className="flex w-full items-center gap-2">
        <span
          className="h-2 w-2 shrink-0 rounded-full"
          style={{ backgroundColor: route.colorVar }}
        />
        <span className="flex-1 truncate">{route.activity}</span>
        <span className="text-muted-foreground shrink-0 text-xs">{route.date}</span>
      </span>
      {/* Absent entirely for a route that matched no workout, rather than a row of em
          dashes: there is one thing missing, not three. */}
      {route.stats && (
        <span className="text-muted-foreground pl-4 text-xs tabular-nums">{route.stats}</span>
      )}
    </button>
  )
})

/** A route with no segment of at least 2 points can't be drawn on the map (see RoutesMap)
 * -- excluded here too so every list entry is actually selectable.
 */
export function RoutesList({
  routes,
  selectedId,
  hoveredId,
  onSelect,
  onHoverChange,
}: RoutesListProps) {
  const rows = useMemo(
    () =>
      routes
        .filter((r) => r.segments.some((seg) => seg.length > 1))
        .map((route) => ({
          id: route.id,
          colorVar: routeColorVar(route.activity_type),
          activity: formatActivityType(route.activity_type),
          date: formatFullDate(route.start_local_date),
          stats: routeStatsLine(route),
        })),
    [routes],
  )

  return (
    // Scrolls, unlike the in-card tables that grew a "show all" control instead: this is a
    // full-height master pane beside its detail view, where a scrollbar is the expected
    // shape and expanding it would push the map itself off the page. Side by side on a wide
    // screen; above the map and capped in height on a narrow one, where a full-height list
    // would be all you ever saw.
    <div className="border-border flex max-h-48 w-full shrink-0 flex-col overflow-y-auto border-b sm:max-h-none sm:w-56 sm:border-r sm:border-b-0 md:w-64">
      <button
        type="button"
        onClick={() => onSelect(null)}
        className={cn(
          'border-border w-full border-b px-3 py-2 text-left text-sm font-medium',
          selectableRowClass(selectedId === null),
        )}
      >
        All routes
        <span className="text-muted-foreground ml-2 font-normal">{rows.length}</span>
      </button>
      {rows.map((route) => (
        <RouteRow
          key={route.id}
          route={route}
          selected={selectedId === route.id}
          hovered={hoveredId === route.id}
          onSelect={onSelect}
          onHoverChange={onHoverChange}
        />
      ))}
    </div>
  )
}
