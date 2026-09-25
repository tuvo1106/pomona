"""Greedy non-overlapping interval deduplication for cumulative HealthKit metrics.

Apple Health independently logs step count (and other cumulative "sum" metrics: active/basal
energy, distance, flights climbed) from every device that tracks them -- iPhone and Apple Watch
both record steps for overlapping stretches of the day. Naively summing every record therefore
inflates the true total on any day with more than one active source (e.g. 23,215 "steps" on a day
that was really ~13,000, because the Watch and two iPhone entries each logged overlapping counts).

This walks records in chronological order and keeps one only if its time window doesn't overlap
any window already kept, so the resulting sum never double-counts real-world activity. The
tradeoff: a record that does overlap is dropped in full, not partially credited -- HealthKit gives
no way to know which portion of a count happened in the overlapping sub-interval, so partial
credit would just be a different kind of guess. This can't be expressed as a single SQL query
(the accept/reject decision for each row depends on which earlier rows were themselves accepted,
which is exactly the kind of sequential state a set-based query can't carry across rows without
recursion) -- pure Python is simpler and fast enough at this data's scale (a few hundred thousand
rows at most for a single metric type over the entire export).
"""

from dataclasses import dataclass
from datetime import date as date_cls
from datetime import timedelta


@dataclass(frozen=True, slots=True)
class IntervalRecord:
    start_date: int  # unix epoch seconds
    end_date: int  # unix epoch seconds
    value: float
    start_local_date: str  # 'YYYY-MM-DD', for bucketing after dedup


def dedup_nonoverlapping(records: list[IntervalRecord]) -> list[IntervalRecord]:
    """Returns the subset of records whose time window doesn't overlap any earlier-sorted
    record that was itself kept. Sorted by (start_date, end_date) for a deterministic result
    regardless of the order records are passed in.
    """
    ordered = sorted(records, key=lambda r: (r.start_date, r.end_date))
    kept: list[IntervalRecord] = []
    covered_until: int | None = None
    for r in ordered:
        if covered_until is None or r.start_date >= covered_until:
            kept.append(r)
            covered_until = r.end_date
    return kept


def bucket_local_date(local_date: str, bucket: str) -> str:
    """Maps a 'YYYY-MM-DD' string to its bucket key: unchanged for 'day', the Monday of its
    week for 'week', or the 1st of its month for 'month' -- matches the SQL bucket semantics
    used elsewhere in the API (BUCKET_EXPRESSIONS in api/dashboard.py).
    """
    d = date_cls.fromisoformat(local_date)
    if bucket == "week":
        d -= timedelta(days=d.weekday())
    elif bucket == "month":
        d = d.replace(day=1)
    return d.isoformat()


def sum_by_bucket(records: list[IntervalRecord], bucket: str) -> dict[str, float]:
    totals: dict[str, float] = {}
    for r in records:
        key = bucket_local_date(r.start_local_date, bucket)
        totals[key] = totals.get(key, 0.0) + r.value
    return totals


# A gap longer than this between consecutive asleep segments starts a new sleep session.
# Stage segments within one night (Core/Deep/REM, brief wakes) are minutes apart; separate
# nights are many hours apart.
SLEEP_SESSION_GAP_SECONDS = 3 * 3600


def nightly_totals(records: list[IntervalRecord]) -> dict[str, float]:
    """Sums dedup'd sleep segments per *night*, keyed by the local date the session started.

    Keying each segment by its own start_local_date instead would split one night that
    crosses midnight into two keys (a short pre-midnight fragment, then the rest), and any
    per-night average would count it as two short nights. Grouping into sessions first keeps
    the whole night under the evening it began. No timezone offset is needed: sessions are
    found from epoch gaps, and only the first segment's local date is used.
    """
    totals: dict[str, float] = {}
    session_key: str | None = None
    last_end: int | None = None
    for r in sorted(records, key=lambda r: (r.start_date, r.end_date)):
        if last_end is None or r.start_date - last_end > SLEEP_SESSION_GAP_SECONDS:
            session_key = r.start_local_date
        totals[session_key] = totals.get(session_key, 0.0) + r.value
        last_end = r.end_date if last_end is None else max(last_end, r.end_date)
    return totals
