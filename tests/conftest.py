import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from pomona import db as db_module
from pomona.ingest.clinical_loader import load_clinical_records
from pomona.ingest.ecg_loader import load_ecg_recordings
from pomona.ingest.gpx_loader import load_workout_routes
from pomona.ingest.loader import load_export_xml

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_EXPORT_XML = FIXTURES_DIR / "sample_export.xml"
CLINICAL_FIXTURES_DIR = FIXTURES_DIR / "clinical-records"
ROUTES_FIXTURES_DIR = FIXTURES_DIR / "workout-routes"
ECG_FIXTURES_DIR = FIXTURES_DIR / "electrocardiograms"


@pytest.fixture
def db_path(tmp_path) -> Path:
    return tmp_path / "health.db"


@pytest.fixture
def writable_conn(db_path) -> sqlite3.Connection:
    """A writable connection with the schema already created, autocommit (isolation_level=None)
    so tests can manage their own transactions the same way the CLI's ingest command does.
    """
    conn = db_module.connect(db_path, isolation_level=None)
    db_module.init_schema(conn)
    yield conn
    conn.close()


def checkpoint_and_close(conn: sqlite3.Connection) -> None:
    """Flushes WAL to the main DB file so a subsequently opened mode=ro connection sees it."""
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()


@contextmanager
def writing(db_path: Path) -> Iterator[sqlite3.Connection]:
    """An autocommit connection for seeding a test database, checkpointed and closed on exit so
    a read-only connection opened afterwards -- the API's -- sees every write.
    """
    conn = db_module.connect(db_path, isolation_level=None)
    try:
        yield conn
    finally:
        checkpoint_and_close(conn)


def ingest_into(
    conn: sqlite3.Connection,
    *,
    export_xml: Path | None = None,
    clinical_dir: Path | None = None,
    routes_dir: Path | None = None,
    ecg_dir: Path | None = None,
) -> None:
    """Builds the schema and loads whichever sources are given, with the loaders the CLI's
    ingest uses, then creates the indexes as ingest does."""
    db_module.init_schema(conn)
    if export_xml is not None:
        load_export_xml(conn, export_xml, show_progress=False)
    if clinical_dir is not None:
        load_clinical_records(conn, clinical_dir)
    if routes_dir is not None:
        load_workout_routes(conn, routes_dir)
    if ecg_dir is not None:
        load_ecg_recordings(conn, ecg_dir)
    db_module.create_indexes(conn)
