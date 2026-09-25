import sqlite3

from typer.testing import CliRunner

from pomona.cli import app
from tests.conftest import SAMPLE_EXPORT_XML

runner = CliRunner()


class TestIngestMeta:
    def test_ingest_stores_latest_date_across_records_and_workouts(self, tmp_path):
        # /api/meta reads this key instead of scanning `records` on every page load. The
        # fixture's newest <Record> is 2026-08-05 but a <Workout> is 2026-08-10, so the
        # stored value must be the max across tables, not just records.
        db_path = tmp_path / "health.db"
        result = runner.invoke(
            app, ["ingest", str(SAMPLE_EXPORT_XML), "--db", str(db_path), "--fast"]
        )
        assert result.exit_code == 0, result.output

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT value FROM ingest_meta WHERE key = 'latest_date'").fetchone()
        earliest = conn.execute(
            "SELECT value FROM ingest_meta WHERE key = 'earliest_date'"
        ).fetchone()
        conn.close()
        assert row == ("2026-08-10",)
        # /api/overview reads this to tell whether a comparison period has data. The oldest
        # <Record> (2026-03-10) is older than any workout or ECG in the fixture.
        assert earliest == ("2026-03-10",)


class TestIngestStaleSchema:
    def test_pre_existing_older_schema_gives_a_clear_message_not_a_traceback(self, tmp_path):
        # Simulate a database built before a schema change (e.g. clinical_records losing
        # its resource_id column -- see ADR-0003): init_schema()'s CREATE TABLE IF NOT
        # EXISTS is a no-op against it, so the mismatch only surfaces once ingest tries to
        # write a column that isn't there.
        db_path = tmp_path / "stale.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE clinical_records (id TEXT PRIMARY KEY, resource_type TEXT NOT NULL, "
            "raw_json TEXT NOT NULL)"
        )
        conn.commit()
        conn.close()

        result = runner.invoke(
            app, ["ingest", str(SAMPLE_EXPORT_XML), "--db", str(db_path), "--fast"]
        )

        assert result.exit_code == 1
        assert "no in-place migration" in result.output
        assert str(db_path) in result.output
        assert "Traceback" not in result.output

    def test_unrelated_operational_errors_still_raise(self, tmp_path):
        # A locked/corrupt file, a permissions issue, etc. isn't a schema problem and must
        # not be swallowed into the "delete your database" message.
        db_path = tmp_path / "not-a-database.db"
        db_path.write_text("this is not a sqlite file")

        result = runner.invoke(
            app, ["ingest", str(SAMPLE_EXPORT_XML), "--db", str(db_path), "--fast"]
        )

        assert result.exit_code != 0
        assert "no in-place migration" not in result.output
