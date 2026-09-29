import json
import threading
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from pomona import fhir
from pomona.api.dependencies import DbDep
from pomona.clinical import INGESTED_RESOURCE_TYPES
from pomona.db import earliest_data_date, latest_data_date
from pomona.dedup import (
    IntervalRecord,
    bucket_local_date,
    dedup_nonoverlapping,
    nightly_totals,
    sum_by_bucket,
)
from pomona.metrics import aggregation_mode
from pomona.waveform import downsample_minmax

router = APIRouter(prefix="/api", tags=["dashboard"])

# Validated by FastAPI from the annotation, so an unknown value is a 422 before the handler runs.
Bucket = Literal["day", "week", "month"]


def _bucket_expr(column: str, bucket: Bucket) -> str:
    """SQL bucket expression for the (non-dedup) endpoints that aggregate directly in SQL."""
    if bucket == "week":
        return f"date({column}, '-' || ((strftime('%w', {column}) + 6) % 7) || ' days')"
    if bucket == "month":
        return f"strftime('%Y-%m-01', {column})"
    return column  # day


STEP_COUNT = "HKQuantityTypeIdentifierStepCount"
BODY_MASS = "HKQuantityTypeIdentifierBodyMass"
RESTING_HR = "HKQuantityTypeIdentifierRestingHeartRate"
VO2_MAX = "HKQuantityTypeIdentifierVO2Max"
SLEEP_ANALYSIS = "HKCategoryTypeIdentifierSleepAnalysis"
BP_SYSTOLIC = "HKQuantityTypeIdentifierBloodPressureSystolic"
BP_DIASTOLIC = "HKQuantityTypeIdentifierBloodPressureDiastolic"
HRV_SDNN = "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"


def _where(
    column: str,
    start: str | None,
    end: str | None,
    conditions: list[str] | None = None,
    params: list | None = None,
) -> tuple[str, list]:
    """A `WHERE` clause ANDing `conditions` with an inclusive date range on `column`, and its
    parameters (`params` first, for the placeholders in `conditions`). An empty string when
    there's nothing to filter on, so it can be dropped straight into a query.

    Lists, not any sequence: a bare string would be split into one condition (or one bound
    parameter) per character.
    """
    where = list(conditions or [])
    all_params = list(params or [])
    if start:
        where.append(f"{column} >= ?")
        all_params.append(start)
    if end:
        where.append(f"{column} <= ?")
        all_params.append(end)
    return (f"WHERE {' AND '.join(where)}" if where else ""), all_params


ASLEEP = "value_text LIKE 'HKCategoryValueSleepAnalysisAsleep%'"

# Systolic and diastolic are separate record types; averaged side by side over one scan.
BP_AVERAGES = f"""
    AVG(CASE WHEN type = '{BP_SYSTOLIC}' THEN value_num END) AS systolic,
    AVG(CASE WHEN type = '{BP_DIASTOLIC}' THEN value_num END) AS diastolic
"""


def _deduped_totals(
    conn, metric_type: str, start: str | None, end: str | None, bucket: Bucket
) -> dict[str, float]:
    """A cumulative metric's total per bucket, deduplicated across sources first.

    Cumulative metrics (steps, energy, distance, ...) are independently logged by every
    source that tracks them, so a naive SUM double-counts overlapping devices -- dedupe by
    time window first. See dedup.py.
    """
    where_sql, params = _where(
        "start_local_date", start, end, ["type = ?", "value_num IS NOT NULL"], [metric_type]
    )
    rows = conn.execute(
        f"SELECT start_date, end_date, value_num, start_local_date "
        f"FROM records {where_sql} ORDER BY start_date",
        params,
    ).fetchall()
    intervals = [
        IntervalRecord(
            row["start_date"], row["end_date"], row["value_num"], row["start_local_date"]
        )
        for row in rows
    ]
    return sum_by_bucket(dedup_nonoverlapping(intervals), bucket)


def _nightly_sleep_seconds(conn, start: str | None, end: str | None) -> dict[str, float]:
    """Seconds asleep per night, keyed by the evening the night began (see nightly_totals).

    Deduplicated the same way cumulative metrics are (see dedup.py): iPhone and Watch can
    both log overlapping sleep segments for the same night, so a naive SUM would double-count
    the overlap.
    """
    where_sql, params = _where(
        "start_local_date", start, end, ["type = ?", ASLEEP], [SLEEP_ANALYSIS]
    )
    rows = conn.execute(
        f"SELECT start_date, end_date, start_local_date FROM records "
        f"{where_sql} ORDER BY start_date",
        params,
    ).fetchall()
    intervals = [
        IntervalRecord(
            row["start_date"],
            row["end_date"],
            row["end_date"] - row["start_date"],
            row["start_local_date"],
        )
        for row in rows
    ]
    return nightly_totals(dedup_nonoverlapping(intervals))


