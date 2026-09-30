"""Workouts: the list, per-type summary, running mileage, and GPS routes."""

import json
from datetime import date

from fastapi import APIRouter, Query

from pomona.api.dependencies import DbDep
from pomona.api.query import data_span, mark_partial_buckets, next_month, where_clause

router = APIRouter(prefix="/api", tags=["workouts"])


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
    where_sql, params = where_clause("start_local_date", start, end, conditions, condition_params)

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
    where_sql, params = where_clause("start_local_date", start, end)
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
    same way the cumulative charts' buckets are (see `mark_partial_buckets`).
    """
    where_sql, params = where_clause(
        "start_local_date", start, end, ["activity_type = ?"], [RUNNING]
    )
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

    earliest, latest = data_span(conn)
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
            cursor = next_month(cursor)

    points = [months[key] for key in sorted(months)]
    mark_partial_buckets(points, "month", start, end, latest, earliest)
    return {
        "unit": unit,
        "total_distance": total if unit else None,
        "runs": len(rows),
        "unmeasured_runs": len(rows) - len(measured),
        "points": points,
    }


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
    where_sql, params = where_clause("wr.start_local_date", start, end)
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
