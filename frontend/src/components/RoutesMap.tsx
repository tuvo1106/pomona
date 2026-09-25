import 'leaflet/dist/leaflet.css'
import './RoutesMap.css'
import { memo, useEffect, useMemo } from 'react'
import {
  CircleMarker,
  MapContainer,
  Pane,
  Polyline,
  Popup,
  TileLayer,
  useMap,
} from 'react-leaflet'
import type { WorkoutRoute } from '@/api/client'
import { useResolvedTheme } from '@/hooks/useTheme'
import { formatActivityType } from '@/lib/activityType'
import { formatFullDate } from '@/lib/formatDate'
import { routeColorClass } from '@/lib/routeActivity'
import { routeStatsLine } from '@/lib/routeStats'

// OSM's own tiles in both themes: free, no API key, no account (ADR-0004). Dark mode is a
// CSS filter over these same tiles (see RoutesMap.css), not a second tile source -- CARTO's
// dark_all basemap was used until it started stamping "API KEY REQUIRED" across every tile
// for keyless requests. Filtering the one source we already depend on avoids taking on a
// second third-party dependency whose keyless access could change the same way.
//
// Overridable at build time for anyone who would rather point at their own provider -- a
// paid one with a key in the URL, or a tile server on their own network. See
// frontend/.env.example.
const CUSTOM_TILE_URL = import.meta.env.VITE_TILE_URL
const OSM_TILE_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

// Note which fallback is conditional. An explicit VITE_TILE_ATTRIBUTION always wins, but the
// OSM credit is only the default while the tiles are actually OSM's -- attribution isn't
// transferable, so inheriting it onto someone else's tiles would print a false licence
// statement about both sources. A build that overrides the URL and forgets the attribution
// therefore ships none, which is a missing credit rather than a wrong one.
const TILE_LAYER = {
  url: CUSTOM_TILE_URL || OSM_TILE_URL,
  attribution:
    import.meta.env.VITE_TILE_ATTRIBUTION || (CUSTOM_TILE_URL ? undefined : OSM_ATTRIBUTION),
}

const TRACK_WEIGHT = 3
const EMPHASIZED_TRACK_WEIGHT = 4
/** Added to the track's weight, so the casing shows as an outline of even thickness. */
const CASING_EXTRA_WEIGHT = 3

/** The all-routes view stacks every track in the range -- around eighty of them for a year,
 * most following the same few streets. At full strength they read as one solid mat; held
 * back, the shape of where you go comes through and a hovered or selected route stands out
 * from it.
 */
const CROWD_OPACITY = 0.5

/** A loop run starts and ends in the same place, so the two dots land on top of each
 * other. The end is the larger ring and is drawn first, leaving the start dot sitting
 * inside it -- at the same coordinates that still reads as two things, where two dots of
 * one size would just be the second one.
 */
const START_RADIUS = 4
const END_RADIUS = 7
const ENDPOINT_WEIGHT = 2
/** Leaflet's CircleMarker fill defaults to 0.2, and the CSS below sets which colour the fill
 * is, not how opaque -- without this the start dot is a 20% smudge and the end ring shows the
 * basemap through its middle.
 */
const ENDPOINT_FILL_OPACITY = 1

/* A note on `className` being a prop of its own rather than part of `pathOptions`, since it
   looks like an oversight: react-leaflet passes top-level props to the Leaflet constructor,
   but applies `pathOptions` afterwards through setStyle -- and setStyle restyles an existing
   element, so it has no way to change a class and ignores one. A className inside
   pathOptions silently never arrives; the layer keeps Leaflet's default blue. Colours here
   come from the class, so they belong to construction; weight and opacity change as you
   hover, so they belong in pathOptions. */

/** The name of the Leaflet pane every casing is drawn into, below the tracks' own
 * (overlayPane is 400). Casings have to be under *all* tracks, not just their own: a casing
 * drawn beside its track would paint over the track of every route before it, and eighty
 * routes would cross-hatch each other's outlines.
 *
 * A pane rather than simply emitting all the casings before all the tracks, which is what
 * this did first and is not enough. Within one pane Leaflet paints in insertion order and
 * appends each new layer at the end, while react-leaflet adds a layer once, on mount -- so a
 * layer that survives a re-render keeps its position and everything mounted after it lands
 * behind. Select a route and back: the one route that stayed mounted is now first, and the
 * other eighty casings, appended after its track, paint over it. Two panes can't be got out
 * of order that way.
 */
