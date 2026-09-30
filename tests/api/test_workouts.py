import pytest

from tests.conftest import writing


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


def _add_runs(db_path, runs):
    """Inserts (distance, unit, start_local_date) running workouts into a seeded database."""
    with writing(db_path) as conn:
        conn.executemany(
            "INSERT INTO workouts (activity_type, total_distance, total_distance_unit, "
            "start_date, end_date, start_local_date) VALUES (?, ?, ?, 0, 0, ?)",
            [("HKWorkoutActivityTypeRunning", *run) for run in runs],
        )


class TestRunningMileage:
    def test_totals_only_running(self, client):
        body = client.get("/api/workouts/running").json()
        # The fixture's cycling workout (15.2) is another sport and stays out.
        assert body["unit"] == "mi"
        assert body["runs"] == 1
        assert body["unmeasured_runs"] == 0
        assert body["total_distance"] == 3.1

    def test_months_span_the_range_clamped_to_the_data(self, client):
        # The range starts in January, but the fixture's data begins 2026-03-10: months
        # before it would be zeros meaning "no export", not "no runs".
        points = client.get("/api/workouts/running?start=2026-01-01&end=2026-08-10").json()[
            "points"
        ]
        assert [p["date"] for p in points] == [
            "2026-03-01",
            "2026-04-01",
            "2026-05-01",
            "2026-06-01",
            "2026-07-01",
            "2026-08-01",
        ]
        assert points[1] == {"date": "2026-04-01", "distance": 0.0, "runs": 0, "partial": None}
        assert points[-1]["distance"] == 3.1

    def test_partial_months_are_marked(self, client):
        points = client.get("/api/workouts/running").json()["points"]
        assert points[0]["partial"] == "truncated"  # data starts 2026-03-10
        assert points[-1]["partial"] == "in_progress"  # holds the newest data date

    def test_no_runs_in_range(self, client):
        body = client.get("/api/workouts/running?start=2026-09-01").json()
        assert body == {
            "unit": None,
            "total_distance": None,
            "runs": 0,
            "unmeasured_runs": 0,
            "points": [],
        }

    def test_mixed_units_are_converted_not_added(self, seeded_db_path, client):
        _add_runs(seeded_db_path, [(5.0, "mi", "2026-07-12"), (1609.344, "m", "2026-07-20")])
        body = client.get("/api/workouts/running").json()
        assert body["unit"] == "mi"
        assert body["total_distance"] == pytest.approx(3.1 + 5.0 + 1.0)
        july = next(p for p in body["points"] if p["date"] == "2026-07-01")
        assert july["distance"] == pytest.approx(6.0)

    def test_unit_tie_goes_to_the_more_recent(self, seeded_db_path, client):
        # One run in mi (the fixture's, 2026-08-10) and one earlier in km.
        _add_runs(seeded_db_path, [(10.0, "km", "2026-05-01")])
        assert client.get("/api/workouts/running").json()["unit"] == "mi"
        _add_runs(seeded_db_path, [(10.0, "km", "2026-08-10")])
        assert client.get("/api/workouts/running").json()["unit"] == "km"

    def test_unusable_distances_count_as_runs_but_are_reported(self, seeded_db_path, client):
        _add_runs(
            seeded_db_path,
            [(None, None, "2026-07-01"), (4.0, None, "2026-07-02"), (4.0, "kcal", "2026-07-03")],
        )
        body = client.get("/api/workouts/running").json()
        assert body["runs"] == 4
        assert body["unmeasured_runs"] == 3
        assert body["total_distance"] == 3.1


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
