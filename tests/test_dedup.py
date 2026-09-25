from pomona.dedup import (
    IntervalRecord,
    bucket_local_date,
    dedup_nonoverlapping,
    nightly_totals,
    sum_by_bucket,
)


def rec(start: int, end: int, value: float, local_date: str = "2026-01-01") -> IntervalRecord:
    return IntervalRecord(start_date=start, end_date=end, value=value, start_local_date=local_date)


class TestDedupNonoverlapping:
    def test_no_overlap_keeps_everything(self):
        records = [rec(0, 10, 1.0), rec(10, 20, 2.0), rec(20, 30, 3.0)]
        kept = dedup_nonoverlapping(records)
        assert kept == records

    def test_fully_duplicate_interval_from_a_second_source_is_dropped(self):
        # Same time window logged by two sources (e.g. iPhone + Watch both cover 0-10).
        a = rec(0, 10, 100.0)
        b = rec(0, 10, 90.0)
        kept = dedup_nonoverlapping([a, b])
        assert kept == [a]

    def test_partially_overlapping_interval_is_dropped_entirely_not_partially_credited(self):
        a = rec(0, 10, 50.0)
        b = rec(5, 20, 90.0)  # overlaps a's tail (5-10) but extends to 20
        kept = dedup_nonoverlapping([a, b])
        assert kept == [a]  # b is fully dropped, not credited for its 10-20 non-overlapping part

    def test_rejected_record_does_not_block_a_later_non_overlapping_record(self):
        # a: 0-10 (accepted). b: 5-20 (overlaps a, rejected). c: 15-25 (does NOT overlap a,
        # only overlaps the *rejected* b) -- c must still be accepted, since covered_until
        # should only ever be extended by records that were actually kept.
        a = rec(0, 10, 1.0)
        b = rec(5, 20, 2.0)
        c = rec(15, 25, 3.0)
        kept = dedup_nonoverlapping([a, b, c])
        assert kept == [a, c]

    def test_back_to_back_intervals_touching_at_the_boundary_are_not_overlapping(self):
        a = rec(0, 10, 1.0)
        b = rec(10, 20, 2.0)  # starts exactly where a ends
        kept = dedup_nonoverlapping([a, b])
        assert kept == [a, b]

    def test_result_is_order_independent(self):
        a = rec(0, 10, 1.0)
        b = rec(5, 15, 2.0)  # overlaps a
        c = rec(20, 30, 3.0)
        assert dedup_nonoverlapping([a, b, c]) == dedup_nonoverlapping([c, b, a])
        assert dedup_nonoverlapping([b, c, a]) == [a, c]

    def test_empty_input_returns_empty(self):
        assert dedup_nonoverlapping([]) == []


class TestBucketLocalDate:
    def test_day_bucket_is_unchanged(self):
        assert bucket_local_date("2026-08-13", "day") == "2026-08-13"

    def test_week_bucket_is_the_preceding_or_same_monday(self):
        # 2026-08-13 is a Thursday.
        assert bucket_local_date("2026-08-13", "week") == "2026-08-10"
        # A Monday maps to itself.
        assert bucket_local_date("2026-08-10", "week") == "2026-08-10"

    def test_month_bucket_is_the_first_of_the_month(self):
        assert bucket_local_date("2026-08-13", "month") == "2026-08-01"


class TestSumByBucket:
    def test_sums_values_within_the_same_bucket(self):
        records = [
            rec(0, 1, 10.0, "2026-08-13"),
            rec(1, 2, 5.0, "2026-08-13"),
            rec(2, 3, 7.0, "2026-08-14"),
        ]
        totals = sum_by_bucket(records, "day")
        assert totals == {"2026-08-13": 15.0, "2026-08-14": 7.0}

    def test_week_bucket_merges_multiple_days_into_one_key(self):
        records = [rec(0, 1, 10.0, "2026-08-10"), rec(1, 2, 5.0, "2026-08-13")]
        totals = sum_by_bucket(records, "week")
        assert totals == {"2026-08-10": 15.0}


H = 3600


class TestNightlyTotals:
    def test_night_crossing_midnight_stays_one_night(self):
        # 23:00-23:50 logged under 08-01, then 00:00-07:00 under 08-02: one session.
        segments = [
            rec(23 * H, 23 * H + 50 * 60, 50 * 60, "2026-08-01"),
            rec(24 * H, 31 * H, 7 * H, "2026-08-02"),
        ]
        assert nightly_totals(segments) == {"2026-08-01": 7 * H + 50 * 60}

    def test_consecutive_nights_are_separate(self):
        day = 24 * H
        segments = [
            rec(23 * H, 30 * H, 7 * H, "2026-08-01"),
            rec(day + 23 * H, day + 29 * H, 6 * H, "2026-08-02"),
        ]
        assert nightly_totals(segments) == {"2026-08-01": 7 * H, "2026-08-02": 6 * H}

    def test_sessions_far_apart_on_same_date_both_count(self):
        # An afternoon nap and a late-evening start on the same local date.
        segments = [
            rec(13 * H, 14 * H, 1 * H, "2026-08-01"),
            rec(22 * H, 23 * H, 1 * H, "2026-08-01"),
        ]
        assert nightly_totals(segments) == {"2026-08-01": 2 * H}

    def test_empty(self):
        assert nightly_totals([]) == {}
