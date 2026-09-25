from pomona.ingest.loader import load_export_xml
from tests.conftest import SAMPLE_EXPORT_XML


def _load(conn):
    return load_export_xml(conn, SAMPLE_EXPORT_XML, show_progress=False)


class TestLoadExportXml:
    def test_row_counts_match_parsed_elements(self, writable_conn):
        counts = _load(writable_conn)
        assert counts == {"Record": 18, "Workout": 2, "ActivitySummary": 2}
        assert writable_conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 18
        assert writable_conn.execute("SELECT COUNT(*) FROM workouts").fetchone()[0] == 2
        assert writable_conn.execute("SELECT COUNT(*) FROM activity_summaries").fetchone()[0] == 2

    def test_numeric_record_value_is_parsed_into_value_num(self, writable_conn):
        _load(writable_conn)
        row = writable_conn.execute(
            "SELECT value_text, value_num, unit FROM records WHERE type = ? AND value_num = 123",
            ["HKQuantityTypeIdentifierStepCount"],
        ).fetchone()
        assert row["value_text"] == "123"
        assert row["value_num"] == 123.0
        assert row["unit"] == "count"

    def test_categorical_record_value_num_is_null(self, writable_conn):
        _load(writable_conn)
        row = writable_conn.execute(
            "SELECT value_text, value_num FROM records "
            "WHERE type = 'HKCategoryTypeIdentifierSleepAnalysis'"
        ).fetchone()
        assert row["value_text"] == "HKCategoryValueSleepAnalysisAsleepUnspecified"
        assert row["value_num"] is None

    def test_start_local_date_follows_each_records_own_offset(self, writable_conn):
        _load(writable_conn)
        rows = writable_conn.execute(
            "SELECT start_local_date FROM records "
            "WHERE type = 'HKQuantityTypeIdentifierStepCount' ORDER BY start_date"
        ).fetchall()
        local_dates = {row["start_local_date"] for row in rows}
        assert "2026-08-01" in local_dates
        assert "2026-03-10" in local_dates  # the +0100-offset record

    def test_workout_fields_are_captured(self, writable_conn):
        _load(writable_conn)
        row = writable_conn.execute(
            "SELECT * FROM workouts WHERE activity_type = 'HKWorkoutActivityTypeCycling'"
        ).fetchone()
        assert row["duration"] == 45.5
        assert row["duration_unit"] == "min"
        assert row["total_distance"] == 15.2
        assert row["total_energy_burned"] == 420.0
        assert row["start_local_date"] == "2026-08-01"

    def test_workout_without_inline_totals_backfills_from_statistics(self, writable_conn):
        # Modern (watchOS 9+) export format: energy/distance only exist as nested
        # WorkoutStatistics children, not inline Workout attributes.
        _load(writable_conn)
        row = writable_conn.execute(
            "SELECT * FROM workouts WHERE activity_type = 'HKWorkoutActivityTypeRunning'"
        ).fetchone()
        assert row["total_energy_burned"] == 310.5
        assert row["total_energy_burned_unit"] == "Cal"
        assert row["total_distance"] == 3.1
        assert row["total_distance_unit"] == "mi"

    def test_activity_summary_fields_are_captured(self, writable_conn):
        _load(writable_conn)
        row = writable_conn.execute(
            "SELECT * FROM activity_summaries WHERE date = '2026-08-01'"
        ).fetchone()
        assert row["active_energy_burned"] == 420.0
        assert row["apple_stand_hours"] == 10.0

    def test_duplicate_activity_summary_dates_do_not_abort_the_ingest(
        self, writable_conn, tmp_path
    ):
        # date is the primary key, but backup-restored / device-merged exports can repeat a
        # day. The run must survive it (keeping the last entry) rather than raising
        # IntegrityError and rolling back everything ingested so far.
        xml_path = tmp_path / "export.xml"
        xml_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<HealthData>\n"
            '  <ActivitySummary dateComponents="2024-01-01" activeEnergyBurned="300"\n'
            '                   appleStandHours="8"/>\n'
            '  <ActivitySummary dateComponents="2024-01-01" activeEnergyBurned="450"\n'
            '                   appleStandHours="11"/>\n'
            "</HealthData>\n"
        )
        counts = load_export_xml(writable_conn, xml_path, show_progress=False)
        assert counts["ActivitySummary"] == 2
        rows = writable_conn.execute("SELECT * FROM activity_summaries").fetchall()
        assert len(rows) == 1
        assert rows[0]["active_energy_burned"] == 450.0

    def test_reingesting_is_idempotent(self, writable_conn):
        first = _load(writable_conn)
        second = _load(writable_conn)
        assert first == second
        assert writable_conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 18

    def test_drop_and_reload_clears_previous_data_before_reinserting(self, writable_conn):
        _load(writable_conn)
        # Simulate stale data from a previous ingest that a real re-export would never
        # produce, to prove the next ingest clears it rather than merely appending.
        writable_conn.execute(
            "INSERT INTO records "
            "(type, value_text, value_num, unit, start_date, end_date, start_local_date) "
            "VALUES ('Stale', 'x', NULL, NULL, 0, 0, '1970-01-01')"
        )
        assert writable_conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 19
        _load(writable_conn)
        assert writable_conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 18
        assert (
            writable_conn.execute("SELECT COUNT(*) FROM records WHERE type = 'Stale'").fetchone()[0]
            == 0
        )
