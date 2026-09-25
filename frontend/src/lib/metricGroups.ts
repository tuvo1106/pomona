/** Every chartable metric, grouped for the "all charts" view. A chart is shown only if
 * its underlying type(s) actually have data in this export (checked against /api/metric-types
 * at render time) -- so the grid adapts to whatever a given Apple Health export contains.
 */

import { friendlyName } from '@/lib/metricNames'

export type ChartSpec =
  | { kind: 'quantity'; type: string; title?: string }
  | {
      kind: 'category'
      type: string
      mode: 'count' | 'duration'
      title: string
      valuePrefix?: string
    }
  | { kind: 'blood-pressure' }
  | { kind: 'sleep' }

export interface MetricGroup {
  id: string
  label: string
  /** The group's hue, as a `var(--group-*)` reference (see the palette block in index.css).
   * Every chart in the group draws in it, and the section heading shows it as a dot, so the
   * color says which part of Health you're looking at instead of line-vs-bar.
   */
  color: string
  charts: ChartSpec[]
}

const q = (type: string, title?: string): ChartSpec => ({ kind: 'quantity', type, title })

export const METRIC_GROUPS: MetricGroup[] = [
  {
    id: 'activity',
    label: 'Activity',
    color: 'var(--group-activity)',
    charts: [
      q('HKQuantityTypeIdentifierStepCount', 'Steps'),
      q('HKQuantityTypeIdentifierDistanceWalkingRunning', 'Distance'),
      q('HKQuantityTypeIdentifierDistanceCycling', 'Cycling distance'),
      q('HKQuantityTypeIdentifierActiveEnergyBurned', 'Active energy'),
      q('HKQuantityTypeIdentifierBasalEnergyBurned', 'Basal energy'),
      q('HKQuantityTypeIdentifierAppleExerciseTime', 'Exercise time'),
      q('HKQuantityTypeIdentifierAppleStandTime', 'Stand time'),
      {
        kind: 'category',
        type: 'HKCategoryTypeIdentifierAppleStandHour',
        mode: 'count',
        title: 'Stand hours',
        // Apple logs a record every checked hour whether or not the user actually stood
        // ('...Stood' vs '...Idle') -- without this filter every day would show ~24.
        valuePrefix: 'HKCategoryValueAppleStandHourStood',
      },
      q('HKQuantityTypeIdentifierFlightsClimbed', 'Flights climbed'),
      q('HKQuantityTypeIdentifierTimeInDaylight', 'Time in daylight'),
      q('HKQuantityTypeIdentifierPhysicalEffort', 'Physical effort'),
    ],
  },
  {
    id: 'heart',
    label: 'Heart',
    color: 'var(--group-heart)',
    charts: [
      q('HKQuantityTypeIdentifierHeartRate', 'Heart rate'),
      q('HKQuantityTypeIdentifierRestingHeartRate', 'Resting heart rate'),
      q('HKQuantityTypeIdentifierWalkingHeartRateAverage', 'Walking heart rate'),
      q('HKQuantityTypeIdentifierHeartRateVariabilitySDNN', 'Heart rate variability'),
      q('HKQuantityTypeIdentifierHeartRateRecoveryOneMinute', 'Heart rate recovery'),
      q('HKQuantityTypeIdentifierVO2Max', 'VO2 max'),
      { kind: 'blood-pressure' },
      q('HKQuantityTypeIdentifierOxygenSaturation', 'Blood oxygen (SpO2)'),
      q('HKQuantityTypeIdentifierRespiratoryRate', 'Respiratory rate'),
      {
        kind: 'category',
        type: 'HKCategoryTypeIdentifierHighHeartRateEvent',
        mode: 'count',
        title: 'High heart rate events',
      },
    ],
  },
  {
    id: 'mobility',
    label: 'Mobility & gait',
    color: 'var(--group-mobility)',
    charts: [
      q('HKQuantityTypeIdentifierWalkingSpeed', 'Walking speed'),
      q('HKQuantityTypeIdentifierWalkingStepLength', 'Step length'),
      q('HKQuantityTypeIdentifierWalkingDoubleSupportPercentage', 'Double support'),
      q('HKQuantityTypeIdentifierWalkingAsymmetryPercentage', 'Walking asymmetry'),
      q('HKQuantityTypeIdentifierAppleWalkingSteadiness', 'Walking steadiness'),
      q('HKQuantityTypeIdentifierStairAscentSpeed', 'Stair ascent speed'),
      q('HKQuantityTypeIdentifierStairDescentSpeed', 'Stair descent speed'),
      q('HKQuantityTypeIdentifierSixMinuteWalkTestDistance', '6-minute walk distance'),
    ],
  },
  {
    id: 'running',
    label: 'Running dynamics',
    color: 'var(--group-running)',
    charts: [
      q('HKQuantityTypeIdentifierRunningPower', 'Running power'),
      q('HKQuantityTypeIdentifierRunningSpeed', 'Running speed'),
      q('HKQuantityTypeIdentifierRunningStrideLength', 'Stride length'),
      q('HKQuantityTypeIdentifierRunningGroundContactTime', 'Ground contact time'),
      q('HKQuantityTypeIdentifierRunningVerticalOscillation', 'Vertical oscillation'),
    ],
  },
  {
    id: 'body',
    label: 'Body measurements',
    color: 'var(--group-body)',
    charts: [
      q('HKQuantityTypeIdentifierBodyMass', 'Weight'),
      q('HKQuantityTypeIdentifierHeight', 'Height'),
      q('HKQuantityTypeIdentifierAppleSleepingWristTemperature', 'Sleeping wrist temperature'),
    ],
  },
  {
    id: 'sleep',
    label: 'Sleep & mindfulness',
    color: 'var(--group-sleep)',
    charts: [
      { kind: 'sleep' },
      {
        kind: 'category',
        type: 'HKCategoryTypeIdentifierMindfulSession',
        mode: 'duration',
        title: 'Mindful minutes',
      },
      q('HKDataTypeSleepDurationGoal', 'Sleep goal'),
    ],
  },
  {
    id: 'environment',
    label: 'Environment & hearing',
    color: 'var(--group-environment)',
    charts: [
      q('HKQuantityTypeIdentifierHeadphoneAudioExposure', 'Headphone audio exposure'),
      q('HKQuantityTypeIdentifierEnvironmentalAudioExposure', 'Environmental audio exposure'),
    ],
  },
  {
    id: 'nutrition',
    label: 'Nutrition',
    color: 'var(--group-nutrition)',
    charts: [q('HKQuantityTypeIdentifierDietaryWater', 'Water intake')],
  },
]

