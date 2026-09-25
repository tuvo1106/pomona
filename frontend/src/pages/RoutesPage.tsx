import { useCallback, useMemo, useState } from 'react'
import type { WorkoutRoute } from '@/api/client'
import { ChartStateWrapper } from '@/components/ChartStateWrapper'
import { DataFreshness } from '@/components/DataFreshness'
import { RoutesList } from '@/components/RoutesList'
import { RoutesMap } from '@/components/RoutesMap'
import { TimeRangeSelect } from '@/components/TimeRangeSelect'
import { Button } from '@/components/ui/button'
import { useAnchoredRange } from '@/hooks/useAnchoredRange'
import { useBasemapEnabled } from '@/hooks/useBasemap'
import { useRoutes } from '@/hooks/useRoutes'
import { useSearchParamId } from '@/hooks/useSearchParamState'
import { cn } from '@/lib/utils'

/** Tall enough that a track has room to be a shape rather than a squiggle, capped so the
 * map doesn't outgrow a laptop screen. Viewport-relative below that cap: a fixed 600px on a
 * short window leaves the controls above it and the page's own scrollbar fighting for the
 * same space.
 */
const MAP_FRAME = 'h-[70vh] min-h-[380px] sm:h-[600px]'

/** Stable empty array: a fresh `[]` before the query resolves would be a new identity every
 * render, which is exactly what the memoization below is avoiding.
 */
const NO_ROUTES: WorkoutRoute[] = []

export function RoutesPage() {
  // Defaults to the last year, not the dashboard-wide 30 days -- routes only exist for
  // outdoor workouts, so a 30-day window is often empty.
  const {
    rangeOption,
    setRangeOption,
    customRange,
    setCustomRange,
    range,
    ready,
    latestDate,
    ingestedAt,
  } = useAnchoredRange('365d')
  const { data, isLoading, error } = useRoutes(range, { enabled: ready })
  const routes = data ?? NO_ROUTES
  // Derived once and used twice on purpose: ChartStateWrapper below stands in for the whole
  // map when any of these hold, and the basemap toggle controls something inside it. Sharing
  // the condition is what keeps a control from outliving the thing it controls.
  const isMapLoading = isLoading || !ready
  const showsMap = !isMapLoading && !error && routes.length > 0

  // Off until asked for: tiles are the only thing this app fetches from anywhere else, and
  // which tiles you need says where your routes are (see useBasemapEnabled).
  const [showBasemap, setShowBasemap] = useBasemapEnabled()
  // In the URL, unlike the hover below: which track you picked is worth reloading into.
  const [selectedRouteId, setSelectedRouteId] = useSearchParamId('route')
  // Which route the cursor (or keyboard focus) is on, in either direction: a list row
  // highlights its track, a track highlights its row. Held here because it's the one thing
  // both halves need to agree about. Stable identity so the map's memoized tracks don't all
  // re-render when it changes -- see RouteTrack.
  const [hoveredRouteId, setHoveredRouteId] = useState<number | null>(null)
  const handleHoverChange = useCallback((id: number | null) => setHoveredRouteId(id), [])
  // Derived, not stored separately: if the selected route fell out of the current range
  // (e.g. the date picker changed), treat the selection as cleared rather than pointing at
  // a route that's no longer in `routes`.
  const selectedId = routes.some((r) => r.id === selectedRouteId) ? selectedRouteId : null
  // Memoized on the selection, not rebuilt per render: this array is the map's `routes`
  // prop, and a new identity on every render would rebuild all ~80 memoized tracks each
  // time the hover moved -- the thing RouteTrack exists to prevent.
  const visibleRoutes = useMemo(
    () => (selectedId != null ? routes.filter((r) => r.id === selectedId) : routes),
    [routes, selectedId],
  )

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-8">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-foreground text-base font-semibold">Routes</h2>
          <p className="text-muted-foreground text-xs">
            GPS tracks from outdoor workouts. Indoor workouts have no route to show.
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-x-4 gap-y-2">
          <DataFreshness latestDate={latestDate} ingestedAt={ingestedAt} />
          {/* Only alongside a map. While loading, on error, and on a first run with no
              outdoor workouts in range, the frame below holds a message instead -- and a
              button that flips to "Hide map" with nothing on screen to hide is a dead
              control. Nothing jumps by appearing here: DataFreshness beside it renders null
              until the range resolves, so this row already settles once on load.

              aria-pressed rather than a checkbox: it toggles something already on screen,
              which is the same shape as the activity card's Rings/Table pair. */}
          {showsMap && (
            <Button
              type="button"
              variant={showBasemap ? 'secondary' : 'outline'}
              size="sm"
              aria-pressed={showBasemap}
              onClick={() => setShowBasemap(!showBasemap)}
              title={
                showBasemap
                  ? 'Map tiles are being fetched from OpenStreetMap'
                  : 'Draws streets behind your tracks. Fetches map tiles from OpenStreetMap.'
              }
            >
              {showBasemap ? 'Hide map' : 'Show map'}
            </Button>
          )}
          <TimeRangeSelect
            value={rangeOption}
            onChange={setRangeOption}
            custom={customRange}
            onCustomChange={setCustomRange}
          />
        </div>
      </div>

      <div className={cn('border-border overflow-hidden rounded-lg border', MAP_FRAME)}>
        <ChartStateWrapper
          isLoading={isMapLoading}
          error={error}
          isEmpty={routes.length === 0}
          height="100%"
          errorMessage="Failed to load routes."
        >
          <div className="flex h-full flex-col sm:flex-row">
            <RoutesList
              routes={routes}
              selectedId={selectedId}
              hoveredId={hoveredRouteId}
              onSelect={setSelectedRouteId}
              onHoverChange={handleHoverChange}
            />
            {/* min-h-0: a flex child defaults to min-height:auto, which lets the map's own
                100% height push the frame taller than the border it's inside. */}
            <div className="min-h-0 flex-1">
              <RoutesMap
                routes={visibleRoutes}
                showBasemap={showBasemap}
                selectedId={selectedId}
                hoveredId={hoveredRouteId}
                onHoverChange={handleHoverChange}
              />
            </div>
          </div>
        </ChartStateWrapper>
      </div>
    </main>
  )
}
