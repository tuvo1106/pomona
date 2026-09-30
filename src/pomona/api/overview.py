"""The dashboard's summary stats for a range, compared with the period before it."""

from datetime import date, timedelta

from fastapi import APIRouter

from pomona.api.dependencies import DbDep
from pomona.api.query import (
    BODY_MASS,
    BP_AVERAGES,
    BP_DIASTOLIC,
    BP_SYSTOLIC,
    HRV_SDNN,
    RESTING_HR,
    STEP_COUNT,
    VO2_MAX,
    data_span,
    deduped_totals,
    nightly_sleep_seconds,
    where_clause,
)

router = APIRouter(prefix="/api", tags=["overview"])


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
        where_sql, all_params = where_clause("start_local_date", start, end, conditions, params)
        return conn.execute(f"SELECT {select} FROM {table} {where_sql}", all_params).fetchone()

    def avg_with_unit(metric_type: str) -> dict | None:
        row = fetch_row("AVG(value_num) AS avg, MAX(unit) AS unit", ["type = ?"], [metric_type])
        if row is None or row["avg"] is None:
            return None
        return {"value": row["avg"], "unit": row["unit"]}

    daily_step_totals = deduped_totals(conn, STEP_COUNT, start, end, "day")
    avg_daily_steps = (
        sum(daily_step_totals.values()) / len(daily_step_totals) if daily_step_totals else None
    )
    avg_weight = avg_with_unit(BODY_MASS)
    avg_resting_hr = fetch_row("AVG(value_num)", ["type = ?"], [RESTING_HR])[0]
    workout_count = fetch_row("COUNT(*)", [], [], table="workouts")[0]
    avg_vo2_max = avg_with_unit(VO2_MAX)
    nightly_seconds = nightly_sleep_seconds(conn, start, end)
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
        earliest, latest = data_span(conn)
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
