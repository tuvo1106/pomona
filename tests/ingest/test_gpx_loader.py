import json
from datetime import datetime

from pomona.ingest.dates import parse_fhir_datetime
from pomona.ingest.gpx_loader import load_workout_routes
from pomona.ingest.loader import load_export_xml
from tests.conftest import ROUTES_FIXTURES_DIR, SAMPLE_EXPORT_XML


def _load(conn):
    load_export_xml(conn, SAMPLE_EXPORT_XML, show_progress=False)
    return load_workout_routes(conn, ROUTES_FIXTURES_DIR)


class TestLoadWorkoutRoutes:
    def test_loads_every_fixture_file(self, writable_conn):
        # ROUTES_FIXTURES_DIR also has malformed.gpx (bad XML) and no-time.gpx (no per-point
        # timestamps) -- both must be skipped, not loaded and not fatal to the other three.
        loaded, skipped = _load(writable_conn)
        assert loaded == 3
        assert skipped == 2
        assert writable_conn.execute("SELECT COUNT(*) FROM workout_routes").fetchone()[0] == 3

    def test_malformed_gpx_is_skipped_not_fatal(self, writable_conn):
        # A corrupt file must not raise out of load_workout_routes -- that would abort the
        # whole ingest transaction (export.xml included), not just the routes step.
        loaded, skipped = _load(writable_conn)
        assert loaded == 3
        assert skipped == 2
        source_files = {
            row["source_file"]
            for row in writable_conn.execute("SELECT source_file FROM workout_routes")
        }
        assert "malformed.gpx" not in source_files
        assert "no-time.gpx" not in source_files

    def test_route_overlapping_a_workout_is_matched_to_it(self, writable_conn):
        _load(writable_conn)
        cycling_id = writable_conn.execute(
            "SELECT id FROM workouts WHERE activity_type = 'HKWorkoutActivityTypeCycling'"
        ).fetchone()[0]
        row = writable_conn.execute(
            "SELECT * FROM workout_routes WHERE source_file = 'route_2026-08-01_10.00am.gpx'"
        ).fetchone()
        assert row["workout_id"] == cycling_id
        # start_local_date is inherited from the matched workout, not derived from the
        # route's own (UTC) timestamps.
        assert row["start_local_date"] == "2026-08-01"
        assert row["point_count"] == 3
        segments = json.loads(row["points_json"])
        # A single <trkseg> -- one segment holding all three points.
        assert segments == [[[37.7749, -122.4194], [37.7755, -122.4184], [37.7761, -122.4174]]]

    def test_route_with_a_pause_keeps_segments_separate(self, writable_conn):
        # Two <trkseg> blocks (a pause/resume) must stay two separate point lists, not get
        # flattened into one continuous line -- flattening would draw a false straight line
        # across the gap between them when rendered on the map.
        _load(writable_conn)
        row = writable_conn.execute(
            "SELECT * FROM workout_routes WHERE source_file = 'route_2026-08-01_10.20am_paused.gpx'"
        ).fetchone()
        assert row["point_count"] == 4
        segments = json.loads(row["points_json"])
        assert segments == [
            [[37.8000, -122.5000], [37.8010, -122.5010]],
            [[37.9000, -122.6000], [37.9010, -122.6010]],
        ]

    def test_route_matching_no_workout_is_kept_with_null_workout_id(self, writable_conn):
        _load(writable_conn)
        row = writable_conn.execute(
            "SELECT * FROM workout_routes WHERE source_file = 'route_2019-01-01_08.00am.gpx'"
        ).fetchone()
        assert row["workout_id"] is None
        # Falls back to the ingest machine's own local date (no matched workout to inherit a
        # real local date from, and GPX <time> carries no UTC offset) -- computed the same
        # way the loader does, not hardcoded, so this isn't tied to the test machine's zone.
        expected_epoch = parse_fhir_datetime("2019-01-01T13:00:00Z")
        assert row["start_local_date"] == datetime.fromtimestamp(expected_epoch).date().isoformat()
        assert row["point_count"] == 2

    def test_missing_routes_dir_returns_zero_without_raising(self, writable_conn, tmp_path):
        loaded, skipped = load_workout_routes(writable_conn, tmp_path / "does-not-exist")
        assert (loaded, skipped) == (0, 0)

    def test_missing_routes_dir_leaves_existing_rows_intact(self, writable_conn, tmp_path):
        _load(writable_conn)
        load_workout_routes(writable_conn, tmp_path / "typo-workout-routes")
        assert writable_conn.execute("SELECT COUNT(*) FROM workout_routes").fetchone()[0] == 3

    def test_reingesting_is_idempotent(self, writable_conn):
        first = _load(writable_conn)
        second = load_workout_routes(writable_conn, ROUTES_FIXTURES_DIR)
        assert first == second == (3, 2)
        assert writable_conn.execute("SELECT COUNT(*) FROM workout_routes").fetchone()[0] == 3
