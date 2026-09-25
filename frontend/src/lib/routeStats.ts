import type { WorkoutRoute } from '@/api/client'
import { formatDistance, formatPace } from '@/lib/distance'
import { formatDuration } from '@/lib/duration'

/** Distance, duration and pace in one line, for the route list's rows and the map's popup.
 *
 * Shared so the two can't describe the same route differently. Whatever the workout doesn't
 * have is left out rather than printed as a gap, and a route that matched no workout has
 * none of the three and gets no line at all -- the caller drops the line instead of showing
 * three em dashes, which would suggest three missing measurements rather than one missing
 * workout.
 */
export function routeStatsLine(route: WorkoutRoute): string | null {
  const parts = [
    // `> 0`, not just non-null, for the reason lib/distance.ts gives and formatPace already
    // applies: a workout that recorded a zero distance has nothing to report, and "0.0 mi"
    // states that it measured standing still.
    route.total_distance != null && route.total_distance > 0
      ? formatDistance(route.total_distance, route.total_distance_unit)
      : null,
    route.duration != null ? formatDuration(route.duration, route.duration_unit) : null,
    formatPace(
      route.total_distance,
      route.total_distance_unit,
      route.duration,
      route.duration_unit,
    ),
  ].filter(Boolean)
  return parts.length > 0 ? parts.join(' · ') : null
}
