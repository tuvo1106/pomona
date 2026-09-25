export interface DateRangeParams {
  start?: string
  end?: string
}

export interface MetricTypeInfo {
  type: string
  count: number
  unit: string | null
  min_date: string
  max_date: string
}

/** Why a bucket only covers part of its period (see `_mark_partial_buckets` in
 * api/dashboard.py): it holds the newest data date, assumed still in progress, or the date
 * range cuts it off. Only cumulative series are marked -- partial sums read as a false dip.
 */
export type PartialKind = 'in_progress' | 'truncated'

export interface TimeseriesPoint {
  date: string
  value: number | null
  partial?: PartialKind | null
}

export interface TimeseriesResponse {
  metric_type: string
  unit: string | null
  bucket: 'day' | 'week' | 'month'
  // Only present on /api/metrics/{type}/timeseries (quantity metrics). Category-metric
  // timeseries are always rendered as bars, which must stay zero-baselined regardless.
  aggregation_mode?: 'sum' | 'avg'
  points: TimeseriesPoint[]
}

export interface SleepPoint {
  date: string
  hours: number
}

export interface SleepResponse {
  bucket: 'day' | 'week' | 'month'
  points: SleepPoint[]
}

export interface BloodPressurePoint {
  date: string
  systolic: number | null
  diastolic: number | null
}

export interface BloodPressureResponse {
  bucket: 'day' | 'week' | 'month'
  points: BloodPressurePoint[]
}

export type CategoryMetricMode = 'count' | 'duration'

export interface Workout {
  id: number
  activity_type: string
  duration: number | null
  duration_unit: string | null
  total_distance: number | null
  total_distance_unit: string | null
  total_energy_burned: number | null
  total_energy_burned_unit: string | null
  start_local_date: string
  start_date: number
  end_date: number
}

export interface WorkoutTypeSummary {
  activity_type: string
  count: number
  total_distance: number | null
  distance_unit: string | null
  total_duration: number | null
  duration_unit: string | null
}

export interface ActivitySummary {
  date: string
  active_energy_burned: number | null
  active_energy_burned_goal: number | null
  active_energy_burned_unit: string | null
  apple_move_time: number | null
  apple_move_time_goal: number | null
  apple_exercise_time: number | null
  apple_exercise_time_goal: number | null
  apple_stand_hours: number | null
  apple_stand_hours_goal: number | null
}

export interface DiagnosticReportResult {
  display: string | null
  code_text: string | null
  value_num: number | null
  value_unit: string | null
  value_text: string | null
  status: string | null
}

export interface ClinicalRecord {
  id: number
  resource_type: string
  code_text: string | null
  code_system: string | null
  code_value: string | null
  status: string | null
  value_num: number | null
  value_unit: string | null
  value_text: string | null
  effective_date: number | null
  category: string | null
  // Resolved DiagnosticReport.result[] references (see clinical_loader.py); null for every
  // other resource type, and for a DiagnosticReport with no result[] entries.
  results: DiagnosticReportResult[] | null
  // An Observation's first FHIR referenceRange (see _reference_range in dashboard.py); null
  // for every other resource type and for an Observation without one. low/high are only set
  // when the bound is numeric -- a text-only range carries just `text`.
  reference_range: ReferenceRange | null
  // An Observation measured in parts (see _components in dashboard.py): blood pressure and
  // other panels put their values here and leave value_num/value_text null. Null for an
  // ordinary single-valued record. FHIR does not fix the order, so match on `code`.
  components: ObservationComponent[] | null
}

export interface ObservationComponent {
  label: string | null
  /** The part's LOINC code, when it has one -- e.g. systolic vs diastolic. */
  code: string | null
  value_num: number | null
  value_unit: string | null
  value_text: string | null
  reference_range: ReferenceRange | null
}

export interface ReferenceRange {
  low: number | null
  high: number | null
  unit: string | null
  text: string | null
}

export interface AvgWithUnit {
  value: number
  unit: string | null
}

export interface AvgBloodPressure {
  systolic: number | null
  diastolic: number | null
}

export interface WorkoutRoute {
  id: number
  workout_id: number | null
  activity_type: string | null
  start_local_date: string
  // The matched workout's own numbers, null together with activity_type when no workout
  // overlapped this track. Null is "unknown", not zero -- render the absence (lib/distance.ts).
  duration: number | null
  duration_unit: string | null
  total_distance: number | null
  total_distance_unit: string | null
  // Each element is one continuous <trkseg> -- kept separate (not flattened into one point
  // list) so a paused-and-resumed workout doesn't draw a false straight line across the gap.
  segments: [number, number][][]
}

export interface EcgRecording {
  id: number
  recorded_date: number
  recorded_local_date: string
  classification: string | null
  symptoms: string | null
  sample_rate: number
  lead: string | null
  device: string | null
  sample_count: number
}

export interface EcgPoint {
  t: number
  value: number
}

