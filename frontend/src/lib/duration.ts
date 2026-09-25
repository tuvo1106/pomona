/** Workout durations, written the way a person says them.
 *
 * HealthKit stores a duration as a number plus a unit, and that unit is minutes in every
 * export seen so far -- so the raw value reads as "72 min" where anyone scanning a workout
 * list wants "1h 12m". Long totals are the case that really needs it: a summary row adding
 * up a month of workouts gives "1,340 min", a number you have to do arithmetic on before it
 * means anything.
 *
 * Any unit that isn't minutes is left as it came. Splitting an unfamiliar unit into hours
 * and minutes would be a guess printed as a fact, and a wrong duration looks exactly like a
 * right one.
 */
export function formatDuration(
  value: number | null | undefined,
  unit: string | null | undefined,
): string {
  if (value == null) return '—'
  if (unit !== 'min') return unit ? `${Math.round(value)} ${unit}` : `${Math.round(value)}`

  const total = Math.round(value)
  const hours = Math.floor(total / 60)
  const minutes = total % 60
  if (hours === 0) return `${minutes}m`
  return minutes === 0 ? `${hours}h` : `${hours}h ${minutes}m`
}
