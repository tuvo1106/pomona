from datetime import datetime, timedelta, timezone

import pytest

from pomona import db as db_module
from pomona.api import dashboard
from pomona.clinical import INGESTED_RESOURCE_TYPES
from tests.conftest import checkpoint_and_close


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

    def test_invalid_bucket_returns_400(self, client):
        response = client.get(
            "/api/metrics/HKQuantityTypeIdentifierStepCount/timeseries?bucket=year"
        )
        assert response.status_code == 400

    def test_unit_is_the_most_common_one_within_the_requested_window(self, client, seeded_db_path):
        # A metric's unit can change over time (weight logged in lb, then kg). The label
        # must describe the window actually plotted, not whichever row SQLite happened to
        # reach first across all of history.
        conn = db_module.connect(seeded_db_path, isolation_level=None)
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
        checkpoint_and_close(conn)

        base = "/api/metrics/HKQuantityTypeIdentifierBodyMass/timeseries"
        assert client.get(f"{base}?start=2026-01-01&end=2026-12-31").json()["unit"] == "kg"
        assert client.get(f"{base}?start=2020-01-01&end=2020-12-31").json()["unit"] == "lb"
        # Unbounded: lb wins on count, rather than being an arbitrary pick.
        assert client.get(base).json()["unit"] == "lb"


class TestWorkouts:
    def test_returns_the_seeded_workouts(self, client):
        response = client.get("/api/workouts")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        cycling = next(w for w in body if w["activity_type"] == "HKWorkoutActivityTypeCycling")
        assert cycling["total_energy_burned"] == 420.0

    def test_activity_type_filter(self, client):
        response = client.get("/api/workouts?activity_type=HKWorkoutActivityTypeRunning")
        body = response.json()
        assert len(body) == 1
        # Modern (statistics-only) workout: energy/distance backfilled from
        # WorkoutStatistics children, not inline attributes.
        assert body[0]["total_energy_burned"] == 310.5
        assert body[0]["total_distance"] == 3.1

    def test_limit_paginates(self, client):
        assert len(client.get("/api/workouts?limit=1").json()) == 1

    def test_negative_limit_is_rejected_rather_than_returning_everything(self, client):
        # SQLite treats a negative LIMIT as unbounded, so this must be refused at the
        # boundary instead of quietly defeating pagination.
        assert client.get("/api/workouts?limit=-1").status_code == 422
        assert client.get("/api/workouts?limit=0").status_code == 422
        assert client.get("/api/workouts?limit=100000").status_code == 422
        assert client.get("/api/workouts?offset=-1").status_code == 422


class TestWorkoutsSummary:
    def test_groups_by_activity_type(self, client):
        response = client.get("/api/workouts/summary")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        cycling = next(w for w in body if w["activity_type"] == "HKWorkoutActivityTypeCycling")
        assert cycling["count"] == 1
        assert cycling["total_distance"] == 15.2


