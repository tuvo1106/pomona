"""Query building and reads shared by the API's endpoint modules: the date-range WHERE
clause, bucket expressions, deduplicated totals, partial-bucket marking, and the span of dates
the database holds.
"""

import threading
from datetime import date, timedelta
from typing import Literal

from pomona.db import earliest_data_date, latest_data_date
from pomona.dedup import IntervalRecord, dedup_nonoverlapping, nightly_totals, sum_by_bucket

# Validated by FastAPI from the annotation, so an unknown value is a 422 before the handler runs.
Bucket = Literal["day", "week", "month"]


def bucket_expr(column: str, bucket: Bucket) -> str:
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


def where_clause(
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


def deduped_totals(
    conn, metric_type: str, start: str | None, end: str | None, bucket: Bucket
) -> dict[str, float]:
    """A cumulative metric's total per bucket, deduplicated across sources first.

    Cumulative metrics (steps, energy, distance, ...) are independently logged by every
    source that tracks them, so a naive SUM double-counts overlapping devices -- dedupe by
    time window first. See dedup.py.
    """
    where_sql, params = where_clause(
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


def nightly_sleep_seconds(conn, start: str | None, end: str | None) -> dict[str, float]:
    """Seconds asleep per night, keyed by the evening the night began (see nightly_totals).

    Deduplicated the same way cumulative metrics are (see dedup.py): iPhone and Watch can
    both log overlapping sleep segments for the same night, so a naive SUM would double-count
    the overlap.
    """
    where_sql, params = where_clause(
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


def next_month(day: date) -> date:
    """The 1st of the month after `day`'s."""
    return (day.replace(day=28) + timedelta(days=4)).replace(day=1)


def bucket_last_day(first_day: date, bucket: Bucket) -> date:
    """The last calendar day covered by the bucket that starts on `first_day`."""
    if bucket == "week":
        return first_day + timedelta(days=6)
    if bucket == "month":
        return next_month(first_day) - timedelta(days=1)
    return first_day


def mark_partial_buckets(
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
        last_day = bucket_last_day(first_day, bucket)
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


# Live fallback results of `data_span`, keyed by (database file, ingested_at). Every
# cumulative chart asks for the newest data date, so without this a database ingested before
# `earliest_date`/`latest_date` were stored would re-scan `records` once per chart per load.
# ingested_at changes on every ingest -- the only writer -- so a stale entry is never hit.
_live_span_cache: dict[tuple[str, str], tuple[str | None, str | None]] = {}
_live_span_lock = threading.Lock()


def data_span(conn) -> tuple[str | None, str | None]:
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
