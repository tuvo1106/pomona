import sqlite3
from pathlib import Path

import pytest

from pomona import db as db_module

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