const CASING_PANE = 'route-casings'
const CASING_PANE_Z_INDEX = 399

/** The dark line under one route, drawn wider than the track so what shows of it is an
 * outline.
 */
const RouteCasing = memo(function RouteCasing({
  segments,
  weight,
  opacity,
}: {
  segments: [number, number][][]
  weight: number
  opacity: number
}) {
  return (
    // Not interactive: it is wider than the track and sits under it, so it would swallow
    // the mouseover that should reach the track.
    <Polyline
      positions={segments}
      interactive={false}
      className="route-casing"
      pathOptions={{ weight: weight + CASING_EXTRA_WEIGHT, opacity }}
    />
  )
})

/** One route's coloured line, its popup, and -- when it's the selected route -- a dot at
 * each end.
 *
 * Memoized, and every prop is a primitive or an array that changes only when the route data
 * does. Moving the hover therefore costs a shallow compare per route (~80 of them) plus a
 * real re-render of the two that changed, rather than rebuilding eighty Leaflet layers on
 * every mouseover -- which would feel worse than having no highlight at all.
 */
const RouteTrack = memo(function RouteTrack({
  routeId,
  segments,
  colorClass,
  weight,
  opacity,
  showEndpoints,
  title,
  date,
  stats,
  onHoverChange,
}: {
  routeId: number
  segments: [number, number][][]
  colorClass: string
  weight: number
  opacity: number
  showEndpoints: boolean
  title: string
  date: string
  stats: string | null
  onHoverChange: (id: number | null) => void
}) {
  const eventHandlers = useMemo(
    () => ({
      mouseover: () => onHoverChange(routeId),
      mouseout: () => onHoverChange(null),
    }),
    [routeId, onHoverChange],
  )

  const lastSegment = segments[segments.length - 1]
  const start = segments[0][0]
  const end = lastSegment[lastSegment.length - 1]

  return (
    <>
      <Polyline
        positions={segments}
        eventHandlers={eventHandlers}
        className={`route-track ${colorClass}`}
        pathOptions={{ weight, opacity }}
      >
        <Popup>
          <span className="font-medium">{title}</span>
          <br />
          {date}
          {stats && (
            <>
              <br />
              {stats}
            </>
          )}
        </Popup>
      </Polyline>
      {showEndpoints && (
        <>
          <CircleMarker
            center={end}
            radius={END_RADIUS}
            interactive={false}
            className={`route-end ${colorClass}`}
            pathOptions={{ weight: ENDPOINT_WEIGHT, fillOpacity: ENDPOINT_FILL_OPACITY }}
          />
          <CircleMarker
            center={start}
            radius={START_RADIUS}
            interactive={false}
            className={`route-start ${colorClass}`}
            pathOptions={{ weight: ENDPOINT_WEIGHT, fillOpacity: ENDPOINT_FILL_OPACITY }}
          />
        </>
      )}
    </>
  )
})

/** Re-fits the map's viewport whenever the set of rendered routes changes -- MapContainer
 * only reads its `center`/`zoom` props once at mount, so a later data change (e.g. the date
 * range picker) needs an imperative fitBounds call via the map instance instead.
 */
function FitBounds({ routes }: { routes: DrawableRoute[] }) {
  const map = useMap()
  useEffect(() => {
    const allPoints = routes.flatMap((r) => r.segments.flat())
    if (allPoints.length === 0) return
    map.fitBounds(allPoints, { padding: [24, 24] })
  }, [routes, map])
  return null
}

interface DrawableRoute {
  id: number
  segments: [number, number][][]
  colorClass: string
  title: string
  date: string
  stats: string | null
}

/** Each segment is a separate <trkseg> (see gpx_loader.py) -- kept as a nested array so
 * Leaflet draws them as disconnected lines rather than joining the end of one to the start
 * of the next across a paused-workout gap. A segment needs at least 2 points to draw at all,
 * and a route with no such segment isn't drawn (RoutesList hides those rows to match).
 *
 * Built once per data change rather than per render: these arrays are what lets the
 * memoized tracks skip re-rendering when only the hover moves.
 */
