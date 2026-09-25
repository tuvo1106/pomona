/** Workout distances, and the pace they imply, written the way a person says them.
 *
 * Everything here answers the same question the em dash answers elsewhere in the UI: what
 * to print when the number isn't there. A route whose workout didn't match gets null
 * distance and duration from the API (a LEFT join -- see api/dashboard.py), and null is
 * *unknown*, not zero: "0.0 mi" reads as a real measurement of standing still. So a missing
 * input gives a missing output, never a computed-from-nothing one.
 */

/** Distance with its unit as HealthKit reported it ("5.2 km"). Two decimals is more than
 * anyone reads, one is how a watch shows it.
 */
export function formatDistance(
  value: number | null | undefined,
  unit: string | null | undefined,
): string {
  if (value == null) return '—'
  const rounded = value.toLocaleString('en-US', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })
  return unit ? `${rounded} ${unit}` : rounded
}

/** Time per unit distance, as m:ss ("8:45 /mi") -- the form every running app uses, and the
 * one that makes two workouts comparable when neither distance matches.
 *
 * Returns null, not an em dash, when it can't be computed, so a caller can drop the field
 * rather than print a gap: an unmatched route has no pace to be missing. It can't be
 * computed unless the duration is in minutes (the only unit seen in an export -- guessing
 * at another would print a wrong pace, which looks exactly like a right one) and the
 * distance is greater than zero (a zero-distance workout has no pace; the division would
 * say "Infinity").
 *
 * Given for every activity, including cycling, where a rider would more likely ask for
 * km/h. It's the same number either way round, and one format across the list beats a
 * per-activity rule about which workouts deserve which.
 */
export function formatPace(
  distance: number | null | undefined,
  distanceUnit: string | null | undefined,
  duration: number | null | undefined,
  durationUnit: string | null | undefined,
): string | null {
  if (distance == null || distance <= 0 || duration == null || duration <= 0) return null
  if (durationUnit !== 'min' || !distanceUnit) return null

  const totalSeconds = Math.round((duration * 60) / distance)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${String(seconds).padStart(2, '0')} /${distanceUnit}`
}