def _parse_day(value: str | None) -> date | None:
    """A YYYY-MM-DD query param as a date, or None if absent or malformed -- the partial-
    bucket marking is an extra, so a bad param degrades to "no marking", never a 500.
    """
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _next_month(day: date) -> date:
    """The 1st of the month after `day`'s."""
    return (day.replace(day=28) + timedelta(days=4)).replace(day=1)


def _bucket_last_day(first_day: date, bucket: Bucket) -> date:
    """The last calendar day covered by the bucket that starts on `first_day`."""
    if bucket == "week":
        return first_day + timedelta(days=6)
    if bucket == "month":
        return _next_month(first_day) - timedelta(days=1)
    return first_day


def _mark_partial_buckets(
    points: list[dict],
    bucket: Bucket,
    start: str | None,
    end: str | None,
    latest: str | None,
    earliest: str | None,
) -> None:
    """Sets `partial` on each point of a cumulative series: "in_progress", "truncated" or None.

    A bucket that only covers part of its period reads as a steep drop in any summed metric
    (the week isn't over yet, so its total is a fraction of a normal week's), and the chart
    labels exactly that point. Marking it lets the frontend de-emphasize it:
    - "in_progress": the bucket holds the newest data date. That day is assumed to still be
      recording -- an export is usually taken partway through a day -- the same assumption
      `/api/overview` makes for its "partial_day" case. Daily buckets included: ranges are
      anchored to the newest data date, so the last daily point is usually that partial day.
    - "truncated": the bucket is cut short by something other than time still to come -- it
      begins before the range or before the first day with any data, it runs past a range
      `end` that stops short of the data, or it lies entirely past the newest data date. A
      bucket short at both ends is "in_progress": the period is still running.

    The bounds are the export's, not the series': a metric's own first/last record conflates
    "stopped logging" with "logs sparsely" (a Monday-only metric's final week is complete,
    not partial), so per-metric bounds would dash and unlabel buckets that are perfectly
    representative. A discontinued metric's last bucket therefore stays unmarked -- its dip
    is a real historical fact about that week, not an artifact of the export being taken
    mid-period.

    Only cumulative series get this (sums and counts); an average over part of a period is
    still a fair average, so avg-mode series are left unmarked.
    """
    start_day, end_day = _parse_day(start), _parse_day(end)
    latest_day, earliest_day = _parse_day(latest), _parse_day(earliest)
    # A bucket that starts before the range OR before any data exists is equally partial --
    # the all-time range sends no `start`, so without `earliest` its first bucket dips unmarked.
    lower_bound = max((d for d in (start_day, earliest_day) if d), default=None)
    for point in points:
        first_day = _parse_day(point["date"])
        if first_day is None:
            point["partial"] = None
            continue
        last_day = _bucket_last_day(first_day, bucket)
        holds_latest = bool(latest_day and first_day <= latest_day <= last_day)
        # `end` only truncates when it stops short of the data. The frontend's preset ranges
        # send end == the newest data date, so testing this first would caption every
        # "in progress" bucket as "truncated" instead -- the very case UI-02 is about.
        end_cuts = bool(
            end_day and last_day > end_day and (latest_day is None or end_day < latest_day)
        )
        if end_cuts:
            point["partial"] = "truncated"
        elif holds_latest:
            # Tested before the head cut: a bucket can be short at both ends (all-time on a
            # database whose data starts mid-bucket and ends in the same one), and "in
            # progress" is the more useful caption when the period is still running.
            point["partial"] = "in_progress"
        elif lower_bound and first_day < lower_bound:
            point["partial"] = "truncated"
        elif latest_day and first_day > latest_day:
            # Entirely past the newest date the database records -- e.g. rows added since the
            # span was stored, so the bucket holds only part of what will eventually be there.
            point["partial"] = "truncated"
        else:
            point["partial"] = None