class TestRoutes:
    def test_returns_every_route_with_points(self, client):
        response = client.get("/api/routes")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 3
        # Two routes share start_local_date 2026-08-01 (the single-segment one and the
        # paused/two-segment one below) -- distinguish by segment shape.
        matched = next(
            r for r in body if r["start_local_date"] == "2026-08-01" and len(r["segments"]) == 1
        )
        assert matched["activity_type"] == "HKWorkoutActivityTypeCycling"
        assert matched["workout_id"] is not None
        assert matched["segments"] == [
            [[37.7749, -122.4194], [37.7755, -122.4184], [37.7761, -122.4174]]
        ]

    def test_route_with_a_pause_has_two_disconnected_segments(self, client):
        response = client.get("/api/routes")
        paused = next(r for r in response.json() if len(r["segments"]) == 2)
        assert paused["activity_type"] == "HKWorkoutActivityTypeCycling"
        assert paused["segments"] == [
            [[37.8000, -122.5000], [37.8010, -122.5010]],
            [[37.9000, -122.6000], [37.9010, -122.6010]],
        ]

    def test_unmatched_route_has_null_workout_id_and_activity_type(self, client):
        response = client.get("/api/routes")
        unmatched = next(r for r in response.json() if r["start_local_date"] == "2019-01-01")
        assert unmatched["workout_id"] is None
        assert unmatched["activity_type"] is None

    def test_matched_route_carries_its_workout_distance_and_duration(self, client):
        response = client.get("/api/routes")
        matched = next(
            r
            for r in response.json()
            if r["start_local_date"] == "2026-08-01" and len(r["segments"]) == 1
        )
        assert matched["duration"] == 45.5
        assert matched["duration_unit"] == "min"
        assert matched["total_distance"] == 15.2
        assert matched["total_distance_unit"] == "km"

    def test_unmatched_route_has_no_distance_or_duration(self, client):
        """The join is a LEFT join, so these are null rather than 0 -- an unknown distance
        must not arrive as a number the page would render as a real measurement.
        """
        response = client.get("/api/routes")
        unmatched = next(r for r in response.json() if r["start_local_date"] == "2019-01-01")
        assert unmatched["duration"] is None
        assert unmatched["duration_unit"] is None
        assert unmatched["total_distance"] is None
        assert unmatched["total_distance_unit"] is None

    def test_two_routes_matched_to_one_workout_both_carry_its_stats(self, client):
        """A paused workout can export as more than one route file, and the loader matches
        each to the same `workouts` row -- so the stats are the workout's, repeated, not a
        share of it split between the tracks.
        """
        matched = [r for r in client.get("/api/routes").json() if r["workout_id"] is not None]
        assert len(matched) == 2
        assert {r["workout_id"] for r in matched} == {1}
        assert all(r["total_distance"] == 15.2 and r["duration"] == 45.5 for r in matched)

    def test_date_range_filter(self, client):
        response = client.get("/api/routes?start=2026-01-01")
        body = response.json()
        assert len(body) == 2
        assert all(r["start_local_date"] == "2026-08-01" for r in body)


