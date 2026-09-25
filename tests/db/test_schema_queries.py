from pomona import db as db_module


def _seed(conn, rows):
    conn.executemany(
        "INSERT INTO records "
        "(type, value_text, value_num, unit, start_date, end_date, start_local_date) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )


class TestSchemaCreation:
    def test_all_tables_exist(self, writable_conn):
        tables = {
            row["name"]
            for row in writable_conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {
            "records",
            "workouts",
            "activity_summaries",
            "clinical_records",
            "ingest_meta",
            "workout_routes",
            "ecg_recordings",
        } <= tables

    def test_init_schema_is_idempotent(self, writable_conn):
        db_module.init_schema(writable_conn)  # must not raise (CREATE TABLE IF NOT EXISTS)

    def test_indexes_exist_after_create_indexes(self, writable_conn):
        db_module.create_indexes(writable_conn)
        indexes = {
            row["name"]
            for row in writable_conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
        assert "idx_records_type_start" in indexes
        assert "idx_records_type_localdate" in indexes
        assert "idx_workouts_type_start" in indexes
        assert "idx_clinical_type_date" in indexes
        assert "idx_ecg_recordings_recorded_date" in indexes

    def test_create_indexes_is_idempotent(self, writable_conn):
        db_module.create_indexes(writable_conn)
        db_module.create_indexes(writable_conn)  # must not raise

    def test_views_are_queryable(self, writable_conn):
        db_module.create_views(writable_conn)
        _seed(
            writable_conn,
            [
                (
                    "HKQuantityTypeIdentifierRestingHeartRate",
                    "60",
                    60.0,
                    "count/min",
                    0,
                    0,
                    "2026-01-01",
                ),
                (
                    "HKQuantityTypeIdentifierRestingHeartRate",
                    "70",
                    70.0,
                    "count/min",
                    1,
                    1,
                    "2026-01-01",
                ),
            ],
        )
        row = writable_conn.execute(
            "SELECT value FROM daily_resting_hr WHERE date = '2026-01-01'"
        ).fetchone()
        assert row["value"] == 65.0


class TestAggregationQueries:
    def test_sum_aggregation_over_a_day_matches_hand_computed_total(self, writable_conn):
        _seed(
            writable_conn,
            [
                ("HKQuantityTypeIdentifierStepCount", "10", 10.0, "count", 0, 1, "2026-01-01"),
                ("HKQuantityTypeIdentifierStepCount", "20", 20.0, "count", 1, 2, "2026-01-01"),
                ("HKQuantityTypeIdentifierStepCount", "5", 5.0, "count", 2, 3, "2026-01-02"),
            ],
        )
        rows = writable_conn.execute(
            "SELECT start_local_date AS date, SUM(value_num) AS total "
            "FROM records WHERE type = 'HKQuantityTypeIdentifierStepCount' "
            "GROUP BY start_local_date ORDER BY date"
        ).fetchall()
        assert [(row["date"], row["total"]) for row in rows] == [
            ("2026-01-01", 30.0),
            ("2026-01-02", 5.0),
        ]

    def test_avg_aggregation_matches_hand_computed_average(self, writable_conn):
        _seed(
            writable_conn,
            [
                ("HKQuantityTypeIdentifierHeartRate", "60", 60.0, "count/min", 0, 0, "2026-01-01"),
                ("HKQuantityTypeIdentifierHeartRate", "80", 80.0, "count/min", 1, 1, "2026-01-01"),
            ],
        )
        row = writable_conn.execute(
            "SELECT AVG(value_num) AS avg FROM records "
            "WHERE type = 'HKQuantityTypeIdentifierHeartRate'"
        ).fetchone()
        assert row["avg"] == 70.0

    def test_type_and_localdate_index_is_used_for_the_dashboard_timeseries_query(
        self, writable_conn
    ):
        db_module.create_indexes(writable_conn)
        plan = writable_conn.execute(
            "EXPLAIN QUERY PLAN "
            "SELECT start_local_date, SUM(value_num) FROM records "
            "WHERE type = 'HKQuantityTypeIdentifierStepCount' GROUP BY start_local_date"
        ).fetchall()
        plan_text = " ".join(row["detail"] for row in plan)
        assert "idx_records_type_localdate" in plan_text
