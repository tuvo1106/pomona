import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  id                INTEGER PRIMARY KEY,
  type              TEXT NOT NULL,
  value_text        TEXT,
  value_num         REAL,
  unit              TEXT,
  source_name       TEXT,
  source_version    TEXT,
  device            TEXT,
  creation_date     INTEGER,
  start_date        INTEGER NOT NULL,
  end_date          INTEGER NOT NULL,
  start_local_date  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workouts (
  id                        INTEGER PRIMARY KEY,
  activity_type             TEXT NOT NULL,
  duration                  REAL,
  duration_unit             TEXT,
  total_distance            REAL,
  total_distance_unit       TEXT,
  total_energy_burned       REAL,
  total_energy_burned_unit  TEXT,
  source_name               TEXT,
  source_version            TEXT,
  device                    TEXT,
  creation_date             INTEGER,
  start_date                INTEGER NOT NULL,
  end_date                  INTEGER NOT NULL,
  start_local_date          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activity_summaries (
  date                        TEXT PRIMARY KEY,
  active_energy_burned        REAL,
  active_energy_burned_goal   REAL,
  active_energy_burned_unit   TEXT,
  apple_move_time             REAL,
  apple_move_time_goal        REAL,
  apple_exercise_time         REAL,
  apple_exercise_time_goal    REAL,
  apple_stand_hours           REAL,
  apple_stand_hours_goal      REAL
);

-- resource_id is the FHIR resource's own id, which is only unique per resource type per
-- issuing server -- a Condition and an Observation can both be id "1", and two providers
-- can hand out the same id for the same type. So it's a plain column, not the key, and
-- rows are identified by a synthetic rowid instead.
CREATE TABLE IF NOT EXISTS clinical_records (
  id                INTEGER PRIMARY KEY,
  resource_id       TEXT NOT NULL,
  resource_type     TEXT NOT NULL,
  code_text         TEXT,
  code_system       TEXT,
  code_value        TEXT,
  status            TEXT,
  value_num         REAL,
  value_unit        TEXT,
  value_text        TEXT,
  effective_date    INTEGER,
  recorded_date     INTEGER,
  category          TEXT,
  results_json      TEXT,
  raw_json          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);

-- workout_id is nullable: a route is kept even if no workout's time window overlaps it
-- (matching is best-effort by timestamp, not a guaranteed join -- see gpx_loader.py).
CREATE TABLE IF NOT EXISTS workout_routes (
  id                INTEGER PRIMARY KEY,
  workout_id        INTEGER,
  start_date        INTEGER NOT NULL,
  end_date          INTEGER NOT NULL,
  start_local_date  TEXT NOT NULL,
  point_count       INTEGER NOT NULL,
  points_json       TEXT NOT NULL,
  source_file       TEXT NOT NULL
);

-- lead/unit are columns rather than hardcoded (every current export has "Lead I"/"µV")
-- since this app never migrates schemas -- a future export with a different lead name
-- would otherwise need one. samples_json is the raw, lossless sample array -- downsampling
-- for charting happens at request time in the API (see waveform.py), not at ingest.
CREATE TABLE IF NOT EXISTS ecg_recordings (
  id                    INTEGER PRIMARY KEY,
  recorded_date         INTEGER NOT NULL,
  recorded_local_date   TEXT NOT NULL,
  classification        TEXT,
  symptoms              TEXT,
  software_version      TEXT,
  device                TEXT,
  sample_rate           REAL NOT NULL,
  lead                  TEXT,
  unit                  TEXT,
  sample_count          INTEGER NOT NULL,
  samples_json          TEXT NOT NULL,
  source_file           TEXT NOT NULL
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_records_type_start     ON records(type, start_date);
CREATE INDEX IF NOT EXISTS idx_records_type_localdate ON records(type, start_local_date);

CREATE INDEX IF NOT EXISTS idx_workouts_type_start ON workouts(activity_type, start_date);
CREATE INDEX IF NOT EXISTS idx_workouts_localdate  ON workouts(start_local_date);

CREATE INDEX IF NOT EXISTS idx_clinical_type_date
  ON clinical_records(resource_type, effective_date);
CREATE INDEX IF NOT EXISTS idx_clinical_code ON clinical_records(code_text);

CREATE INDEX IF NOT EXISTS idx_workout_routes_workout ON workout_routes(workout_id);

CREATE INDEX IF NOT EXISTS idx_ecg_recordings_recorded_date ON ecg_recordings(recorded_date);
"""

VIEWS = """
CREATE VIEW IF NOT EXISTS daily_resting_hr AS
  SELECT start_local_date AS date, AVG(value_num) AS value
  FROM records WHERE type = 'HKQuantityTypeIdentifierRestingHeartRate'
  GROUP BY start_local_date;

CREATE VIEW IF NOT EXISTS daily_weight AS
  SELECT start_local_date AS date, AVG(value_num) AS value
  FROM records WHERE type = 'HKQuantityTypeIdentifierBodyMass'
  GROUP BY start_local_date;
"""
# No daily_steps / daily_active_energy views: those are cumulative "sum" metrics that
# HealthKit logs independently per source (iPhone, Watch, ...), so a naive SUM over
# `records` inflates the true total on any day with more than one active device. The
# correct aggregation requires per-record time-window deduplication (see dedup.py), which
# is a sequential/stateful algorithm that can't be expressed as a plain SQL view -- use the
# /api/metrics/{type}/timeseries endpoint (or dedup.py directly) instead of querying
# `records` for these types. daily_resting_hr/daily_weight are unaffected: they're
# point-in-time averages, not cumulative sums, so multi-source overlap doesn't inflate them.


def connect(
    db_path: Path, *, readonly: bool = False, isolation_level: str | None = ""
) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if readonly:
        conn = sqlite3.connect(
            f"file:{db_path}?mode=ro",
            uri=True,
            check_same_thread=False,
            isolation_level=isolation_level,
        )
    else:
        conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=isolation_level)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA cache_size=-64000")
    conn.execute("PRAGMA mmap_size=268435456")
    conn.row_factory = sqlite3.Row
    return conn


def _exec_statements(conn: sqlite3.Connection, sql_block: str) -> None:
    """Executes each statement individually via conn.execute(), NOT executescript().

    executescript() implicitly commits any pending transaction before running, which
    would silently break the caller's explicit BEGIN/COMMIT around a full ingest run.
    """
    for statement in sql_block.split(";"):
        statement = statement.strip()
        if statement:
            conn.execute(statement)


def init_schema(conn: sqlite3.Connection) -> None:
    _exec_statements(conn, SCHEMA)


def create_indexes(conn: sqlite3.Connection) -> None:
    _exec_statements(conn, INDEXES)


def create_views(conn: sqlite3.Connection) -> None:
    _exec_statements(conn, VIEWS)


def latest_data_date(conn: sqlite3.Connection) -> str | None:
    """The newest local date (YYYY-MM-DD) across records, workouts and ECG recordings -- the
    tables the dated pages filter on (routes are dated by their workout) -- or None if all
    three are empty.

    Not cheap on a real export: `records` has no index that leads with `start_local_date`
    (`idx_records_type_localdate` leads with `type`), so its MAX is a full index scan. So
    ingest computes this once and stores it in `ingest_meta` under `latest_date`, and the
    API only calls this live for a database ingested before that key existed.
    """
    newest_ecg = conn.execute(
        # recorded_date is the indexed epoch; its local date is what's reported.
        "SELECT recorded_local_date FROM ecg_recordings ORDER BY recorded_date DESC LIMIT 1"
    ).fetchone()
    candidates = [
        conn.execute("SELECT MAX(start_local_date) FROM records").fetchone()[0],
        conn.execute("SELECT MAX(start_local_date) FROM workouts").fetchone()[0],
        newest_ecg[0] if newest_ecg else None,
    ]
    # Zero-padded YYYY-MM-DD, so string max is date max.
    return max((d for d in candidates if d), default=None)


def earliest_data_date(conn: sqlite3.Connection) -> str | None:
    """The oldest local date across the same tables as `latest_data_date`, or None if all
    three are empty. Same cost profile (a full index scan of `records`), so ingest stores it
    in `ingest_meta` under `earliest_date` and the API only computes it live as a fallback.
    """
    oldest_ecg = conn.execute(
        "SELECT recorded_local_date FROM ecg_recordings ORDER BY recorded_date ASC LIMIT 1"
    ).fetchone()
    candidates = [
        conn.execute("SELECT MIN(start_local_date) FROM records").fetchone()[0],
        conn.execute("SELECT MIN(start_local_date) FROM workouts").fetchone()[0],
        oldest_ecg[0] if oldest_ecg else None,
    ]
    return min((d for d in candidates if d), default=None)