/** Types referenced by every ChartSpec across all groups -- used to find any type present
 * in the export but not covered by a known group (falls back into an "Other" group).
 */
function specTypes(spec: ChartSpec): string[] {
  switch (spec.kind) {
    case 'quantity':
    case 'category':
      return [spec.type]
    case 'blood-pressure':
      return [
        'HKQuantityTypeIdentifierBloodPressureSystolic',
        'HKQuantityTypeIdentifierBloodPressureDiastolic',
      ]
    case 'sleep':
      return ['HKCategoryTypeIdentifierSleepAnalysis']
  }
}

export const KNOWN_TYPES = new Set(METRIC_GROUPS.flatMap((g) => g.charts.flatMap(specTypes)))

/** Apple's own naming convention reliably distinguishes the two: HKCategoryTypeIdentifier*
 * records never carry a numeric value_num (see api/dashboard.py's category_metric_timeseries),
 * while everything else (HKQuantityTypeIdentifier*, HKDataType*) does. An unrecognized quantity
 * type can safely reuse the generic line-chart spec; an unrecognized category type needs the
 * count-mode bar chart instead, or it would route through /api/metrics/{type}/timeseries (which
 * filters on value_num IS NOT NULL) and show "No data" forever despite having real records.
 */
function inferUnknownSpec(type: string): ChartSpec {
  if (type.startsWith('HKCategoryTypeIdentifier')) {
    return { kind: 'category', type, mode: 'count', title: friendlyName(type) }
  }
  return q(type)
}

export function groupsWithUnknownTypes(presentTypes: string[]): MetricGroup[] {
  const unknown = presentTypes.filter((t) => !KNOWN_TYPES.has(t))
  if (unknown.length === 0) return METRIC_GROUPS
  return [
    ...METRIC_GROUPS,
    {
      id: 'other',
      label: 'Other',
      color: 'var(--group-other)',
      charts: unknown.map(inferUnknownSpec),
    },
  ]
}

/** Charts shown per group before "Show all". Three fills exactly one row at the widest
 * breakpoint, and each group's list above is already authored best-first, so the preview is
 * the top of that list rather than a second ranking to keep in step.
 */
export const PREVIEW_COUNT = 3

/** The DOM id of a group's section on the dashboard -- shared with the nav that scrolls
 * to it, so the two can't drift apart.
 */
export function groupSectionId(groupId: string): string {
  return `metrics-${groupId}`
}

/** The heading a chart renders under.
 *
 * Mirrors what each chart component titles itself with, so an error fallback standing in
 * for a card that never rendered can still name it. Kept beside specKey rather than in
 * AllCharts: the two fixed-title charts hard-code theirs in their own components, and one
 * place to look beats guessing which.
 */
export function specTitle(spec: ChartSpec): string {
  switch (spec.kind) {
    case 'quantity':
      return spec.title ?? friendlyName(spec.type)
    case 'category':
      return spec.title
    case 'blood-pressure':
      return 'Blood pressure'
    case 'sleep':
      return 'Sleep'
  }
}

/** A stable key for a chart, for React lists and for remembering which charts are shown. */
export function specKey(spec: ChartSpec): string {
  switch (spec.kind) {
    case 'quantity':
    case 'category':
      return `${spec.kind}:${spec.type}`
    case 'blood-pressure':
      return 'blood-pressure'
    case 'sleep':
      return 'sleep'
  }
}

/** The groups to render for one range: only charts whose underlying type has data in it,
 * and only groups left with a chart. Both the section nav and the chart grid read this, so
 * a section can never appear in the nav without a matching heading to scroll to.
 */
export function presentGroups(presentTypes: string[]): MetricGroup[] {
  const present = new Set(presentTypes)
  return groupsWithUnknownTypes(presentTypes)
    .map((group) => ({
      ...group,
      // Blood pressure needs either half to be worth charting, sleep needs its one type;
      // specTypes already knows which types each spec is built from.
      charts: group.charts.filter((spec) => specTypes(spec).some((t) => present.has(t))),
    }))
    .filter((group) => group.charts.length > 0)
}