export interface EcgRecordingDetail extends EcgRecording {
  software_version: string | null
  unit: string | null
  points: EcgPoint[]
}

export interface OverviewStats {
  avg_daily_steps: number | null
  avg_weight: AvgWithUnit | null
  avg_resting_hr: number | null
  workout_count: number
  avg_vo2_max: AvgWithUnit | null
  avg_sleep_hours: number | null
  avg_blood_pressure: AvgBloodPressure | null
  avg_hrv: AvgWithUnit | null
}

export interface Overview extends OverviewStats {
  date_range: { start: string | null; end: string | null }
  /** The equal-length period just before `date_range`; null for an unbounded range. */
  previous_range: { start: string; end: string } | null
  /** The same stats over `previous_range`, for period-over-period deltas. */
  previous: OverviewStats | null
  /** Why `previous` is null despite a `previous_range`: that window starts before the oldest
   * data, or this is a single day that's likely still in progress. */
  previous_withheld: 'before_data' | 'partial_day' | null
}

export interface DataMeta {
  /** Newest record's local date (YYYY-MM-DD), or null on an empty database. */
  latest_date: string | null
  /** When `pomona ingest` last ran, as a unix epoch in seconds. */
  ingested_at: number | null
}

function buildQuery<T extends object>(params: T): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params) as [string, string | number | undefined][]) {
    if (value !== undefined && value !== '') search.set(key, String(value))
  }
  const qs = search.toString()
  return qs ? `?${qs}` : ''
}

/** A failed API response, carrying the status so callers can tell *why* it failed.
 *
 * A plain Error made every failure look alike, which meant the retry policy had to treat a
 * missing database the same as a dropped connection, and the app couldn't recognise the one
 * failure it can give real advice about.
 */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }

  /** The server has started but there's no database to read -- see api/dependencies.py,
   * which answers 503 with the `pomona ingest` command in its detail. Distinct from
   * an empty database, which answers 200 with no rows.
   */
  get isNoDatabase(): boolean {
    return this.status === 503
  }
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) {
    // Carry the API's own explanation through when there is one -- e.g. the 503 telling you
    // to run `pomona ingest` first, which is far more useful than the status text.
    const detail = await res
      .json()
      .then((body: { detail?: string }) => body?.detail)
      .catch(() => undefined)
    throw new ApiError(res.status, detail ?? `Request failed: ${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  meta: () => getJSON<DataMeta>('/api/meta'),

  metricTypes: (params: DateRangeParams = {}) =>
    getJSON<MetricTypeInfo[]>(`/api/metric-types${buildQuery(params)}`),

  metricTimeseries: (
    metricType: string,
    params: DateRangeParams & { bucket?: string } = {},
  ) =>
    getJSON<TimeseriesResponse>(
      `/api/metrics/${encodeURIComponent(metricType)}/timeseries${buildQuery(params)}`,
    ),

  categoryMetricTimeseries: (
    metricType: string,
    mode: CategoryMetricMode,
    params: DateRangeParams & { bucket?: string; value_prefix?: string } = {},
  ) =>
    getJSON<TimeseriesResponse>(
      `/api/category-metrics/${encodeURIComponent(metricType)}/timeseries${buildQuery({ ...params, mode })}`,
    ),

  sleep: (params: DateRangeParams & { bucket?: string } = {}) =>
    getJSON<SleepResponse>(`/api/sleep${buildQuery(params)}`),

  bloodPressure: (params: DateRangeParams & { bucket?: string } = {}) =>
    getJSON<BloodPressureResponse>(`/api/blood-pressure${buildQuery(params)}`),

  workouts: (
    params: DateRangeParams & { activity_type?: string; limit?: number; offset?: number } = {},
  ) => getJSON<Workout[]>(`/api/workouts${buildQuery(params)}`),

  workoutsSummary: (params: DateRangeParams = {}) =>
    getJSON<WorkoutTypeSummary[]>(`/api/workouts/summary${buildQuery(params)}`),

  activitySummary: (params: DateRangeParams = {}) =>
    getJSON<ActivitySummary[]>(`/api/activity-summary${buildQuery(params)}`),

  clinical: (params: DateRangeParams & { resource_type?: string } = {}) =>
    getJSON<ClinicalRecord[]>(`/api/clinical${buildQuery(params)}`),

  overview: (params: DateRangeParams = {}) =>
    getJSON<Overview>(`/api/overview${buildQuery(params)}`),

  routes: (params: DateRangeParams = {}) =>
    getJSON<WorkoutRoute[]>(`/api/routes${buildQuery(params)}`),

  ecgRecordings: (params: DateRangeParams = {}) =>
    getJSON<EcgRecording[]>(`/api/ecg${buildQuery(params)}`),

  ecgRecording: (id: number, params: { max_points?: number } = {}) =>
    getJSON<EcgRecordingDetail>(`/api/ecg/${id}${buildQuery(params)}`),
}
