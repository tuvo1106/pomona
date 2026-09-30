from datetime import datetime

import pytest

from pomona.api import query
from tests.conftest import writing


class TestPartialBuckets:
    """Cumulative series mark buckets that only cover part of their period.

    The seeded fixture's newest data date is 2026-08-10 (a workout, see TestMeta), and it has
    no `latest_date` in ingest_meta, so these exercise the live fallback unless a test stores
    one. Step counts are synthetic; only their dates matter here.
    """

    STEPS = "/api/metrics/HKQuantityTypeIdentifierStepCount/timeseries"
    MINDFUL = "/api/category-metrics/HKCategoryTypeIdentifierMindfulSession/timeseries"

    @staticmethod
    def _add_steps(db_path, *local_dates):
        with writing(db_path) as conn:
            conn.executemany(
                "INSERT INTO records "
                "(type, value_num, unit, start_date, end_date, start_local_date) "
                "VALUES ('HKQuantityTypeIdentifierStepCount', 100, 'count', ?, ?, ?)",
                # Distinct, non-overlapping epochs so dedup keeps every row.
                [(i * 1000, i * 1000 + 10, d) for i, d in enumerate(local_dates, start=1)],
            )

    @staticmethod
    def _partial(response) -> dict:
        assert response.status_code == 200
        return {p["date"]: p["partial"] for p in response.json()["points"]}

    def test_daily_point_on_the_newest_data_date_is_in_progress(self, client, seeded_db_path):
        self._add_steps(seeded_db_path, "2026-08-10")
        partial = self._partial(client.get(f"{self.STEPS}?bucket=day"))
        assert partial["2026-08-10"] == "in_progress"
        assert partial["2026-08-05"] is None
        assert partial["2026-08-01"] is None

    def test_week_that_starts_before_the_range_is_truncated(self, client, seeded_db_path):
        self._add_steps(seeded_db_path, "2026-08-10")
        # 2026-08-05 is a Wednesday, so its week (from Monday 08-03) begins before `start`.
        partial = self._partial(client.get(f"{self.STEPS}?bucket=week&start=2026-08-05"))
        assert partial == {"2026-08-03": "truncated", "2026-08-10": "in_progress"}

    def test_week_cut_off_by_a_custom_range_end_is_truncated(self, client):
        # The week of 08-03 runs to 08-09, past `end`; the week of 07-27 ends 08-02 and is
        # whole.
        partial = self._partial(
            client.get(f"{self.STEPS}?bucket=week&start=2026-07-27&end=2026-08-05")
        )
        assert partial == {"2026-07-27": None, "2026-08-03": "truncated"}

    def test_complete_week_before_the_newest_date_is_not_partial(self, client, seeded_db_path):
        # Steps through the export's newest date, so nothing cuts this series short early.
        self._add_steps(seeded_db_path, "2026-08-10")
        # Unbounded range: the week of 08-03 ends 08-09, before the newest date (08-10).
        partial = self._partial(client.get(f"{self.STEPS}?bucket=week"))
        assert partial["2026-08-03"] is None

    def test_month_containing_the_newest_date_is_in_progress(self, client, seeded_db_path):
        self._add_steps(seeded_db_path, "2026-08-10")
        partial = self._partial(client.get(f"{self.STEPS}?bucket=month"))
        # March is cut short by where the data itself begins (2026-03-10), not by a range
        # bound -- an all-time range sends no `start`, so only `earliest` catches it.
        assert partial == {"2026-03-01": "truncated", "2026-08-01": "in_progress"}

    def test_bucket_before_the_first_day_with_data_is_truncated(self, client, seeded_db_path):
        self._add_steps(seeded_db_path, "2026-08-10")
        # The fixture's first record is 2026-03-10, so the week from Monday 03-09 holds one
        # day of data out of seven and dips like any other partial bucket.
        partial = self._partial(client.get(f"{self.STEPS}?bucket=week"))
        assert partial["2026-03-09"] == "truncated"

    def test_range_end_cutting_the_newest_bucket_wins_over_in_progress(self, client):
        # The month holds the newest data date (08-10), but it is short because the range
        # ends on the 5th -- "In progress" would be the wrong caption for that.
        partial = self._partial(
            client.get(f"{self.STEPS}?bucket=month&start=2026-08-01&end=2026-08-05")
        )
        assert partial["2026-08-01"] == "truncated"

    def test_series_that_stopped_before_the_export_end_is_not_marked(self, client):
        # Step counts stop on 08-05 while the export runs to 08-10 (a workout). The bounds
        # are the export's, not the series': a metric's own last record can't tell "stopped
        # logging" from "logs weekly", and marking the latter's final bucket would dash a
        # week that is complete and representative.
        partial = self._partial(client.get(f"{self.STEPS}?bucket=week"))
        assert partial["2026-08-03"] is None

    def test_preset_range_ending_on_the_newest_date_still_reads_in_progress(
        self, client, seeded_db_path
    ):
        # The frontend's preset ranges send end == the newest data date, so an `end` that
        # only "cuts" the bucket because the data stops there must not caption it as
        # truncated -- that is the week/month case UI-02 is about.
        self._add_steps(seeded_db_path, "2026-08-10")
        partial = self._partial(
            client.get(f"{self.STEPS}?bucket=week&start=2026-07-13&end=2026-08-10")
        )
        assert partial["2026-08-10"] == "in_progress"
        monthly = self._partial(
            client.get(f"{self.STEPS}?bucket=month&start=2026-03-01&end=2026-08-10")
        )
        assert monthly["2026-08-01"] == "in_progress"

    def test_avg_mode_series_are_never_marked(self, client):
        # An average over part of a period is still a fair average.
        body = client.get(
            "/api/metrics/HKQuantityTypeIdentifierHeartRate/timeseries?bucket=month"
        ).json()
        assert body["aggregation_mode"] == "avg"
        assert body["points"]
        assert all(p["partial"] is None for p in body["points"])

    def test_category_series_are_marked_like_sums(self, client):
        truncated = self._partial(
            client.get(f"{self.MINDFUL}?mode=count&bucket=week&start=2026-07-29")
        )
        assert truncated == {"2026-07-27": "truncated"}
        # August holds the export's newest date, so it is in progress even though this
        # series' own last session is earlier in the month: the month still has time to run.
        # Bounds come from the export, not the series -- see
        # test_series_that_stopped_before_the_export_end_is_not_marked.
        in_progress = self._partial(client.get(f"{self.MINDFUL}?mode=duration&bucket=month"))
        assert in_progress["2026-08-01"] == "in_progress"

    def test_sleep_points_carry_no_partial_flag(self, client):
        # Week/month sleep points are per-night averages and a daily point is one whole
        # night, so a partial period doesn't drag them down the way it drags a sum.
        for bucket in ("day", "week", "month"):
            points = client.get(f"/api/sleep?bucket={bucket}").json()["points"]
            assert points
            assert all("partial" not in p for p in points)

    def test_stored_latest_date_drives_in_progress(self, client, seeded_db_path):
        with writing(seeded_db_path) as conn:
            conn.executemany(
                "INSERT INTO ingest_meta (key, value) VALUES (?, ?)",
                [("earliest_date", "2026-03-10"), ("latest_date", "2026-08-05")],
            )
        # Not the live answer (08-10), so this proves the stored key was used.
        partial = self._partial(client.get(f"{self.STEPS}?bucket=day"))
        assert partial["2026-08-05"] == "in_progress"

    def test_malformed_range_param_skips_that_bound_instead_of_failing(
        self, client, seeded_db_path
    ):
        # A malformed `end` still filters in SQL (every date sorts before "n"), so the points
        # come back; marking ignores the unusable bound and falls back to the newest date.
        self._add_steps(seeded_db_path, "2026-08-10")
        partial = self._partial(client.get(f"{self.STEPS}?bucket=week&end=not-a-date"))
        assert partial["2026-08-03"] is None
        assert partial["2026-07-27"] is None

    def test_live_span_is_cached_per_ingest(self, client, seeded_db_path):
        # A database from `pomona ingest` that predates the stored span keys: the live
        # result is cached against its ingested_at, and a new ingest (new ingested_at) misses.
        with writing(seeded_db_path) as conn:
            conn.execute("INSERT INTO ingest_meta (key, value) VALUES ('ingested_at', '1')")
        assert self._partial(client.get(f"{self.STEPS}?bucket=day"))["2026-08-05"] is None

        self._add_steps(seeded_db_path, "2026-08-20")
        # Same ingest identity: still the cached newest date (08-10), so the 08-20 point reads
        # as past the data's end rather than as the day in progress.
        assert self._partial(client.get(f"{self.STEPS}?bucket=day"))["2026-08-20"] == "truncated"

        with writing(seeded_db_path) as conn:
            conn.execute("UPDATE ingest_meta SET value = '2' WHERE key = 'ingested_at'")
        assert self._partial(client.get(f"{self.STEPS}?bucket=day"))["2026-08-20"] == "in_progress"


class TestBucketLastDay:
    @pytest.mark.parametrize(
        ("first", "bucket", "last"),
        [
            ("2026-08-10", "day", "2026-08-10"),
            ("2026-08-10", "week", "2026-08-16"),
            ("2026-02-01", "month", "2026-02-28"),
            ("2028-02-01", "month", "2028-02-29"),
            ("2026-12-01", "month", "2026-12-31"),
        ],
    )
    def test_last_day_of_bucket(self, first, bucket, last):
        first_day = datetime.fromisoformat(first).date()
        assert query.bucket_last_day(first_day, bucket).isoformat() == last
