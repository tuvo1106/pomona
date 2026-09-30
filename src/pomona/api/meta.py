"""How fresh the data is, for anchoring the frontend's relative date ranges."""

from fastapi import APIRouter

from pomona.api.dependencies import DbDep
from pomona.api.query import data_span

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/meta")
def meta(conn: DbDep) -> dict:
    """How fresh the data is, so the frontend can anchor relative ranges ("last 30 days") to
    the newest record instead of today. Data arrives in occasional manual exports, not a
    continuous sync, so "today" is usually past the end of the data -- anchoring to it makes
    the default view empty whenever the last export is over a month old.

    `latest_date` is the newest local date across records, workouts and ECG recordings (see
    `db.latest_data_date`). Anchoring on records alone would push a workout or ECG newer than
    the last Record outside every relative range. Every dated page waits on this endpoint at
    load and on each window refocus, so it's read from `ingest_meta`, where ingest stores it,
    rather than recomputed per request -- the `records` part is a full index scan on a real
    export. A database ingested before that key existed falls back to `query.data_span`, which
    computes it live once per ingest.

    `ingested_at` is when `pomona ingest` last ran, as a unix epoch. Either is null
    on an empty or partially built database.
    """
    stored = {
        row["key"]: row["value"]
        for row in conn.execute(
            "SELECT key, value FROM ingest_meta WHERE key IN ('latest_date', 'ingested_at')"
        )
    }
    if "latest_date" in stored:
        # Stored as "" when the ingest had no dated data at all.
        latest_date = stored["latest_date"] or None
    else:
        latest_date = data_span(conn)[1]
    return {
        "latest_date": latest_date,
        "ingested_at": int(stored["ingested_at"]) if "ingested_at" in stored else None,
    }
