import sqlite3
import time
from pathlib import Path

import typer

from pomona import db
from pomona.config import settings
from pomona.ingest.clinical_loader import load_clinical_records
from pomona.ingest.ecg_loader import load_ecg_recordings
from pomona.ingest.gpx_loader import load_workout_routes
from pomona.ingest.loader import load_export_xml

app = typer.Typer(help="Pomona: a local dashboard for your Apple Health export")


# There's no schema migration here (see AGENTS.md / ADR-0003) -- the database is fully
# rebuilt from the export every ingest, so a schema change is meant to be handled by
# deleting the file, not upgrading it in place. sqlite3's own message for the mismatch
# this produces ("no such column: ...", "table X has no column named Y", "no such
# table: ...") is accurate but reads like a bug report, not instructions. This turns it
# into the latter.
_STALE_SCHEMA_MARKERS = ("no such column", "has no column named", "no such table")


def _is_stale_schema_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in _STALE_SCHEMA_MARKERS)


@app.command()
def ingest(
    export_xml: Path = typer.Argument(..., help="Path to Apple Health's export.xml"),
    clinical_dir: Path = typer.Option(
        None,
        "--clinical-dir",
        exists=True,
        file_okay=False,
        help="Path to clinical-records/ (FHIR JSON). Defaults to a sibling "
        "clinical-records/ next to export.xml, if it exists.",
    ),
    routes_dir: Path = typer.Option(
        None,
        "--routes-dir",
        exists=True,
        file_okay=False,
        help="Path to workout-routes/ (GPX files). Defaults to a sibling "
        "workout-routes/ next to export.xml, if it exists.",
    ),
    ecg_dir: Path = typer.Option(
        None,
        "--ecg-dir",
        exists=True,
        file_okay=False,
        help="Path to electrocardiograms/ (ECG CSV files). Defaults to a sibling "
        "electrocardiograms/ next to export.xml, if it exists.",
    ),
    db_path: Path = typer.Option(settings.db_path, "--db", help="SQLite database path"),
    fast: bool = typer.Option(
        False, "--fast", help="Skip the pre-count pass (no ETA, just a running counter)"
    ),
) -> None:
    """Streams export.xml (and clinical-records/, if present) into a local SQLite DB.

    Drop-and-reload: safe to re-run after a new export. Runs inside a single
    transaction, so a crash partway through leaves the previous database untouched.
    """
    if clinical_dir is None:
        candidate = export_xml.parent / "clinical-records"
        clinical_dir = candidate if candidate.exists() else None
    if routes_dir is None:
        candidate = export_xml.parent / "workout-routes"
        routes_dir = candidate if candidate.exists() else None
    if ecg_dir is None:
        candidate = export_xml.parent / "electrocardiograms"
        ecg_dir = candidate if candidate.exists() else None

    conn = db.connect(db_path, isolation_level=None)
    try:
        db.init_schema(conn)
        conn.execute("BEGIN")
        start = time.monotonic()

        counts = load_export_xml(conn, export_xml, show_progress=not fast)
        clinical_count = load_clinical_records(conn, clinical_dir) if clinical_dir else 0
        routes_count, routes_skipped = (
            load_workout_routes(conn, routes_dir) if routes_dir else (0, 0)
        )
        ecg_count, ecg_skipped = load_ecg_recordings(conn, ecg_dir) if ecg_dir else (0, 0)

        db.create_indexes(conn)
        db.create_views(conn)
        elapsed = time.monotonic() - start

        conn.execute("DELETE FROM ingest_meta")
        conn.executemany(
            "INSERT INTO ingest_meta (key, value) VALUES (?, ?)",
            [
                ("source_file", str(export_xml)),
                ("clinical_dir", str(clinical_dir) if clinical_dir else ""),
                ("routes_dir", str(routes_dir) if routes_dir else ""),
                ("ecg_dir", str(ecg_dir) if ecg_dir else ""),
                ("records_count", str(counts.get("Record", 0))),
                ("workouts_count", str(counts.get("Workout", 0))),
                ("activity_summaries_count", str(counts.get("ActivitySummary", 0))),
                ("clinical_records_count", str(clinical_count)),
                ("routes_count", str(routes_count)),
                ("routes_skipped_count", str(routes_skipped)),
                ("ecg_count", str(ecg_count)),
                ("ecg_skipped_count", str(ecg_skipped)),
                ("ingested_at", str(int(time.time()))),
                ("ingest_seconds", f"{elapsed:.1f}"),
                # Read by /api/meta on every page load; too slow to compute per request.
                ("latest_date", db.latest_data_date(conn) or ""),
                # Read by /api/overview to tell whether a comparison period has data.
                ("earliest_date", db.earliest_data_date(conn) or ""),
            ],
        )
        conn.commit()
    except sqlite3.OperationalError as exc:
        conn.rollback()
        if _is_stale_schema_error(exc):
            typer.echo(
                f"Error: {db_path} was built with an older version of this app's schema "
                f"({exc}).\nThere's no in-place migration -- delete {db_path} "
                f"(and any -wal/-shm files next to it) and re-run ingest.",
                err=True,
            )
            raise typer.Exit(code=1) from None
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    routes_note = f" ({routes_skipped:,} skipped)" if routes_skipped else ""
    ecg_note = f" ({ecg_skipped:,} skipped)" if ecg_skipped else ""
    typer.echo(
        f"Ingested {counts.get('Record', 0):,} records, {counts.get('Workout', 0):,} workouts, "
        f"{counts.get('ActivitySummary', 0):,} activity summaries, "
        f"{clinical_count:,} clinical records, {routes_count:,} workout routes{routes_note}, "
        f"{ecg_count:,} ECG recordings{ecg_note} "
        f"in {elapsed:.1f}s -> {db_path}"
    )


@app.command()
def serve(
    host: str = typer.Option(settings.host, "--host"),
    port: int = typer.Option(settings.port, "--port"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """Runs the FastAPI server (use `fastapi dev` instead during active development)."""
    import uvicorn

    uvicorn.run("pomona.api.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
