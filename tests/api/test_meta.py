from tests.conftest import writing


class TestMeta:
    # The seeded fixture is built with the loaders directly, not `pomona ingest`, so
    # ingest_meta has no `latest_date` key -- the tests up to the stored-key ones below all
    # exercise the live fallback a pre-existing database gets.

    def test_stored_latest_date_is_returned_instead_of_computing_it_live(
        self, client, seeded_db_path
    ):
        with writing(seeded_db_path) as conn:
            # Deliberately not the live answer (2026-08-10), so getting it back proves the
            # stored key was used rather than the full-scan query.
            conn.execute(
                "INSERT INTO ingest_meta (key, value) VALUES ('latest_date', '2030-01-01')"
            )
        assert client.get("/api/meta").json()["latest_date"] == "2030-01-01"

    def test_stored_empty_latest_date_is_null_not_a_live_fallback(self, client, seeded_db_path):
        # Ingest stores "" when there was no dated data. That's a real answer, not a missing
        # key, so it must not fall back to the live query (which here would find data).
        with writing(seeded_db_path) as conn:
            conn.execute("INSERT INTO ingest_meta (key, value) VALUES ('latest_date', '')")
        assert client.get("/api/meta").json()["latest_date"] is None

    def test_a_workout_newer_than_every_record_sets_latest_date(self, client):
        response = client.get("/api/meta")
        assert response.status_code == 200
        # The newest <Record> in sample_export.xml is on 2026-08-05, but a <Workout> is on
        # 2026-08-10. Anchoring on records alone would leave that workout outside every
        # relative range.
        assert response.json()["latest_date"] == "2026-08-10"

    def test_latest_date_is_the_newest_record_when_records_are_newest(self, client, seeded_db_path):
        with writing(seeded_db_path) as conn:
            conn.execute(
                "INSERT INTO records "
                "(type, value_num, unit, start_date, end_date, start_local_date) "
                "VALUES ('HKQuantityTypeIdentifierStepCount', 10, 'count', 0, 0, '2026-08-15')"
            )
        assert client.get("/api/meta").json()["latest_date"] == "2026-08-15"

    def test_an_ecg_newer_than_everything_else_sets_latest_date(self, client, seeded_db_path):
        with writing(seeded_db_path) as conn:
            # recorded_date (the indexed epoch) is what picks the newest recording; its
            # recorded_local_date is what's reported.
            conn.execute(
                "INSERT INTO ecg_recordings (recorded_date, recorded_local_date, sample_rate, "
                "sample_count, samples_json, source_file) "
                "VALUES (1787000000, '2026-08-17', 512, 0, '[]', 'ecg_2026-08-17.csv')"
            )
        assert client.get("/api/meta").json()["latest_date"] == "2026-08-17"

    def test_ingested_at_is_null_when_ingest_never_wrote_it(self, client):
        # The fixture is built with the loaders directly, not `pomona ingest`, so
        # ingest_meta is empty -- that must read as null, not fail.
        assert client.get("/api/meta").json()["ingested_at"] is None

    def test_ingested_at_is_read_from_ingest_meta_as_an_epoch(self, client, seeded_db_path):
        with writing(seeded_db_path) as conn:
            conn.execute(
                "INSERT INTO ingest_meta (key, value) VALUES ('ingested_at', '1787242117')"
            )
        assert client.get("/api/meta").json()["ingested_at"] == 1787242117

    def test_empty_tables_return_null_latest_date(self, client, seeded_db_path):
        with writing(seeded_db_path) as conn:
            for table in ("records", "workouts", "ecg_recordings"):
                conn.execute(f"DELETE FROM {table}")
        assert client.get("/api/meta").json()["latest_date"] is None