class TestEcg:
    def test_list_returns_every_recording_without_samples(self, client):
        response = client.get("/api/ecg")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert "samples_json" not in body[0]
        assert "points" not in body[0]
        by_date = {row["recorded_local_date"]: row for row in body}
        assert by_date["2026-06-01"]["classification"] == "Sinus Rhythm"
        assert by_date["2026-06-15"]["classification"] == "Inconclusive"
        assert by_date["2026-06-15"]["symptoms"] == "Rapid Heartbeat"

    def test_list_ordered_most_recent_first(self, client):
        response = client.get("/api/ecg")
        body = response.json()
        assert [row["recorded_local_date"] for row in body] == ["2026-06-15", "2026-06-01"]

    def test_date_range_filter(self, client):
        response = client.get("/api/ecg?start=2026-06-10")
        body = response.json()
        assert len(body) == 1
        assert body[0]["recorded_local_date"] == "2026-06-15"

    def test_detail_returns_metadata_and_points(self, client):
        list_response = client.get("/api/ecg")
        recording_id = next(
            row["id"] for row in list_response.json() if row["recorded_local_date"] == "2026-06-01"
        )

        response = client.get(f"/api/ecg/{recording_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["classification"] == "Sinus Rhythm"
        assert body["lead"] == "Lead I"
        assert body["unit"] == "µV"
        assert body["sample_rate"] == 512.0
        assert body["sample_count"] == 250
        # 250 samples is under the default 2000-point cap, so this is a passthrough --
        # every sample comes back, in order, none dropped.
        assert len(body["points"]) == 250
        assert body["points"][0] == {"t": 0.0, "value": 999.0}

    def test_detail_downsamples_when_max_points_is_small(self, client):
        list_response = client.get("/api/ecg")
        recording_id = next(
            row["id"] for row in list_response.json() if row["recorded_local_date"] == "2026-06-01"
        )

        response = client.get(f"/api/ecg/{recording_id}?max_points=100")
        assert response.status_code == 200
        body = response.json()
        assert len(body["points"]) <= 100
        assert len(body["points"]) < 250  # actually reduced, not a passthrough
        # The spike at index 0 (999.0, far outside the 0.0-3.0 oscillation everywhere else)
        # must survive min/max-per-bucket decimation even though most samples are dropped.
        assert body["points"][0] == {"t": 0.0, "value": 999.0}

    def test_unknown_id_is_a_404(self, client):
        response = client.get("/api/ecg/999999")
        assert response.status_code == 404


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

    def test_invalid_mode_is_a_400(self, client):
        response = client.get(
            "/api/category-metrics/HKCategoryTypeIdentifierMindfulSession/timeseries?mode=bogus"
        )
        assert response.status_code == 400


class TestActivitySummary:
    def test_returns_both_seeded_days(self, client):
        response = client.get("/api/activity-summary")
        assert response.status_code == 200
        dates = [row["date"] for row in response.json()]
        assert dates == ["2026-08-01", "2026-08-02"]


class TestClinical:
    def test_lists_five_rows_from_the_seven_fixture_files(self, client):
        response = client.get("/api/clinical")
        assert response.status_code == 200
        body = response.json()
        # Seven fixture files, five rows: Patient and Procedure are both off the ingest
        # allowlist, so neither reaches the database (see clinical_loader).
        assert len(body) == 5
        assert all(row["resource_type"] != "Patient" for row in body)

    def test_excludes_types_off_the_allowlist_even_from_a_stale_database(
        self, client, seeded_db_path
    ):
        # A database built before a type left the ingest allowlist still holds those rows until
        # the next drop-and-reload. Written straight into the table for that reason: the loader
        # can no longer produce one, which is exactly why the endpoint has to defend itself.
        conn = db_module.connect(seeded_db_path, isolation_level=None)
        conn.execute(
            "INSERT INTO clinical_records (resource_id, resource_type, code_text, raw_json)"
            " VALUES ('stale-row', 'SomeUnservedType', 'whatever', '{}')"
        )
        checkpoint_and_close(conn)

        served = {row["resource_type"] for row in client.get("/api/clinical").json()}
        # Non-empty first: `served <= allowlist` is satisfied by the empty set, so on its own it
        # would also pass if /api/clinical returned nothing -- including if the allowlist shrank
        # to nothing, which makes the `IN ()` clause a syntax error and every request a 500.
        assert served, "/api/clinical returned no rows, so the exclusion below proves nothing"
        assert served <= INGESTED_RESOURCE_TYPES, served - INGESTED_RESOURCE_TYPES

        # Not even when asked for by name.
        assert client.get("/api/clinical?resource_type=SomeUnservedType").json() == []

    def test_resource_type_filter(self, client):
        response = client.get("/api/clinical?resource_type=Observation")
        body = response.json()
        assert len(body) == 1
        assert body[0]["code_text"] == "LDL CALCULATED"
        assert body[0]["value_num"] == 95
        assert body[0]["results"] is None

    def test_observation_includes_reference_range(self, client):
        body = client.get("/api/clinical?resource_type=Observation").json()
        assert body[0]["reference_range"] == {
            "low": 0,
            "high": 99,
            "unit": "mg/dL",
            "text": "0-99 mg/dL",
        }

    def test_non_observations_have_no_reference_range(self, client):
        body = client.get("/api/clinical").json()
        others = [row for row in body if row["resource_type"] != "Observation"]
        assert others
        assert all(row["reference_range"] is None for row in others)
        assert all("raw_json" not in row for row in body)


class TestReferenceRangeParsing:
    @pytest.mark.parametrize(
        ("resource", "expected"),
        [
            ({}, None),
            ({"referenceRange": []}, None),
            ({"referenceRange": [{}]}, None),
            (
                {"referenceRange": [{"text": "Negative"}]},
                {"low": None, "high": None, "unit": None, "text": "Negative"},
            ),
            (
                {"referenceRange": [{"low": {"value": 3.5, "unit": "g/dL"}}]},
                {"low": 3.5, "high": None, "unit": "g/dL", "text": None},
            ),
            (
                {"referenceRange": [{"high": {"value": "<200"}, "text": "<200"}]},
                {"low": None, "high": None, "unit": None, "text": "<200"},
            ),
            ({"referenceRange": [{"low": {"value": True}}]}, None),
            ({"referenceRange": {"low": {"value": 1}}}, None),
        ],
    )
    def test_flattens_first_range(self, resource, expected):
        assert dashboard._reference_range(resource) == expected

    def test_malformed_json_is_none(self):
        # Both range and component parsing go through _resource, which is where a stored
        # payload that isn't a JSON object stops being anyone's problem.
        assert dashboard._resource("not json") is None
        assert dashboard._resource("[]") is None
        assert dashboard._resource(None) is None
        assert dashboard._reference_range(None) is None

    def test_diagnostic_report_includes_resolved_results(self, client):
        response = client.get("/api/clinical?resource_type=DiagnosticReport")
        body = response.json()
        assert len(body) == 1
        assert body[0]["results"] == [
            {
                "display": None,
                "code_text": "LDL CALCULATED",
                "value_num": 95,
                "value_unit": "mg/dL",
                "value_text": None,
                "status": "final",
            }
        ]


# Invented readings, not anyone's: a textbook 120/80 so the assertions read unambiguously.
SYSTOLIC_COMPONENT = {
    "code": {
        "text": "Systolic blood pressure",
        "coding": [
            {"system": "http://snomed.info/sct", "code": "271649006"},
            {"system": "http://loinc.org", "code": "8480-6", "display": "Systolic"},
        ],
    },
    "valueQuantity": {"value": 120, "unit": "mmHg"},
}

DIASTOLIC_COMPONENT = {
    "code": {
        "text": "Diastolic blood pressure",
        "coding": [{"system": "http://loinc.org", "code": "8462-4", "display": "Diastolic"}],
    },
    "valueQuantity": {"value": 80, "unit": "mmHg"},
}


def _panel(*components: dict) -> dict:
    return {
        "resourceType": "Observation",
        "id": "obs-panel",
        "status": "final",
        "code": {"text": "Blood pressure panel"},
        "effectiveDateTime": "2026-05-04T09:00:00Z",
        "component": list(components),
    }


class TestObservationComponents:
    def test_blood_pressure_panel_exposes_both_parts(self, clinical_client):
        client = clinical_client(_panel(SYSTOLIC_COMPONENT, DIASTOLIC_COMPONENT))
        body = client.get("/api/clinical").json()
        assert len(body) == 1
        # The row itself has no value -- that's the bug this fixes.
        assert body[0]["value_num"] is None
        assert body[0]["value_text"] is None
        assert body[0]["components"] == [
            {
                "label": "Systolic blood pressure",
                "code": "8480-6",
                "value_num": 120,
                "value_unit": "mmHg",
                "value_text": None,
                "reference_range": None,
            },
            {
                "label": "Diastolic blood pressure",
                "code": "8462-4",
                "value_num": 80,
                "value_unit": "mmHg",
                "value_text": None,
                "reference_range": None,
            },
        ]

    def test_parts_are_identified_by_code_when_diastolic_comes_first(self, clinical_client):
        # FHIR puts no order on component[], so the codes -- not the positions -- have to
        # carry which part is which.
        client = clinical_client(_panel(DIASTOLIC_COMPONENT, SYSTOLIC_COMPONENT))
        components = client.get("/api/clinical").json()[0]["components"]
        by_code = {c["code"]: c["value_num"] for c in components}
        assert by_code == {"8462-4": 80, "8480-6": 120}

    def test_a_third_part_is_returned_rather_than_dropped(self, clinical_client):
        # The page only collapses a panel to one reading when it is exactly the pair; an
        # extra part has to reach it so it can fall back to the labelled list.
        mean = {
            "code": {"text": "Mean blood pressure"},
            "valueQuantity": {"value": 93, "unit": "mm[Hg]"},
        }
        client = clinical_client(_panel(SYSTOLIC_COMPONENT, DIASTOLIC_COMPONENT, mean))
        components = client.get("/api/clinical").json()[0]["components"]
        assert [c["label"] for c in components] == [
            "Systolic blood pressure",
            "Diastolic blood pressure",
            "Mean blood pressure",
        ]

    def test_a_record_with_both_a_value_and_components_keeps_both(self, clinical_client):
        panel = _panel(SYSTOLIC_COMPONENT, DIASTOLIC_COMPONENT)
        panel["valueQuantity"] = {"value": 5, "unit": "kg"}
        body = clinical_client(panel).get("/api/clinical").json()
        assert body[0]["value_num"] == 5
        assert len(body[0]["components"]) == 2

    def test_ordinary_observation_has_no_components(self, client):
        body = client.get("/api/clinical?resource_type=Observation").json()
        assert body[0]["value_num"] == 95
        assert body[0]["components"] is None

    def test_non_observations_have_no_components(self, client):
        body = client.get("/api/clinical").json()
        others = [row for row in body if row["resource_type"] != "Observation"]
        assert others
        assert all(row["components"] is None for row in others)

    def test_component_reference_range_and_text_value(self, clinical_client):
        client = clinical_client(
            _panel(
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "1111-1"}]},
                    "valueQuantity": {"value": 7, "unit": "mmol/L"},
                    "referenceRange": [
                        {"low": {"value": 4, "unit": "mmol/L"}, "high": {"value": 6}}
                    ],
                },
                {"code": {"text": "Interpretation"}, "valueString": "Within expected limits"},
            )
        )
        components = client.get("/api/clinical").json()[0]["components"]
        assert components[0]["label"] is None
        assert components[0]["reference_range"] == {
            "low": 4,
            "high": 6,
            "unit": "mmol/L",
            "text": None,
        }
        assert components[1] == {
            "label": "Interpretation",
            "code": None,
            "value_num": None,
            "value_unit": None,
            "value_text": "Within expected limits",
            "reference_range": None,
        }

    def test_label_falls_back_to_a_coding_display(self, clinical_client):
        client = clinical_client(
            _panel(
                {"code": SYSTOLIC_COMPONENT["code"] | {"text": ""}, "valueQuantity": {"value": 1}}
            )
        )
        components = client.get("/api/clinical").json()[0]["components"]
        assert components[0]["label"] == "Systolic"
        assert components[0]["value_unit"] is None

    def test_loinc_code_is_read_from_the_oid_spelling_of_the_system(self, clinical_client):
        # Older interfaces identify LOINC by OID rather than by its URL; both name the same
        # code system, and the page needs the code to recognise a blood pressure.
        oid_systolic = {
            "code": {
                "text": "Systolic blood pressure",
                "coding": [{"system": "urn:oid:2.16.840.1.113883.6.1", "code": "8480-6"}],
            },
            "valueQuantity": {"value": 120, "unit": "mm[Hg]"},
        }
        client = clinical_client(_panel(oid_systolic, DIASTOLIC_COMPONENT))
        components = client.get("/api/clinical").json()[0]["components"]
        assert components[0]["code"] == "8480-6"

    def test_a_malformed_panel_does_not_break_the_endpoint(self, clinical_client):
        client = clinical_client(
            _panel(
                "not an object",
                {"code": "not an object", "valueQuantity": {"value": True}},
                # A non-list `coding` is iterated over if it isn't guarded, which would
                # raise out of the flattener and 500 the whole clinical page.
                {"code": {"coding": 7}, "valueQuantity": {"value": True}},
                {"code": {"text": "Kept"}, "valueQuantity": {"value": 2, "unit": "kg"}},
            )
        )
        response = client.get("/api/clinical")
        assert response.status_code == 200
        # The three unusable entries are dropped; the last still renders.
        assert response.json()[0]["components"] == [
            {
                "label": "Kept",
                "code": None,
                "value_num": 2,
                "value_unit": "kg",
                "value_text": None,
                "reference_range": None,
            }
        ]

    @pytest.mark.parametrize(
        "resource",
        [
            {},
            {"component": []},
            {"component": {}},
            {"component": "systolic"},
            {"component": [{}]},
            {"component": [{"code": {}, "valueQuantity": {"value": None}}]},
            {"component": [{"code": {"coding": 7}}]},
        ],
    )
    def test_shapes_with_nothing_to_show_are_none(self, resource):
        assert dashboard._components(resource) is None

    def test_an_unparseable_resource_is_none(self):
        assert dashboard._components(dashboard._resource("not json")) is None
        assert dashboard._components(None) is None


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

        conn = db_module.connect(seeded_db_path, isolation_level=None)
        conn.executemany(
            "INSERT INTO records (type, value_text, start_date, end_date, start_local_date) "
            "VALUES ('HKCategoryTypeIdentifierSleepAnalysis', "
            "'HKCategoryValueSleepAnalysisAsleepCore', ?, ?, ?)",
            [
                (epoch(30, 22), epoch(31, 0), "2026-07-30"),
                (epoch(31, 0), epoch(31, 6), "2026-07-31"),
            ],
        )
        checkpoint_and_close(conn)

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
        conn = db_module.connect(seeded_db_path, isolation_level=None)
        # Deliberately not the live answer (2026-03-10), so a still-present comparison
        # proves the stored key was read rather than the full-scan query.
        conn.executemany(
            "INSERT INTO ingest_meta (key, value) VALUES (?, ?)",
            [("earliest_date", "2026-01-01"), ("latest_date", "2026-08-10")],
        )
        checkpoint_and_close(conn)
        body = client.get("/api/overview?start=2026-03-10&end=2026-03-20").json()
        assert body["previous"] is not None

    def test_malformed_or_inverted_range_skips_the_comparison_instead_of_failing(self, client):
        inverted = client.get("/api/overview?start=2026-08-10&end=2026-08-01")
        assert inverted.status_code == 200
        assert inverted.json()["previous"] is None
        malformed = client.get("/api/overview?start=2026-8-1&end=soon")
        assert malformed.status_code == 200
        assert malformed.json()["previous"] is None


