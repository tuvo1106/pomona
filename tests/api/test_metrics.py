from tests.conftest import writing


class TestMetricTypes:
    def test_returns_a_row_per_distinct_type_with_counts(self, client):
        response = client.get("/api/metric-types")
        assert response.status_code == 200
        by_type = {row["type"]: row for row in response.json()}
        assert by_type["HKQuantityTypeIdentifierStepCount"]["count"] == 6
        assert by_type["HKQuantityTypeIdentifierHeartRate"]["count"] == 1
        assert by_type["HKQuantityTypeIdentifierBloodPressureSystolic"]["count"] == 1

    def test_date_range_excludes_types_with_no_data_in_that_window(self, client):
        # The +0100-offset StepCount record lands on 2026-03-10, the only data that far
        # back -- everything else in the fixture is 2026-08-01/02.
        response = client.get("/api/metric-types?start=2026-03-01&end=2026-03-31")
        types = {row["type"] for row in response.json()}
        assert types == {"HKQuantityTypeIdentifierStepCount"}


class TestMetricTimeseries:
    def test_sum_metric_buckets_and_sums_per_day(self, client):
        response = client.get(
            "/api/metrics/HKQuantityTypeIdentifierStepCount/timeseries?bucket=day"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["metric_type"] == "HKQuantityTypeIdentifierStepCount"
        assert body["unit"] == "count"
        assert body["aggregation_mode"] == "sum"
        points = {p["date"]: p["value"] for p in body["points"]}
        assert points["2026-08-01"] == 579.0  # 123 + 456
        assert points["2026-03-10"] == 789.0

    def test_sum_metric_deduplicates_overlapping_sources_per_day(self, client):
        # Fixture 2026-08-05: iPhone 08:00-08:10 (1000), Watch 08:05-08:15 (800, overlaps
        # -> dropped), Watch 09:00-09:10 (300, no overlap -> kept). Naive sum would be 2100.
        response = client.get(
            "/api/metrics/HKQuantityTypeIdentifierStepCount/timeseries?bucket=day"
        )
        points = {p["date"]: p["value"] for p in response.json()["points"]}
        assert points["2026-08-05"] == 1300.0

    def test_avg_metric_averages_per_day(self, client):
        response = client.get(
            "/api/metrics/HKQuantityTypeIdentifierHeartRate/timeseries?bucket=day"
        )
        body = response.json()
        assert body["aggregation_mode"] == "avg"
        points = {p["date"]: p["value"] for p in body["points"]}
        assert points["2026-08-01"] == 62.0

    def test_date_range_filter_excludes_points_outside_range(self, client):
        response = client.get(
            "/api/metrics/HKQuantityTypeIdentifierStepCount/timeseries"
            "?start=2026-08-01&end=2026-08-31"
        )
        dates = {p["date"] for p in response.json()["points"]}
        assert dates == {"2026-08-01", "2026-08-05"}

    def test_unknown_metric_type_returns_empty_points_not_an_error(self, client):
        response = client.get("/api/metrics/DoesNotExist/timeseries")
        assert response.status_code == 200
        assert response.json()["points"] == []

    def test_invalid_bucket_is_a_422(self, client):
        # Every endpoint that takes a bucket validates it the same way, from the annotation.
        for path in [
            "/api/metrics/HKQuantityTypeIdentifierStepCount/timeseries",
            "/api/sleep",
            "/api/blood-pressure",
            "/api/category-metrics/HKCategoryTypeIdentifierMindfulSession/timeseries?mode=count",
        ]:
            sep = "&" if "?" in path else "?"
            assert client.get(f"{path}{sep}bucket=year").status_code == 422, path

    def test_unit_is_the_most_common_one_within_the_requested_window(self, client, seeded_db_path):
        # A metric's unit can change over time (weight logged in lb, then kg). The label
        # must describe the window actually plotted, not whichever row SQLite happened to
        # reach first across all of history.
        with writing(seeded_db_path) as conn:
            conn.executemany(
                "INSERT INTO records "
                "(type, value_text, value_num, unit, start_date, end_date, start_local_date) "
                "VALUES ('HKQuantityTypeIdentifierBodyMass', ?, ?, ?, 0, 0, ?)",
                [
                    ("180", 180.0, "lb", "2020-01-01"),
                    ("179", 179.0, "lb", "2020-01-02"),
                    ("178", 178.0, "lb", "2020-01-03"),
                    ("80", 80.0, "kg", "2026-08-01"),
                ],
            )

        base = "/api/metrics/HKQuantityTypeIdentifierBodyMass/timeseries"
        assert client.get(f"{base}?start=2026-01-01&end=2026-12-31").json()["unit"] == "kg"
        assert client.get(f"{base}?start=2020-01-01&end=2020-12-31").json()["unit"] == "lb"
        # Unbounded: lb wins on count, rather than being an arbitrary pick.
        assert client.get(base).json()["unit"] == "lb"


class TestSleep:
    def test_returns_daily_asleep_hours(self, client):
        response = client.get("/api/sleep")
        assert response.status_code == 200
        points = {p["date"]: p["hours"] for p in response.json()["points"]}
        # 2026-08-01 23:00 -> 2026-08-02 06:30, bucketed under its own start_local_date.
        assert points["2026-08-01"] == 7.5

    def test_deduplicates_overlapping_sources_per_night(self, client):
        # Fixture 2026-08-05: iPhone 20:00-23:00 (3h), Watch 22:00-23:30 (1.5h, overlaps
        # -> dropped), Watch 23:00-23:30 (0.5h, no overlap -> kept). Naive sum would be 5h.
        response = client.get("/api/sleep")
        points = {p["date"]: p["hours"] for p in response.json()["points"]}
        assert points["2026-08-05"] == 3.5

    def test_date_range_filter(self, client):
        response = client.get("/api/sleep?start=2026-08-06")
        assert response.json()["points"] == []

    def test_month_bucket_is_average_night_not_sum(self, client):
        # Two nights in August: 7.5h (08-01) and 3.5h (08-05, after dedup). Summing would
        # report 11h for the month; the average night is 5.5h.
        response = client.get("/api/sleep?bucket=month")
        assert response.json()["points"] == [{"date": "2026-08-01", "hours": 5.5}]

    def test_week_bucket_averages_only_nights_in_that_week(self, client):
        # 08-01 is a Saturday (week of 07-27), 08-05 a Wednesday (week of 08-03): one night
        # each, so each week's average is just that night.
        response = client.get("/api/sleep?bucket=week")
        points = {p["date"]: p["hours"] for p in response.json()["points"]}
        assert points == {"2026-07-27": 7.5, "2026-08-03": 3.5}

    def test_month_average_matches_overview_avg_sleep(self, client):
        month = client.get("/api/sleep?bucket=month").json()["points"][0]["hours"]
        assert month == client.get("/api/overview").json()["avg_sleep_hours"]


class TestBloodPressure:
    def test_returns_daily_systolic_and_diastolic(self, client):
        response = client.get("/api/blood-pressure")
        assert response.status_code == 200
        points = response.json()["points"]
        assert len(points) == 1
        assert points[0]["date"] == "2026-08-01"
        assert points[0]["systolic"] == 118.0
        assert points[0]["diastolic"] == 76.0


class TestCategoryMetrics:
    def test_count_mode_counts_records_per_bucket(self, client):
        # Fixture has 2 Stood + 1 Idle apple-stand-hour records on 2026-08-01; unfiltered,
        # count mode reports all of them regardless of value.
        response = client.get(
            "/api/category-metrics/HKCategoryTypeIdentifierAppleStandHour/timeseries?mode=count"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["unit"] == "events"
        points = {p["date"]: p["value"] for p in body["points"]}
        assert points["2026-08-01"] == 3

    def test_value_prefix_filters_to_only_matching_values(self, client):
        # Apple logs a stand-hour record every checked hour whether or not the user actually
        # stood ('...Stood' vs '...Idle') -- value_prefix must exclude the Idle one.
        response = client.get(
            "/api/category-metrics/HKCategoryTypeIdentifierAppleStandHour/timeseries"
            "?mode=count&value_prefix=HKCategoryValueAppleStandHourStood"
        )
        assert response.status_code == 200
        points = {p["date"]: p["value"] for p in response.json()["points"]}
        assert points["2026-08-01"] == 2

    def test_duration_mode_sums_minutes_per_bucket(self, client):
        response = client.get(
            "/api/category-metrics/HKCategoryTypeIdentifierMindfulSession/timeseries?mode=duration"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["unit"] == "min"
        points = {p["date"]: p["value"] for p in body["points"]}
        assert points["2026-08-01"] == 20.0  # two 10-minute sessions

    def test_missing_mode_is_a_422(self, client):
        response = client.get(
            "/api/category-metrics/HKCategoryTypeIdentifierMindfulSession/timeseries"
        )
        assert response.status_code == 422

    def test_invalid_mode_is_a_422(self, client):
        response = client.get(
            "/api/category-metrics/HKCategoryTypeIdentifierMindfulSession/timeseries?mode=bogus"
        )
        assert response.status_code == 422


class TestActivitySummary:
    def test_returns_both_seeded_days(self, client):
        response = client.get("/api/activity-summary")
        assert response.status_code == 200
        dates = [row["date"] for row in response.json()]
        assert dates == ["2026-08-01", "2026-08-02"]