function useDrawableRoutes(routes: WorkoutRoute[]): DrawableRoute[] {
  return useMemo(
    () =>
      routes
        .map((route) => ({
          id: route.id,
          segments: route.segments.filter((seg) => seg.length > 1),
          colorClass: routeColorClass(route.activity_type),
          title: formatActivityType(route.activity_type),
          date: formatFullDate(route.start_local_date),
          stats: routeStatsLine(route),
        }))
        .filter((route) => route.segments.length > 0),
    [routes],
  )
}

interface RoutesMapProps {
  routes: WorkoutRoute[]
  /** Whether to request tiles at all (see useBasemapEnabled). False draws the tracks on a
   * plain surface and makes no outbound request -- the TileLayer isn't mounted, rather than
   * mounted and hidden. */
  showBasemap: boolean
  /** Null in the all-routes view. When set, `routes` holds only that route. */
  selectedId: number | null
  hoveredId: number | null
  onHoverChange: (id: number | null) => void
}

export function RoutesMap({
  routes,
  showBasemap,
  selectedId,
  hoveredId,
  onHoverChange,
}: RoutesMapProps) {
  const drawable = useDrawableRoutes(routes)
  const firstPoint = drawable[0]?.segments[0]?.[0] ?? [0, 0]
  const resolvedTheme = useResolvedTheme()

  const weightFor = (id: number) =>
    id === selectedId || id === hoveredId ? EMPHASIZED_TRACK_WEIGHT : TRACK_WEIGHT
  // A selected route is the only one on the map, so nothing is competing with it to be held
  // back from; in the all-routes view everything but the hovered track is.
  const opacityFor = (id: number) => (selectedId == null && id !== hoveredId ? CROWD_OPACITY : 1)

  return (
    // The dark class goes on a wrapper, not MapContainer's own className: react-leaflet
    // captures that prop once at mount, so toggling the theme would never reach it. Driven
    // by the *resolved* theme so "system" on a dark OS gets the dark basemap too.
    <div className={resolvedTheme === 'dark' ? 'routes-map-dark h-full' : 'h-full'}>
      <MapContainer
        center={firstPoint}
        zoom={13}
        // Set here rather than inherited. Leaflet derives a map's zoom limits from its
        // zoom-bound layers, and getMaxZoom() falls back to Infinity when it has none --
        // which is now the default state, since the basemap is opt-in. Unbounded, fitBounds
        // frames a near-stationary route at zoom 21+ (its clamp is Math.min(getMaxZoom(),
        // ...)), the scroll wheel never stops, and switching the basemap on makes Leaflet
        // yank the view back to the tile layer's 18. 18 and 0 are the values that layer
        // supplied before this, so the limits are unchanged -- they just no longer depend on
        // whether the basemap happens to be showing.
        minZoom={0}
        maxZoom={18}
        scrollWheelZoom
        // Leaflet's tile fade-in relies on a requestAnimationFrame loop that can end up
        // stuck at opacity: 0 on initial mount in React (a well-known react-leaflet/Leaflet
        // interaction, not specific to this app) -- tiles otherwise render but stay invisible
        // until the next pan/zoom. Disabling the fade sidesteps it entirely.
        fadeAnimation={false}
        style={{ height: '100%', width: '100%' }}
      >
        {showBasemap && <TileLayer url={TILE_LAYER.url} attribution={TILE_LAYER.attribution} />}
        <Pane name={CASING_PANE} style={{ zIndex: CASING_PANE_Z_INDEX }}>
          {drawable.map((route) => (
            <RouteCasing
              key={route.id}
              segments={route.segments}
              weight={weightFor(route.id)}
              opacity={opacityFor(route.id)}
            />
          ))}
        </Pane>
        {drawable.map((route) => (
          <RouteTrack
            key={route.id}
            routeId={route.id}
            segments={route.segments}
            colorClass={route.colorClass}
            title={route.title}
            date={route.date}
            stats={route.stats}
            weight={weightFor(route.id)}
            opacity={opacityFor(route.id)}
            showEndpoints={route.id === selectedId}
            onHoverChange={onHoverChange}
          />
        ))}
        <FitBounds routes={drawable} />
      </MapContainer>
    </div>
  )
}