@router.get("/metric-types")
def metric_types(conn: DbDep, start: str | None = None, end: str | None = None) -> list[dict]:
    """Distinct record types with counts/date-range. Pass start/end to restrict to types that
    actually have data in that window -- used to hide empty charts for the selected time range.
    """
    where_sql, params = _where("start_local_date", start, end)
    rows = conn.execute(
        f"""
        SELECT type, COUNT(*) AS count, MAX(unit) AS unit,
               MIN(start_local_date) AS min_date, MAX(start_local_date) AS max_date
        FROM records
        {where_sql}
        GROUP BY type
        ORDER BY count DESC
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


@router.get("/metrics/{metric_type}/timeseries")
def metric_timeseries(
    metric_type: str,
    conn: DbDep,
    start: str | None = None,
    end: str | None = None,
    bucket: Bucket = "day",
) -> dict:
    if aggregation_mode(metric_type) == "sum":
        totals = _deduped_totals(conn, metric_type, start, end, bucket)
        points = [{"date": date, "value": value} for date, value in sorted(totals.items())]
        earliest, latest = _data_span(conn)
        _mark_partial_buckets(points, bucket, start, end, latest, earliest)
    else:
        where_sql, params = _where(
            "start_local_date", start, end, ["type = ?", "value_num IS NOT NULL"], [metric_type]
        )
        rows = conn.execute(
            f"""
            SELECT {_bucket_expr("start_local_date", bucket)} AS date, AVG(value_num) AS value
            FROM records
            {where_sql}
            GROUP BY date
            ORDER BY date
            """,
            params,
        ).fetchall()
        points = [{"date": row["date"], "value": row["value"], "partial": None} for row in rows]

    # Scoped to the same window as the points, and picking the most common unit rather than
    # an arbitrary one: a metric's unit can change over time (weight logged in lb, then kg),
    # and labelling the chart with a unit from outside the plotted range would be wrong.
    unit_where_sql, unit_params = _where(
        "start_local_date", start, end, ["type = ?", "unit IS NOT NULL"], [metric_type]
    )
    unit_row = conn.execute(
        f"""
        SELECT unit FROM records
        {unit_where_sql}
        GROUP BY unit
        ORDER BY COUNT(*) DESC
        LIMIT 1
        """,
        unit_params,
    ).fetchone()

    return {
        "metric_type": metric_type,
        "unit": unit_row["unit"] if unit_row else None,
        "bucket": bucket,
        "aggregation_mode": aggregation_mode(metric_type),
        "points": points,
    }


@router.get("/sleep")
def sleep(
    conn: DbDep, start: str | None = None, end: str | None = None, bucket: Bucket = "day"
) -> dict:
    """Hours asleep per night, from 'Asleep*' sleep-analysis segments.

    A night is one sleep session keyed by the evening it began (see nightly_totals), so a
    night crossing midnight isn't split across two dates. 'day' buckets are that night's
    total. 'week' and 'month' buckets are the *average night*
    in that bucket (total / nights with any sleep logged), not the bucket's sum -- nobody
    thinks of sleep as "45 hours this week". Same per-night averaging as the overview's
    avg_sleep_hours, so the two agree.
    """
    nightly_seconds = _nightly_sleep_seconds(conn, start, end)
    nights_by_bucket: dict[str, list[float]] = {}
    for night, seconds in nightly_seconds.items():
        nights_by_bucket.setdefault(bucket_local_date(night, bucket), []).append(seconds)
    points = [
        {"date": date, "hours": sum(nights) / len(nights) / 3600.0}
        for date, nights in sorted(nights_by_bucket.items())
    ]
    return {"bucket": bucket, "points": points}


@router.get("/blood-pressure")
def blood_pressure(
    conn: DbDep, start: str | None = None, end: str | None = None, bucket: Bucket = "day"
) -> dict:
    where_sql, params = _where(
        "start_local_date", start, end, ["type IN (?, ?)"], [BP_SYSTOLIC, BP_DIASTOLIC]
    )
    rows = conn.execute(
        f"""
        SELECT {_bucket_expr("start_local_date", bucket)} AS date, {BP_AVERAGES}
        FROM records
        {where_sql}
        GROUP BY date
        ORDER BY date
        """,
        params,
    ).fetchall()
    return {
        "bucket": bucket,
        "points": [
            {"date": row["date"], "systolic": row["systolic"], "diastolic": row["diastolic"]}
            for row in rows
        ],
    }


@router.get("/category-metrics/{metric_type}/timeseries")
def category_metric_timeseries(
    metric_type: str,
    conn: DbDep,
    mode: Literal["count", "duration"],
    start: str | None = None,
    end: str | None = None,
    bucket: Bucket = "day",
    value_prefix: str | None = None,
) -> dict:
    """Timeseries for HealthKit *category* types (no numeric value), e.g. Apple Stand Hour,
    Mindful Session, High Heart Rate Event -- these can't go through /metrics/{type}/timeseries
    since value_num is always NULL for them. mode='count' counts records per bucket (e.g. stand
    hours logged, high-HR events); mode='duration' sums record duration in minutes per bucket
    (e.g. mindful minutes). Response shape matches /metrics/{type}/timeseries for a shared
    frontend chart component.

    value_prefix filters to value_text starting with that string -- needed because some category
    types log a record for every check, not just the meaningful ones: Apple Stand Hour logs one
    record per hour *whether or not* the user actually stood ('...Stood' vs '...Idle'), so an
    unfiltered count would report 24 "stand hours" a day regardless of how many were real.
    """
    conditions = ["type = ?"]
    condition_params = [metric_type]
    if value_prefix:
        conditions.append("value_text LIKE ?")
        condition_params.append(f"{value_prefix}%")
    where_sql, params = _where("start_local_date", start, end, conditions, condition_params)

    value_expr = "COUNT(*)" if mode == "count" else "SUM(end_date - start_date) / 60.0"
    unit = "events" if mode == "count" else "min"
    rows = conn.execute(
        f"""
        SELECT {_bucket_expr("start_local_date", bucket)} AS date, {value_expr} AS value
        FROM records
        {where_sql}
        GROUP BY date
        ORDER BY date
        """,
        params,
    ).fetchall()
    # Counts and durations are sums per bucket, so a partial bucket dips like any other sum.
    points = [{"date": row["date"], "value": row["value"]} for row in rows]
    earliest, latest = _data_span(conn)
    _mark_partial_buckets(points, bucket, start, end, latest, earliest)

    return {
        "metric_type": metric_type,
        "unit": unit,
        "bucket": bucket,
        "points": points,
    }


@router.get("/workouts")
def workouts(
    conn: DbDep,
    start: str | None = None,
    end: str | None = None,
    activity_type: str | None = None,
    # Bounded explicitly: SQLite treats a negative LIMIT as unbounded, so an unvalidated
    # limit silently returns the whole table instead of a page of it.
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    conditions: list[str] = []
    condition_params: list = []
    if activity_type:
        conditions.append("activity_type = ?")
        condition_params.append(activity_type)
    where_sql, params = _where("start_local_date", start, end, conditions, condition_params)

    rows = conn.execute(
        f"""
        SELECT id, activity_type, duration, duration_unit,
               total_distance, total_distance_unit,
               total_energy_burned, total_energy_burned_unit,
               start_local_date, start_date, end_date
        FROM workouts
        {where_sql}
        ORDER BY start_date DESC
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()
    return [dict(row) for row in rows]


@router.get("/workouts/summary")
def workouts_summary(conn: DbDep, start: str | None = None, end: str | None = None) -> list[dict]:
    where_sql, params = _where("start_local_date", start, end)
    rows = conn.execute(
        f"""
        SELECT activity_type, COUNT(*) AS count,
               SUM(total_distance) AS total_distance, MAX(total_distance_unit) AS distance_unit,
               SUM(duration) AS total_duration, MAX(duration_unit) AS duration_unit
        FROM workouts
        {where_sql}
        GROUP BY activity_type
        ORDER BY count DESC
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


@router.get("/routes")
def routes(conn: DbDep, start: str | None = None, end: str | None = None) -> list[dict]:
    """GPS tracks for outdoor workouts, matched to their `workouts` row by time overlap at
    ingest time (see gpx_loader.py). workout_id/activity_type are null for a route with no
    overlapping workout -- still returned rather than dropped.

    The workout's distance and duration come along for the same reason its activity type
    does: the track is the shape of the workout, these are the numbers that describe it, and
    the join is already here. All of them are null on an unmatched route -- this is a LEFT
    join, and a missing distance is unknown, not zero. Callers render the absence rather
    than substituting a number, since "0.0 mi" reads as a real measurement of standing still.
    """
    where_sql, params = _where("wr.start_local_date", start, end)
    rows = conn.execute(
        f"""
        SELECT wr.id, wr.workout_id, w.activity_type, wr.start_local_date, wr.points_json,
               w.duration, w.duration_unit, w.total_distance, w.total_distance_unit
        FROM workout_routes wr
        LEFT JOIN workouts w ON w.id = wr.workout_id
        {where_sql}
        ORDER BY wr.start_date DESC
        """,
        params,
    ).fetchall()
    return [
        {
            "id": row["id"],
            "workout_id": row["workout_id"],
            "activity_type": row["activity_type"],
            "start_local_date": row["start_local_date"],
            "duration": row["duration"],
            "duration_unit": row["duration_unit"],
            "total_distance": row["total_distance"],
            "total_distance_unit": row["total_distance_unit"],
            "segments": json.loads(row["points_json"]),
        }
        for row in rows
    ]


@router.get("/ecg")
def ecg_recordings(conn: DbDep, start: str | None = None, end: str | None = None) -> list[dict]:
    """Light list of ECG recordings -- no samples_json, unlike /api/routes' segments. Each
    recording's raw samples are a fixed ~100-150KB regardless of range width, and only the
    one selected recording is ever charted at a time, so inlining every recording's waveform
    into a range-filtered list would bloat the payload for data that's never rendered. See
    /api/ecg/{recording_id} for the downsampled waveform of a single recording.
    """
    where_sql, params = _where("recorded_local_date", start, end)
    rows = conn.execute(
        f"""
        SELECT id, recorded_date, recorded_local_date, classification, symptoms,
               sample_rate, lead, device, sample_count
        FROM ecg_recordings
        {where_sql}
        ORDER BY recorded_date DESC
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


@router.get("/ecg/{recording_id}")
def ecg_recording(
    conn: DbDep,
    recording_id: int,
    max_points: int = Query(2000, ge=100, le=10000),
) -> dict:
    row = conn.execute("SELECT * FROM ecg_recordings WHERE id = ?", [recording_id]).fetchone()
    if row is None:
        raise HTTPException(404, f"No ECG recording with id {recording_id}")

    samples = json.loads(row["samples_json"])
    sample_rate = row["sample_rate"]
    points = [
        {"t": index / sample_rate, "value": value}
        for index, value in downsample_minmax(samples, max_points)
    ]
    return {
        "id": row["id"],
        "recorded_date": row["recorded_date"],
        "recorded_local_date": row["recorded_local_date"],
        "classification": row["classification"],
        "symptoms": row["symptoms"],
        "software_version": row["software_version"],
        "device": row["device"],
        "sample_rate": sample_rate,
        "lead": row["lead"],
        "unit": row["unit"],
        "sample_count": row["sample_count"],
        "points": points,
    }


@router.get("/activity-summary")
def activity_summary(conn: DbDep, start: str | None = None, end: str | None = None) -> list[dict]:
    where_sql, params = _where("date", start, end)
    rows = conn.execute(
        f"SELECT * FROM activity_summaries {where_sql} ORDER BY date", params
    ).fetchall()
    return [dict(row) for row in rows]


@router.get("/clinical")
def clinical(
    conn: DbDep,
    resource_type: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> list[dict]:
    # An IN, not a NOT IN, and built from the shared allowlist rather than spelled out here.
    # A database built before a type was dropped from the ingest list still holds those rows
    # until the next drop-and-reload; asking for the types this app serves excludes them, and
    # excludes anything else unexpected in there, without having to know what it is.
    # See pomona.clinical for why both layers apply the policy.
    served = sorted(INGESTED_RESOURCE_TYPES)
    if not served:
        # `IN ()` is a SQLite syntax error, so an empty allowlist would turn every request into a
        # 500 rather than into an empty page. Nothing can be served, which is what this returns.
        return []
    conditions = [f"resource_type IN ({', '.join('?' * len(served))})"]
    condition_params = [*served]
    if resource_type:
        conditions.append("resource_type = ?")
        condition_params.append(resource_type)
    where_sql, params = _where(
        "date(effective_date, 'unixepoch')", start, end, conditions, condition_params
    )

    # raw_json only for Observations: it's the one type whose reference range and components
    # the page uses, and the other types' raw payloads (documents especially) can be large.
    rows = conn.execute(
        f"""
        SELECT id, resource_type, code_text, code_system, code_value, status,
               value_num, value_unit, value_text, effective_date, category, results_json,
               CASE WHEN resource_type = 'Observation' THEN raw_json END AS raw_json
        FROM clinical_records
        {where_sql}
        ORDER BY effective_date DESC
        """,
        params,
    ).fetchall()
    records = []
    for row in rows:
        record = dict(row)
        results_json = record.pop("results_json")
        # A database ingested before the loader dropped non-finite numbers can hold Infinity
        # or NaN in here, which the response can't encode; read them as missing instead.
        record["results"] = (
            json.loads(results_json, parse_constant=lambda _: None) if results_json else None
        )
        # Parsed once here, not once per helper: both read the same stored resource.
        resource = fhir.parse_resource(record.pop("raw_json"))
        record["reference_range"] = fhir.reference_range(resource)
        record["components"] = fhir.components(resource)
        records.append(record)
    return records


RUNNING = "HKWorkoutActivityTypeRunning"
# Length units a workout distance is recorded in, as metres. Anything else is left out of the
# total rather than guessed at, and counted in `unmeasured_runs` so the card can say so.
_METRES_PER_UNIT = {"m": 1.0, "km": 1000.0, "ft": 0.3048, "yd": 0.9144, "mi": 1609.344}


@router.get("/workouts/running")
def running_mileage(conn: DbDep, start: str | None = None, end: str | None = None) -> dict:
    """Running distance over the range, in total and by calendar month.

    Distances are summed in one unit. A workout's unit is whatever the watch was set to when
    it was recorded, so a history that spans a settings change holds both "mi" and "km", and
    adding those raw would print a number in neither. The total is shown in whichever of mi
    and km most runs were recorded in -- the person's own preference, so it reads the way
    their watch does -- with a tie going to the more recent unit; a history in other length
    units (m, yd) is shown in km. Everything else is converted to it.

    A run whose distance can't be used -- none recorded (a treadmill run the watch lost track
    of), no unit, or a unit that isn't a length -- still counts as a run but adds nothing:
    null is unknown, not zero. `unmeasured_runs` says how many, so a total that leaves some
    out doesn't pass for the whole.

    `points` covers every month of the range that has data, zero-filled, so a month without
    a run shows as a gap rather than disappearing. Months cut short are marked `partial` the
    same way the cumulative charts' buckets are (see `_mark_partial_buckets`).
    """
    where_sql, params = _where("start_local_date", start, end, ["activity_type = ?"], [RUNNING])
    rows = conn.execute(
        f"""
        SELECT strftime('%Y-%m-01', start_local_date) AS month,
               total_distance, total_distance_unit
        FROM workouts
        {where_sql}
        ORDER BY start_local_date
        """,
        params,
    ).fetchall()

    measured = [
        row
        for row in rows
        if row["total_distance"] is not None and row["total_distance_unit"] in _METRES_PER_UNIT
    ]
    # (count, index of latest run) per unit: the max is the most-used, ties to the latest.
    usage: dict[str, tuple[int, int]] = {}
    for i, row in enumerate(measured):
        if row["total_distance_unit"] in ("mi", "km"):
            count, _ = usage.get(row["total_distance_unit"], (0, 0))
            usage[row["total_distance_unit"]] = (count + 1, i)
    unit = max(usage, key=lambda u: usage[u]) if usage else ("km" if measured else None)

    months: dict[str, dict] = {}
    for row in rows:
        point = months.setdefault(row["month"], {"date": row["month"], "distance": 0.0, "runs": 0})
        point["runs"] += 1
    total = 0.0
    for row in measured:
        distance = (
            row["total_distance"] * _METRES_PER_UNIT[row["total_distance_unit"]]
        ) / _METRES_PER_UNIT[unit]
        months[row["month"]]["distance"] += distance
        total += distance

    earliest, latest = _data_span(conn)
    if months:
        # From the range's first month to its last, clamped to the data: months before the
        # export begins or after it ends would be zeros that mean "no data", not "no runs".
        lower = max((d for d in (start, earliest) if d), default=None)
        upper = min((d for d in (end, latest) if d), default=None)
        first = min(min(months), f"{lower[:7]}-01") if lower else min(months)
        last = max(max(months), f"{upper[:7]}-01") if upper else max(months)
        cursor = date.fromisoformat(first)
        while cursor <= date.fromisoformat(last):
            key = cursor.isoformat()
            months.setdefault(key, {"date": key, "distance": 0.0, "runs": 0})
            cursor = _next_month(cursor)

    points = [months[key] for key in sorted(months)]
    _mark_partial_buckets(points, "month", start, end, latest, earliest)
    return {
        "unit": unit,
        "total_distance": total if unit else None,
        "runs": len(rows),
        "unmeasured_runs": len(rows) - len(measured),
        "points": points,
    }


def _previous_period(start: str | None, end: str | None) -> tuple[str, str] | None:
    """The period of equal length immediately before [start, end], both ends inclusive.

    None when either bound is missing (all-time, or a half-filled custom range): there's no
    equal-length period before an unbounded one. Also None for a malformed or inverted range,
    rather than a 500 -- the comparison is an extra, and the main stats still render.
    """
    if not start or not end:
        return None
    try:
        start_day, end_day = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        return None
    if end_day < start_day:
        return None
    prev_end = start_day - timedelta(days=1)
    prev_start = prev_end - (end_day - start_day)
    return prev_start.isoformat(), prev_end.isoformat()


def _overview_stats(conn, start: str | None, end: str | None) -> dict:
    """The overview's summary stats for one date range -- see `overview`."""

    def fetch_row(select: str, conditions: list[str], params: list, table: str = "records"):
        where_sql, all_params = _where("start_local_date", start, end, conditions, params)
        return conn.execute(f"SELECT {select} FROM {table} {where_sql}", all_params).fetchone()

    def avg_with_unit(metric_type: str) -> dict | None:
        row = fetch_row("AVG(value_num) AS avg, MAX(unit) AS unit", ["type = ?"], [metric_type])
        if row is None or row["avg"] is None:
            return None
        return {"value": row["avg"], "unit": row["unit"]}

    daily_step_totals = _deduped_totals(conn, STEP_COUNT, start, end, "day")
    avg_daily_steps = (
        sum(daily_step_totals.values()) / len(daily_step_totals) if daily_step_totals else None
    )
    avg_weight = avg_with_unit(BODY_MASS)
    avg_resting_hr = fetch_row("AVG(value_num)", ["type = ?"], [RESTING_HR])[0]
    workout_count = fetch_row("COUNT(*)", [], [], table="workouts")[0]
    avg_vo2_max = avg_with_unit(VO2_MAX)
    nightly_seconds = _nightly_sleep_seconds(conn, start, end)
    avg_sleep_hours = (
        sum(nightly_seconds.values()) / len(nightly_seconds) / 3600.0 if nightly_seconds else None
    )
    bp_row = fetch_row(BP_AVERAGES, ["type IN (?, ?)"], [BP_SYSTOLIC, BP_DIASTOLIC])
    avg_blood_pressure = (
        {"systolic": bp_row["systolic"], "diastolic": bp_row["diastolic"]}
        if bp_row["systolic"] is not None or bp_row["diastolic"] is not None
        else None
    )
    avg_hrv = avg_with_unit(HRV_SDNN)

    return {
        "avg_daily_steps": avg_daily_steps,
        "avg_weight": avg_weight,
        "avg_resting_hr": avg_resting_hr,
        "workout_count": int(workout_count) if workout_count is not None else 0,
        "avg_vo2_max": avg_vo2_max,
        "avg_sleep_hours": avg_sleep_hours,
        "avg_blood_pressure": avg_blood_pressure,
        "avg_hrv": avg_hrv,
    }


@router.get("/overview")
def overview(conn: DbDep, start: str | None = None, end: str | None = None) -> dict:
    """Period-summary stats over the given date range (matching the dashboard's time-range
    filter) rather than a 'latest reading' snapshot -- this data is imported in occasional
    batches, not continuously synced, so 'latest' would just mean 'as of the last import',
    which is stale and not particularly meaningful on its own.

    `previous` holds the same stats for the equal-length period just before this one, so the
    cards can show a period-over-period change. `previous_range` is null for an unbounded
    range. The frontend sends ranges already anchored to the newest data (see
    useAnchoredRange), so "previous" is relative to that anchor, not to today.

    `previous` is also null -- with `previous_range` still set, so the UI can say why -- when
    the two windows aren't comparable:
    - The previous window starts before the oldest data. Counts like `workout_count` are 0,
      not null, over a window with no data, so without this "Last year" on an 8-month export
      would show a full year's workouts as growth; a window only partly covered would
      overstate any count the same way.
    - The range is a single day on or after the newest data date. That day is usually still
      in progress (an export taken mid-morning), and a partial day against a full one reads
      as a steep drop in every cumulative stat. Longer ranges ending there carry the same
      bias diluted over their length, which is accepted.

    `previous_withheld` says which of those applied ("before_data" or "partial_day"), and is
    null whenever `previous` is present or there's no previous range at all.
    """
    previous_range = _previous_period(start, end)
    withheld = None
    if previous_range is not None:
        earliest, latest = _data_span(conn)
        if start == end and latest is not None and start >= latest:
            withheld = "partial_day"
        elif earliest is None or previous_range[0] < earliest:
            withheld = "before_data"
    return {
        "date_range": {"start": start, "end": end},
        **_overview_stats(conn, start, end),
        "previous_range": (
            {"start": previous_range[0], "end": previous_range[1]} if previous_range else None
        ),
        "previous": (
            _overview_stats(conn, *previous_range) if previous_range and not withheld else None
        ),
        "previous_withheld": withheld,
    }


# Live fallback results of `_data_span`, keyed by (database file, ingested_at). Every
# cumulative chart asks for the newest data date, so without this a database ingested before
# `earliest_date`/`latest_date` were stored would re-scan `records` once per chart per load.
# ingested_at changes on every ingest -- the only writer -- so a stale entry is never hit.
_live_span_cache: dict[tuple[str, str], tuple[str | None, str | None]] = {}
_live_span_lock = threading.Lock()


def _data_span(conn) -> tuple[str | None, str | None]:
    """(earliest, latest) local dates with data, from `ingest_meta` where ingest stores them,
    falling back to computing each live for a database ingested before its key existed (both
    are full index scans of `records` on a real export -- see db.latest_data_date). The live
    result is cached per ingest, when the database records one.
    """
    stored = {
        row["key"]: row["value"]
        for row in conn.execute(
            "SELECT key, value FROM ingest_meta "
            "WHERE key IN ('earliest_date', 'latest_date', 'ingested_at')"
        )
    }
    if "earliest_date" in stored and "latest_date" in stored:
        # Each is stored as "" when the ingest had no dated data at all.
        return stored["earliest_date"] or None, stored["latest_date"] or None

    def compute() -> tuple[str | None, str | None]:
        earliest = (
            stored["earliest_date"] or None
            if "earliest_date" in stored
            else earliest_data_date(conn)
        )
        latest = (
            stored["latest_date"] or None if "latest_date" in stored else latest_data_date(conn)
        )
        return earliest, latest

    ingested_at = stored.get("ingested_at")
    if not ingested_at:
        # Not built by `pomona ingest` (e.g. a test fixture), so there's no ingest
        # identity to key a cache on -- always compute.
        return compute()
    cache_key = (conn.execute("PRAGMA database_list").fetchone()[2], ingested_at)
    with _live_span_lock:
        if cache_key not in _live_span_cache:
            _live_span_cache[cache_key] = compute()
        return _live_span_cache[cache_key]


@router.get("/meta")
def meta(conn: DbDep) -> dict:
    """How fresh the data is, so the frontend can anchor relative ranges ("last 30 days") to
    the newest record instead of today. Data arrives in occasional manual exports, not a
    continuous sync, so "today" is usually past the end of the data -- anchoring to it makes
    the default view empty whenever the last export is over a month old.

    `latest_date` is the newest local date across records, workouts and ECG recordings (see
    `db.latest_data_date`). Anchoring on records alone would push a workout or ECG newer than
    the last Record outside every relative range. Every dated page waits on this endpoint at
    load and on each window refocus, so it's read from `ingest_meta`, where ingest stores it,
    rather than recomputed per request -- the `records` part is a full index scan on a real
    export. A database ingested before that key existed falls back to computing it live.

    `ingested_at` is when `pomona ingest` last ran, as a unix epoch. Either is null
    on an empty or partially built database.
    """
    stored = {
        row["key"]: row["value"]
        for row in conn.execute(
            "SELECT key, value FROM ingest_meta WHERE key IN ('latest_date', 'ingested_at')"
        )
    }
    if "latest_date" in stored:
        # Stored as "" when the ingest had no dated data at all.
        latest_date = stored["latest_date"] or None
    else:
        latest_date = latest_data_date(conn)
    return {
        "latest_date": latest_date,
        "ingested_at": int(stored["ingested_at"]) if "ingested_at" in stored else None,
    }
