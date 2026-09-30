from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import writing


class TestOverview:
    def test_returns_the_expected_shape(self, client):
        response = client.get("/api/overview")
        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) == {
            "date_range",
            "avg_daily_steps",
            "avg_weight",
            "avg_resting_hr",
            "workout_count",
            "avg_vo2_max",
            "avg_sleep_hours",
            "avg_blood_pressure",
            "avg_hrv",
            "previous_range",
            "previous",
            "previous_withheld",
        }
        # No BodyMass, RestingHeartRate, VO2Max, or HRV records in the fixture.
        assert body["avg_weight"] is None
        assert body["avg_resting_hr"] is None
        assert body["avg_vo2_max"] is None
        assert body["avg_hrv"] is None

    def test_avg_daily_steps_averages_the_per_day_totals_not_raw_records(self, client):
        # Fixture: 2026-08-01 totals 579 (123+456), 2026-03-10 totals 789,
        # 2026-08-05 dedups to 1300 (see the overlapping-source test) -> avg of the 3 days.
        response = client.get("/api/overview")
        assert response.json()["avg_daily_steps"] == pytest.approx((579.0 + 789.0 + 1300.0) / 3)

    def test_workout_count_and_sleep_and_blood_pressure_from_fixture(self, client):
        body = client.get("/api/overview").json()
        assert body["workout_count"] == 2
        # Average of the two nightly (dedup'd) totals: 2026-08-01 (7.5h) and 2026-08-05 (3.5h).
        assert body["avg_sleep_hours"] == pytest.approx((7.5 + 3.5) / 2)
        assert body["avg_blood_pressure"] == {"systolic": 118.0, "diastolic": 76.0}

    def test_date_range_is_echoed_back(self, client):
        response = client.get("/api/overview?start=2026-08-01&end=2026-08-31")
        body = response.json()
        assert body["date_range"] == {"start": "2026-08-01", "end": "2026-08-31"}
        # 2026-08-01 (579) and 2026-08-05 (dedups to 1300) fall in this range.
        assert body["avg_daily_steps"] == 939.5

    def test_no_workouts_in_range_returns_zero_not_null(self, client):
        response = client.get("/api/overview?start=2020-01-01&end=2020-01-31")
        assert response.json()["workout_count"] == 0

    def test_unbounded_range_has_no_previous_period(self, client):
        body = client.get("/api/overview").json()
        assert body["previous_range"] is None
        assert body["previous"] is None
        # Nothing was withheld: there's simply no previous period to compare with.
        assert body["previous_withheld"] is None
        # A half-filled custom range is unbounded on one side, so no comparison either.
        body = client.get("/api/overview?start=2026-08-01").json()
        assert body["previous"] is None

    def test_previous_period_is_the_equal_length_window_just_before(self, client):
        # 6 days, 2026-08-05..10 -> previous is the 6 days 2026-07-30..08-04.
        body = client.get("/api/overview?start=2026-08-05&end=2026-08-10").json()
        assert body["previous_range"] == {"start": "2026-07-30", "end": "2026-08-04"}

        # Current window: 08-05 steps (dedup'd to 1300), the 08-10 run, the 08-05 night (3.5h).
        assert body["avg_daily_steps"] == 1300.0
        assert body["workout_count"] == 1
        assert body["avg_sleep_hours"] == pytest.approx(3.5)
        assert body["avg_blood_pressure"] is None

        # Previous window: 08-01 steps (579), the 08-01 ride, the 08-01 night (7.5h), 08-01 BP.
        previous = body["previous"]
        assert previous["avg_daily_steps"] == 579.0
        assert previous["workout_count"] == 1
        assert previous["avg_sleep_hours"] == pytest.approx(7.5)
        assert previous["avg_blood_pressure"] == {"systolic": 118.0, "diastolic": 76.0}
        assert body["previous_withheld"] is None
        # The nested stats don't repeat the range bookkeeping.
        assert "date_range" not in previous
        assert "previous" not in previous

    def test_previous_period_sleep_groups_nights_like_the_current_period(
        self, client, seeded_db_path
    ):
        # One synthetic night inside the previous window (2026-07-30..08-04), logged as two
        # segments split at local midnight: 22:00-24:00 on 07-30 and 00:00-06:00 on 07-31
        # (UTC-7). Keyed per segment it would count as two short nights (2h and 6h); grouped
        # into a session (nightly_totals, as the current period is) it's one 8h night on 07-30.
        pdt = timezone(timedelta(hours=-7))

        def epoch(day: int, hour: int) -> int:
            return int(datetime(2026, 7, day, hour, tzinfo=pdt).timestamp())

        with writing(seeded_db_path) as conn:
            conn.executemany(
                "INSERT INTO records (type, value_text, start_date, end_date, start_local_date) "
                "VALUES ('HKCategoryTypeIdentifierSleepAnalysis', "
                "'HKCategoryValueSleepAnalysisAsleepCore', ?, ?, ?)",
                [
                    (epoch(30, 22), epoch(31, 0), "2026-07-30"),
                    (epoch(31, 0), epoch(31, 6), "2026-07-31"),
                ],
            )

        body = client.get("/api/overview?start=2026-08-05&end=2026-08-10").json()
        assert body["previous_range"] == {"start": "2026-07-30", "end": "2026-08-04"}
        # Two nights, 8h (07-30) and the fixture's 7.5h (08-01), not three (2h, 6h, 7.5h).
        assert body["previous"]["avg_sleep_hours"] == pytest.approx((8.0 + 7.5) / 2)
        # The current window is computed the same way, so the delta compares like with like.
        assert body["avg_sleep_hours"] == pytest.approx(3.5)

    def test_single_day_range_compares_against_the_day_before(self, client):
        body = client.get("/api/overview?start=2026-08-02&end=2026-08-02").json()
        assert body["previous_range"] == {"start": "2026-08-01", "end": "2026-08-01"}
        assert body["previous"]["avg_daily_steps"] == 579.0

    def test_no_comparison_when_the_previous_window_starts_before_the_oldest_data(self, client):
        # The fixture's oldest data is 2026-03-10. Previous window here: 2026-02-27..03-09,
        # entirely before it -- workout_count would be 0 there (a count, never null), which
        # would read as growth. The range is still returned so the UI can say why.
        body = client.get("/api/overview?start=2026-03-10&end=2026-03-20").json()
        assert body["previous_range"] == {"start": "2026-02-27", "end": "2026-03-09"}
        assert body["previous"] is None
        assert body["previous_withheld"] == "before_data"

        # Partly before it counts too: 2026-03-05..03-15 -> previous 02-22..03-04.
        body = client.get("/api/overview?start=2026-03-05&end=2026-03-15").json()
        assert body["previous"] is None
        assert body["previous_withheld"] == "before_data"

    def test_no_comparison_for_a_single_day_on_the_newest_data_date(self, client):
        # 2026-08-10 is the fixture's newest data date (its workout), usually a day still in
        # progress when exported, so comparing it with a full day would mislead.
        body = client.get("/api/overview?start=2026-08-10&end=2026-08-10").json()
        assert body["previous_range"] == {"start": "2026-08-09", "end": "2026-08-09"}
        assert body["previous"] is None
        assert body["previous_withheld"] == "partial_day"

    def test_stored_data_span_is_used_instead_of_computing_it_live(self, client, seeded_db_path):
        with writing(seeded_db_path) as conn:
            # Deliberately not the live answer (2026-03-10), so a still-present comparison
            # proves the stored key was read rather than the full-scan query.
            conn.executemany(
                "INSERT INTO ingest_meta (key, value) VALUES (?, ?)",
                [("earliest_date", "2026-01-01"), ("latest_date", "2026-08-10")],
            )
        body = client.get("/api/overview?start=2026-03-10&end=2026-03-20").json()
        assert body["previous"] is not None

    def test_malformed_or_inverted_range_skips_the_comparison_instead_of_failing(self, client):
        inverted = client.get("/api/overview?start=2026-08-10&end=2026-08-01")
        assert inverted.status_code == 200
        assert inverted.json()["previous"] is None
        malformed = client.get("/api/overview?start=2026-8-1&end=soon")
        assert malformed.status_code == 200
        assert malformed.json()["previous"] is None
