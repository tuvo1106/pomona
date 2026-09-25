import json

from pomona.ingest.ecg_loader import load_ecg_recordings
from tests.conftest import ECG_FIXTURES_DIR


class TestLoadEcgRecordings:
    def test_loads_every_valid_fixture_file(self, writable_conn):
        # ECG_FIXTURES_DIR also has malformed.csv (non-numeric sample) and
        # missing-sample-rate.csv (no Sample Rate row) -- both must be skipped, not loaded
        # and not fatal to the other two.
        loaded, skipped = load_ecg_recordings(writable_conn, ECG_FIXTURES_DIR)
        assert loaded == 2
        assert skipped == 2
        assert writable_conn.execute("SELECT COUNT(*) FROM ecg_recordings").fetchone()[0] == 2

    def test_bad_files_are_skipped_not_fatal(self, writable_conn):
        # A corrupt/incomplete file must not raise out of load_ecg_recordings -- that would
        # abort the whole ingest transaction (export.xml included), not just the ECG step.
        load_ecg_recordings(writable_conn, ECG_FIXTURES_DIR)
        source_files = {
            row["source_file"]
            for row in writable_conn.execute("SELECT source_file FROM ecg_recordings")
        }
        assert "malformed.csv" not in source_files
        assert "missing-sample-rate.csv" not in source_files

    def test_fields_parsed_correctly(self, writable_conn):
        load_ecg_recordings(writable_conn, ECG_FIXTURES_DIR)
        row = writable_conn.execute(
            "SELECT * FROM ecg_recordings WHERE source_file = 'ecg_2026-06-01.csv'"
        ).fetchone()
        assert row["classification"] == "Sinus Rhythm"
        assert row["symptoms"] is None
        assert row["software_version"] == "1.90"
        assert row["device"] == "Watch6,14"
        assert row["sample_rate"] == 512.0
        assert row["lead"] == "Lead I"
        assert row["unit"] == "µV"
        assert row["sample_count"] == 250
        assert row["recorded_local_date"] == "2026-06-01"
        samples = json.loads(row["samples_json"])
        assert samples[0] == 999.0
        assert len(samples) == 250

    def test_symptoms_field_kept_when_present(self, writable_conn):
        load_ecg_recordings(writable_conn, ECG_FIXTURES_DIR)
        row = writable_conn.execute(
            "SELECT * FROM ecg_recordings WHERE source_file = 'ecg_2026-06-15.csv'"
        ).fetchone()
        assert row["classification"] == "Inconclusive"
        assert row["symptoms"] == "Rapid Heartbeat"
        assert row["sample_count"] == 5

    def test_missing_ecg_dir_returns_zero_without_raising(self, writable_conn, tmp_path):
        loaded, skipped = load_ecg_recordings(writable_conn, tmp_path / "does-not-exist")
        assert (loaded, skipped) == (0, 0)

    def test_missing_ecg_dir_leaves_existing_rows_intact(self, writable_conn, tmp_path):
        load_ecg_recordings(writable_conn, ECG_FIXTURES_DIR)
        load_ecg_recordings(writable_conn, tmp_path / "typo-electrocardiograms")
        assert writable_conn.execute("SELECT COUNT(*) FROM ecg_recordings").fetchone()[0] == 2

    def test_reingesting_is_idempotent(self, writable_conn):
        first = load_ecg_recordings(writable_conn, ECG_FIXTURES_DIR)
        second = load_ecg_recordings(writable_conn, ECG_FIXTURES_DIR)
        assert first == second == (2, 2)
        assert writable_conn.execute("SELECT COUNT(*) FROM ecg_recordings").fetchone()[0] == 2
