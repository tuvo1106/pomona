import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException

from pomona import db as db_module
from pomona.config import settings


def get_db() -> Iterator[sqlite3.Connection]:
    """A fresh, short-lived read-only connection per request.

    Cheap on a local WAL-mode SQLite file at this concurrency level — no pooling needed.
    Read-only since every dashboard route only ever SELECTs; ingestion is the only writer.
    """
    if not settings.db_path.exists():
        # Serving before ever ingesting is an easy first-run mistake, and a mode=ro connect
        # to a nonexistent file just raises OperationalError -> an unhelpful 500 on every
        # route. Say what's actually wrong instead.
        raise HTTPException(
            503,
            f"No health database at {settings.db_path}. "
            f"Run `pomona ingest <path-to-export.xml>` first.",
        )
    conn = db_module.connect(settings.db_path, readonly=True)
    try:
        yield conn
    finally:
        conn.close()


DbDep = Annotated[sqlite3.Connection, Depends(get_db)]
