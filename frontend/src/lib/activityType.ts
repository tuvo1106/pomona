import {
  Activity,
  Bike,
  Dumbbell,
  Flame,
  Footprints,
  Mountain,
  PersonStanding,
  TrendingUp,
  Waves,
  type LucideIcon,
} from 'lucide-react'

/** Strips HealthKit's `HKWorkoutActivityType` prefix for display, e.g. "Running", "Walking".
 * Shared by every place a workout/route's activity type is rendered, so a future formatting
 * change (spacing, i18n) only needs to happen once.
 */
export function formatActivityType(activityType: string | null | undefined): string {
  return activityType ? activityType.replace('HKWorkoutActivityType', '') : 'Unknown activity'
}

/** An icon per activity, so a list of workouts can be scanned by shape rather than read
 * word by word. Deliberately not exhaustive -- HealthKit defines ~80 activity types and
 * most people log a handful -- so anything unlisted takes the generic mark rather than a
 * loose approximation. An icon that means the wrong sport is worse than one that means
 * "a workout".
 *
 * A Map, not an object literal: the key comes straight out of `export.xml`, and an object
 * would happily resolve `constructor` to a function (see lib/units.ts, where exactly that
 * was a crash).
 */
const ACTIVITY_ICONS = new Map<string, LucideIcon>([
  ['HKWorkoutActivityTypeRunning', Footprints],
  ['HKWorkoutActivityTypeWalking', PersonStanding],
  ['HKWorkoutActivityTypeHiking', Mountain],
  ['HKWorkoutActivityTypeCycling', Bike],
  ['HKWorkoutActivityTypeSwimming', Waves],
  ['HKWorkoutActivityTypeStairClimbing', TrendingUp],
  ['HKWorkoutActivityTypeTraditionalStrengthTraining', Dumbbell],
  ['HKWorkoutActivityTypeFunctionalStrengthTraining', Dumbbell],
  ['HKWorkoutActivityTypeCoreTraining', Dumbbell],
  ['HKWorkoutActivityTypeHighIntensityIntervalTraining', Flame],
])

export function activityIcon(activityType: string | null | undefined): LucideIcon {
  return (activityType && ACTIVITY_ICONS.get(activityType)) || Activity
}
