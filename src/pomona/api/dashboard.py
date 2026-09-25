import json
import threading
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query

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

VALID_BUCKETS = {"day", "week", "month"}


def _bucket_expr(column: str, bucket: str) -> str:
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

# The ways a FHIR feed spells "this coding is LOINC". Used to pick the LOINC code out of a
# component's `coding[]`, which an EHR may fill with codings from several systems. The OID
# form is what older interfaces send, and both spellings identify the same code system.
LOINC_SYSTEMS = frozenset(
    {"http://loinc.org", "https://loinc.org", "urn:oid:2.16.840.1.113883.6.1"}
)


def _date_range_where(
    column: str, start: str | None, end: str | None
) -> tuple[list[str], list[str]]:
    where: list[str] = []
    params: list[str] = []
    if start:
        where.append(f"{column} >= ?")
        params.append(start)
    if end:
        where.append(f"{column} <= ?")
        params.append(end)
    return where, params


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


def _bucket_last_day(first_day: date, bucket: str) -> date:
    """The last calendar day covered by the bucket that starts on `first_day`."""
    if bucket == "week":
        return first_day + timedelta(days=6)
    if bucket == "month":
        next_month = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1)
        return next_month - timedelta(days=1)
    return first_day


def _mark_partial_buckets(
    points: list[dict],
    bucket: str,
    start: str | None,
    end: str | None,
    latest: str | None,
    earliest: str | None = None,
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
    where, params = _date_range_where("start_local_date", start, end)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

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
    bucket: str = "day",
) -> dict:
    if bucket not in VALID_BUCKETS:
        raise HTTPException(400, "bucket must be one of: day, week, month")

    where = ["type = ?", "value_num IS NOT NULL"]
    params: list = [metric_type]
    range_where, range_params = _date_range_where("start_local_date", start, end)
    where += range_where
    params += range_params
    where_sql = " AND ".join(where)

    if aggregation_mode(metric_type) == "sum":
        # Cumulative metrics (steps, energy, distance, ...) are independently logged by every
        # source that tracks them, so a naive SUM double-counts overlapping devices -- dedupe
        # by time window first. See dedup.py.
        rows = conn.execute(
            f"SELECT start_date, end_date, value_num, start_local_date "
            f"FROM records WHERE {where_sql} ORDER BY start_date",
            params,
        ).fetchall()
        intervals = [
            IntervalRecord(
                row["start_date"], row["end_date"], row["value_num"], row["start_local_date"]
            )
            for row in rows
        ]
        totals = sum_by_bucket(dedup_nonoverlapping(intervals), bucket)
        points = [{"date": date, "value": value} for date, value in sorted(totals.items())]
        earliest, latest = _data_span(conn)
        _mark_partial_buckets(points, bucket, start, end, latest, earliest)
    else:
        bucket_expr = _bucket_expr("start_local_date", bucket)
        sql = f"""
            SELECT {bucket_expr} AS date, AVG(value_num) AS value
            FROM records
            WHERE {where_sql}
            GROUP BY date
            ORDER BY date
        """
        rows = conn.execute(sql, params).fetchall()
        points = [{"date": row["date"], "value": row["value"], "partial": None} for row in rows]

    # Scoped to the same window as the points, and picking the most common unit rather than
    # an arbitrary one: a metric's unit can change over time (weight logged in lb, then kg),
    # and labelling the chart with a unit from outside the plotted range would be wrong.
    unit_row = conn.execute(
        f"""
        SELECT unit FROM records
        WHERE {" AND ".join(["type = ?", "unit IS NOT NULL", *range_where])}
        GROUP BY unit
        ORDER BY COUNT(*) DESC
        LIMIT 1
        """,
        [metric_type, *range_params],
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
    conn: DbDep, start: str | None = None, end: str | None = None, bucket: str = "day"
) -> dict:
    """Hours asleep per night, from 'Asleep*' sleep-analysis segments.

    A night is one sleep session keyed by the evening it began (see nightly_totals), so a
    night crossing midnight isn't split across two dates. 'day' buckets are that night's
    total. 'week' and 'month' buckets are the *average night*
    in that bucket (total / nights with any sleep logged), not the bucket's sum -- nobody
    thinks of sleep as "45 hours this week". Same per-night averaging as the overview's
    avg_sleep_hours, so the two agree.

    Deduplicated the same way cumulative metrics are (see dedup.py): iPhone and Watch can
    both log overlapping sleep segments for the same night, so a naive SUM would double-count
    the overlap.
    """
    if bucket not in VALID_BUCKETS:
        raise HTTPException(400, "bucket must be one of: day, week, month")

    where = ["type = ?", "value_text LIKE 'HKCategoryValueSleepAnalysisAsleep%'"]
    params: list = [SLEEP_ANALYSIS]
    range_where, range_params = _date_range_where("start_local_date", start, end)
    where += range_where
    params += range_params

    rows = conn.execute(
        f"SELECT start_date, end_date, start_local_date FROM records "
        f"WHERE {' AND '.join(where)} ORDER BY start_date",
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
    nightly_seconds = nightly_totals(dedup_nonoverlapping(intervals))
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
    conn: DbDep, start: str | None = None, end: str | None = None, bucket: str = "day"
) -> dict:
    if bucket not in VALID_BUCKETS:
        raise HTTPException(400, "bucket must be one of: day, week, month")

    where = ["type IN (?, ?)"]
    params: list = [BP_SYSTOLIC, BP_DIASTOLIC]
    range_where, range_params = _date_range_where("start_local_date", start, end)
    where += range_where
    params += range_params

    bucket_expr = _bucket_expr("start_local_date", bucket)
    rows = conn.execute(
        f"""
        SELECT {bucket_expr} AS date,
               AVG(CASE WHEN type = '{BP_SYSTOLIC}' THEN value_num END) AS systolic,
               AVG(CASE WHEN type = '{BP_DIASTOLIC}' THEN value_num END) AS diastolic
        FROM records
        WHERE {" AND ".join(where)}
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
    mode: str,
    start: str | None = None,
    end: str | None = None,
    bucket: str = "day",
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
    if bucket not in VALID_BUCKETS:
        raise HTTPException(400, "bucket must be one of: day, week, month")
    if mode not in ("count", "duration"):
        raise HTTPException(400, "mode must be one of: count, duration")

    where = ["type = ?"]
    params: list = [metric_type]
    if value_prefix:
        where.append("value_text LIKE ?")
        params.append(f"{value_prefix}%")
    range_where, range_params = _date_range_where("start_local_date", start, end)
    where += range_where
    params += range_params

    value_expr = "COUNT(*)" if mode == "count" else "SUM(end_date - start_date) / 60.0"
    unit = "events" if mode == "count" else "min"
    bucket_expr = _bucket_expr("start_local_date", bucket)
    sql = f"""
        SELECT {bucket_expr} AS date, {value_expr} AS value
        FROM records
        WHERE {" AND ".join(where)}
        GROUP BY date
        ORDER BY date
    """
    rows = conn.execute(sql, params).fetchall()
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
    where, params = _date_range_where("start_local_date", start, end)
    if activity_type:
        where.append("activity_type = ?")
        params.append(activity_type)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

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
    where, params = _date_range_where("start_local_date", start, end)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

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
    where, params = _date_range_where("wr.start_local_date", start, end)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

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
    where, params = _date_range_where("recorded_local_date", start, end)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

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
    where, params = _date_range_where("date", start, end)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

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
    where = [f"resource_type IN ({', '.join('?' * len(served))})"]
    params: list = [*served]
    if resource_type:
        where.append("resource_type = ?")
        params.append(resource_type)
    range_where, range_params = _date_range_where("date(effective_date, 'unixepoch')", start, end)
    where += range_where
    params += range_params

    # raw_json only for Observations: it's the one type whose reference range and components
    # the page uses, and the other types' raw payloads (documents especially) can be large.
    rows = conn.execute(
        f"""
        SELECT id, resource_type, code_text, code_system, code_value, status,
               value_num, value_unit, value_text, effective_date, category, results_json,
               CASE WHEN resource_type = 'Observation' THEN raw_json END AS raw_json
        FROM clinical_records
        WHERE {" AND ".join(where)}
        ORDER BY effective_date DESC
        """,
        params,
    ).fetchall()
    records = []
    for row in rows:
        record = dict(row)
        results_json = record.pop("results_json")
        record["results"] = json.loads(results_json) if results_json else None
        # Parsed once here, not once per helper: both read the same stored resource.
        resource = _resource(record.pop("raw_json"))
        record["reference_range"] = _reference_range(resource)
        record["components"] = _components(resource)
        records.append(record)
    return records


def _resource(raw_json: str | None) -> dict | None:
    """The stored FHIR resource as a dict, or None if it isn't one."""
    if not raw_json:
        return None
    try:
        resource = json.loads(raw_json)
    except json.JSONDecodeError:
        return None
    return resource if isinstance(resource, dict) else None


def _reference_range(resource: dict | None) -> dict | None:
    """The first FHIR `referenceRange` on an Observation, flattened for display.

    Read at request time from the stored resource rather than added as columns, so no
    schema change is needed. `low`/`high` are only populated when the bound is a number;
    a text-only range ("Negative", "See comment") comes back with just `text`, and the
    frontend shows it without flagging anything.
    """
    return _flatten_range(resource.get("referenceRange")) if resource else None


def _flatten_range(ranges: object) -> dict | None:
    if not isinstance(ranges, list) or not ranges or not isinstance(ranges[0], dict):
        return None
    first = ranges[0]

    def bound(key: str) -> tuple[float | None, str | None]:
        side = first.get(key)
        value = side.get("value") if isinstance(side, dict) else None
        # bool is an int subclass -- a malformed `"value": true` isn't a bound.
        if not isinstance(value, int | float) or isinstance(value, bool):
            return None, None
        return value, side.get("unit")

    low, low_unit = bound("low")
    high, high_unit = bound("high")
    text = first.get("text") if isinstance(first.get("text"), str) else None
    if low is None and high is None and text is None:
        return None
    return {"low": low, "high": high, "unit": low_unit or high_unit, "text": text}


def _components(resource: dict | None) -> list[dict] | None:
    """An Observation's FHIR `component[]` entries, flattened for display.

    A panel measured in parts -- blood pressure above all -- carries no top-level `value[x]`
    at all: each part is a `component` with its own code, value and (sometimes) reference
    range, so `value_num`/`value_text` on the row are both null and the page has nothing to
    show without this. Read from the stored resource at request time, like `_reference_range`,
    so no schema change or re-ingest is needed.

    None rather than `[]` for the ordinary single-valued Observation, so the frontend can
    test one field for "this row is a panel". Entries with neither a label nor a value are
    dropped; the order is the resource's, which FHIR does not constrain -- callers that care
    which part is which (systolic vs diastolic) must look at `code`, not the position.
    """
    components = resource.get("component") if resource else None
    if not isinstance(components, list):
        return None

    flattened = []
    for component in components:
        if not isinstance(component, dict):
            continue
        code = component.get("code")
        code = code if isinstance(code, dict) else {}
        coding = code.get("coding")
        codings = [c for c in coding if isinstance(c, dict)] if isinstance(coding, list) else []
        label = code.get("text")
        if not isinstance(label, str) or not label:
            label = next(
                (c["display"] for c in codings if isinstance(c.get("display"), str)),
                None,
            )
        loinc = next(
            (
                c["code"]
                for c in codings
                if c.get("system") in LOINC_SYSTEMS and isinstance(c.get("code"), str)
            ),
            None,
        )
        value_num, value_unit = _quantity(component.get("valueQuantity"))
        value_text = component.get("valueString")
        if not isinstance(value_text, str):
            value_text = None
        if label is None and value_num is None and value_text is None:
            continue
        flattened.append(
            {
                "label": label,
                "code": loinc,
                "value_num": value_num,
                "value_unit": value_unit,
                "value_text": value_text,
                "reference_range": _flatten_range(component.get("referenceRange")),
            }
        )
    return flattened or None


def _quantity(quantity: object) -> tuple[float | None, str | None]:
    """A FHIR Quantity's numeric value and unit, or (None, None) if it isn't one."""
    if not isinstance(quantity, dict):
        return None, None
    value = quantity.get("value")
    # bool is an int subclass -- a malformed `"value": true` isn't a measurement.
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None, None
    unit = quantity.get("unit")
    return value, unit if isinstance(unit, str) else None


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
    range_where, range_params = _date_range_where("start_local_date", start, end)

    def and_range(*base: str) -> str:
        return " AND ".join([*base, *range_where])

    def scalar(sql: str, extra_params: list) -> float | None:
        row = conn.execute(sql, [*extra_params, *range_params]).fetchone()
        return row[0] if row else None

    def avg_with_unit(metric_type: str) -> dict | None:
        row = conn.execute(
            f"SELECT AVG(value_num) AS avg, MAX(unit) AS unit "
            f"FROM records WHERE {and_range('type = ?')}",
            [metric_type, *range_params],
        ).fetchone()
        if row is None or row["avg"] is None:
            return None
        return {"value": row["avg"], "unit": row["unit"]}

    step_rows = conn.execute(
        f"SELECT start_date, end_date, value_num, start_local_date "
        f"FROM records WHERE {and_range('type = ?', 'value_num IS NOT NULL')} ORDER BY start_date",
        [STEP_COUNT, *range_params],
    ).fetchall()
    step_intervals = [
        IntervalRecord(
            row["start_date"], row["end_date"], row["value_num"], row["start_local_date"]
        )
        for row in step_rows
    ]
    daily_step_totals = sum_by_bucket(dedup_nonoverlapping(step_intervals), "day")
    avg_daily_steps = (
        sum(daily_step_totals.values()) / len(daily_step_totals) if daily_step_totals else None
    )
    avg_weight = avg_with_unit(BODY_MASS)
    avg_resting_hr = scalar(
        f"SELECT AVG(value_num) FROM records WHERE {and_range('type = ?')}",
        [RESTING_HR],
    )
    workout_count = scalar(f"SELECT COUNT(*) FROM workouts WHERE {and_range('1=1')}", [])
    avg_vo2_max = avg_with_unit(VO2_MAX)
    # Deduplicated the same way as avg_daily_steps above -- iPhone and Watch can log
    # overlapping sleep segments for the same night (see dedup.py).
    asleep_condition = "value_text LIKE 'HKCategoryValueSleepAnalysisAsleep%'"
    sleep_rows = conn.execute(
        f"SELECT start_date, end_date, start_local_date FROM records "
        f"WHERE {and_range('type = ?', asleep_condition)} ORDER BY start_date",
        [SLEEP_ANALYSIS, *range_params],
    ).fetchall()
    sleep_intervals = [
        IntervalRecord(
            row["start_date"],
            row["end_date"],
            row["end_date"] - row["start_date"],
            row["start_local_date"],
        )
        for row in sleep_rows
    ]
    nightly_seconds = nightly_totals(dedup_nonoverlapping(sleep_intervals))
    avg_sleep_hours = (
        sum(nightly_seconds.values()) / len(nightly_seconds) / 3600.0 if nightly_seconds else None
    )
    bp_row = conn.execute(
        f"""
        SELECT AVG(CASE WHEN type = '{BP_SYSTOLIC}' THEN value_num END) AS systolic,
               AVG(CASE WHEN type = '{BP_DIASTOLIC}' THEN value_num END) AS diastolic
        FROM records
        WHERE {and_range("type IN (?, ?)")}
        """,
        [BP_SYSTOLIC, BP_DIASTOLIC, *range_params],
    ).fetchone()
    avg_blood_pressure = (
        {"systolic": bp_row["systolic"], "diastolic": bp_row["diastolic"]}
        if bp_row and (bp_row["systolic"] is not None or bp_row["diastolic"] is not None)
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
