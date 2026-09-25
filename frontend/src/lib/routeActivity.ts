/** Which colour a route track is drawn in, as a *name* rather than a value.
 *
 * The colours themselves live in index.css as --route-* tokens, and nothing here resolves
 * them. Two reasons they stay in CSS: the light and dark values are one pair of tokens with
 * one comment explaining how they were chosen, and CSS follows a theme change on its own,
 * where a value read out of getComputedStyle has to be re-read at exactly the right moment
 * (the theme class lands in a parent effect, which React runs *after* a child's -- so a
 * child reading tokens on a theme change reads the outgoing theme's).
 *
 * So a route gets a class name and RoutesMap.css maps it to a token. Leaflet writes its
 * colours with setAttribute, i.e. as SVG presentation attributes, which any author rule
 * outranks -- and unlike a presentation attribute, a CSS declaration can hold a var().
 */

/** Keyed by the raw HealthKit activity type; anything not listed is "other". A Map, not an
 * object literal, because these keys come out of the export -- see the note in lib/units.ts
 * about a record whose key is "constructor".
 */
const ACTIVITY_SLUGS = new Map([
  ['HKWorkoutActivityTypeRunning', 'running'],
  ['HKWorkoutActivityTypeWalking', 'walking'],
  ['HKWorkoutActivityTypeCycling', 'cycling'],
])

const OTHER_SLUG = 'other'

function slugForActivity(activityType: string | null): string {
  return (activityType && ACTIVITY_SLUGS.get(activityType)) ?? OTHER_SLUG
}

/** Leaflet `className` for a route's map layers. Pairs with the `.route-running` etc. rules
 * in RoutesMap.css, which only set --route-color; what each layer does with that colour
 * (stroke for a track, fill for a start dot) is the layer's own class.
 */
export function routeColorClass(activityType: string | null): string {
  return `route-${slugForActivity(activityType)}`
}

/** The same colour for ordinary DOM, e.g. the list's legend dot:
 * `style={{ backgroundColor: routeColorVar(type) }}`.
 */
export function routeColorVar(activityType: string | null): string {
  return `var(--route-${slugForActivity(activityType)})`
}