class TestMeta:
    # The seeded fixture is built with the loaders directly, not `pomona ingest`, so
    # ingest_meta has no `latest_date` key -- the tests up to the stored-key ones below all
    # exercise the live fallback a pre-existing database gets.

    def test_stored_latest_date_is_returned_instead_of_computing_it_live(
        self, client, seeded_db_path
    ):
        conn = db_module.connect(seeded_db_path, isolation_level=None)
        # Deliberately not the live answer (2026-08-10), so getting it back proves the
        # stored key was used rather than the full-scan query.
        conn.execute("INSERT INTO ingest_meta (key, value) VALUES ('latest_date', '2030-01-01')")
        checkpoint_and_close(conn)
        assert client.get("/api/meta").json()["latest_date"] == "2030-01-01"

    def test_stored_empty_latest_date_is_null_not_a_live_fallback(self, client, seeded_db_path):
        # Ingest stores "" when there was no dated data. That's a real answer, not a missing
        # key, so it must not fall back to the live query (which here would find data).
        conn = db_module.connect(seeded_db_path, isolation_level=None)
        conn.execute("INSERT INTO ingest_meta (key, value) VALUES ('latest_date', '')")
        checkpoint_and_close(conn)
        assert client.get("/api/meta").json()["latest_date"] is None

    def test_a_workout_newer_than_every_record_sets_latest_date(self, client):
        response = client.get("/api/meta")
        assert response.status_code == 200
        # The newest <Record> in sample_export.xml is on 2026-08-05, but a <Workout> is on
        # 2026-08-10. Anchoring on records alone would leave that workout outside every
        # relative range.
        assert response.json()["latest_date"] == "2026-08-10"

    def test_latest_date_is_the_newest_record_when_records_are_newest(self, client, seeded_db_path):
        conn = db_module.connect(seeded_db_path, isolation_level=None)
        conn.execute(
            "INSERT INTO records (type, value_num, unit, start_date, end_date, start_local_date) "
            "VALUES ('HKQuantityTypeIdentifierStepCount', 10, 'count', 0, 0, '2026-08-15')"
        )
        checkpoint_and_close(conn)
        assert client.get("/api/meta").json()["latest_date"] == "2026-08-15"

    def test_an_ecg_newer_than_everything_else_sets_latest_date(self, client, seeded_db_path):
        conn = db_module.connect(seeded_db_path, isolation_level=None)
        # recorded_date (the indexed epoch) is what picks the newest recording; its
        # recorded_local_date is what's reported.
        conn.execute(
            "INSERT INTO ecg_recordings (recorded_date, recorded_local_date, sample_rate, "
            "sample_count, samples_json, source_file) "
            "VALUES (1787000000, '2026-08-17', 512, 0, '[]', 'ecg_2026-08-17.csv')"
        )
        checkpoint_and_close(conn)
        assert client.get("/api/meta").json()["latest_date"] == "2026-08-17"

    def test_ingested_at_is_null_when_ingest_never_wrote_it(self, client):
        # The fixture is built with the loaders directly, not `pomona ingest`, so
        # ingest_meta is empty -- that must read as null, not fail.
        assert client.get("/api/meta").json()["ingested_at"] is None

    def test_ingested_at_is_read_from_ingest_meta_as_an_epoch(self, client, seeded_db_path):
        conn = db_module.connect(seeded_db_path, isolation_level=None)
        conn.execute("INSERT INTO ingest_meta (key, value) VALUES ('ingested_at', '1787242117')")
        checkpoint_and_close(conn)
        assert client.get("/api/meta").json()["ingested_at"] == 1787242117

    def test_empty_tables_return_null_latest_date(self, client, seeded_db_path):
        conn = db_module.connect(seeded_db_path, isolation_level=None)
        for table in ("records", "workouts", "ecg_recordings"):
            conn.execute(f"DELETE FROM {table}")
        checkpoint_and_close(conn)
        assert client.get("/api/meta").json()["latest_date"] is None


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
        conn = db_module.connect(db_path, isolation_level=None)
        conn.executemany(
            "INSERT INTO records (type, value_num, unit, start_date, end_date, start_local_date) "
            "VALUES ('HKQuantityTypeIdentifierStepCount', 100, 'count', ?, ?, ?)",
            # Distinct, non-overlapping epochs so dedup keeps every row.
            [(i * 1000, i * 1000 + 10, d) for i, d in enumerate(local_dates, start=1)],
        )
        checkpoint_and_close(conn)

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
        conn = db_module.connect(seeded_db_path, isolation_level=None)
        conn.executemany(
            "INSERT INTO ingest_meta (key, value) VALUES (?, ?)",
            [("earliest_date", "2026-03-10"), ("latest_date", "2026-08-05")],
        )
        checkpoint_and_close(conn)
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
        conn = db_module.connect(seeded_db_path, isolation_level=None)
        conn.execute("INSERT INTO ingest_meta (key, value) VALUES ('ingested_at', '1')")
        checkpoint_and_close(conn)
        assert self._partial(client.get(f"{self.STEPS}?bucket=day"))["2026-08-05"] is None

        self._add_steps(seeded_db_path, "2026-08-20")
        # Same ingest identity: still the cached newest date (08-10), so the 08-20 point reads
        # as past the data's end rather than as the day in progress.
        assert self._partial(client.get(f"{self.STEPS}?bucket=day"))["2026-08-20"] == "truncated"

        conn = db_module.connect(seeded_db_path, isolation_level=None)
        conn.execute("UPDATE ingest_meta SET value = '2' WHERE key = 'ingested_at'")
        checkpoint_and_close(conn)
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
        assert dashboard._bucket_last_day(first_day, bucket).isoformat() == last
