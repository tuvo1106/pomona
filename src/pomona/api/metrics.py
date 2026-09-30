"""Health record series: which metric types exist, their timeseries, sleep, blood pressure,
and Apple's daily activity summaries.
"""

from typing import Literal

from fastapi import APIRouter

from pomona.api.dependencies import DbDep
from pomona.api.query import (
    BP_AVERAGES,
    BP_DIASTOLIC,
    BP_SYSTOLIC,
    Bucket,
    bucket_expr,
    data_span,
    deduped_totals,
    mark_partial_buckets,
    nightly_sleep_seconds,
    where_clause,
)
from pomona.dedup import bucket_local_date
from pomona.metrics import aggregation_mode

router = APIRouter(prefix="/api", tags=["metrics"])


@router.get("/metric-types")
def metric_types(conn: DbDep, start: str | None = None, end: str | None = None) -> list[dict]:
    """Distinct record types with counts/date-range. Pass start/end to restrict to types that
    actually have data in that window -- used to hide empty charts for the selected time range.
    """
    where_sql, params = where_clause("start_local_date", start, end)
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
        totals = deduped_totals(conn, metric_type, start, end, bucket)
        points = [{"date": date, "value": value} for date, value in sorted(totals.items())]
        earliest, latest = data_span(conn)
        mark_partial_buckets(points, bucket, start, end, latest, earliest)
    else:
        where_sql, params = where_clause(
            "start_local_date", start, end, ["type = ?", "value_num IS NOT NULL"], [metric_type]
        )
        rows = conn.execute(
            f"""
            SELECT {bucket_expr("start_local_date", bucket)} AS date, AVG(value_num) AS value
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
    unit_where_sql, unit_params = where_clause(
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
    nightly_seconds = nightly_sleep_seconds(conn, start, end)
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
    where_sql, params = where_clause(
        "start_local_date", start, end, ["type IN (?, ?)"], [BP_SYSTOLIC, BP_DIASTOLIC]
    )
    rows = conn.execute(
        f"""
        SELECT {bucket_expr("start_local_date", bucket)} AS date, {BP_AVERAGES}
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
    where_sql, params = where_clause("start_local_date", start, end, conditions, condition_params)

    value_expr = "COUNT(*)" if mode == "count" else "SUM(end_date - start_date) / 60.0"
    unit = "events" if mode == "count" else "min"
    rows = conn.execute(
        f"""
        SELECT {bucket_expr("start_local_date", bucket)} AS date, {value_expr} AS value
        FROM records
        {where_sql}
        GROUP BY date
        ORDER BY date
        """,
        params,
    ).fetchall()
    # Counts and durations are sums per bucket, so a partial bucket dips like any other sum.
    points = [{"date": row["date"], "value": row["value"]} for row in rows]
    earliest, latest = data_span(conn)
    mark_partial_buckets(points, bucket, start, end, latest, earliest)

    return {
        "metric_type": metric_type,
        "unit": unit,
        "bucket": bucket,
        "points": points,
    }


@router.get("/activity-summary")
def activity_summary(conn: DbDep, start: str | None = None, end: str | None = None) -> list[dict]:
    where_sql, params = where_clause("date", start, end)
    rows = conn.execute(
        f"SELECT * FROM activity_summaries {where_sql} ORDER BY date", params
    ).fetchall()
    return [dict(row) for row in rows]
