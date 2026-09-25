"""Loads apple_health_export/workout-routes/*.gpx (per-workout GPS tracks) into workout_routes.

Each file is one `<trk>` of one or more `<trkseg>` point sequences logged during an outdoor
workout -- Apple starts a new `<trkseg>` whenever GPS recording resumes after a pause (a paused
run, a stopped-and-restarted walk), so a file's segments can be spatially disconnected from each
other. Segment boundaries are kept through to storage and rendering rather than flattened into
one point list, so the map never draws a false straight line across a pause.

GPX filenames don't reference a workout id, so each route is matched to its `workouts` row by
time-range overlap (the route's own first/last `<time>` across all segments against
`workouts.start_date`/`end_date`) rather than by filename or file order.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from pomona.ingest.dates import parse_fhir_datetime

NS = {"gpx": "http://www.topografix.com/GPX/1/1"}

COLUMNS = [
    "workout_id",
    "start_date",
    "end_date",
    "start_local_date",
    "point_count",
    "points_json",
    "source_file",
]
INSERT_SQL = (
    f"INSERT INTO workout_routes ({','.join(COLUMNS)}) VALUES ({','.join('?' * len(COLUMNS))})"
)

# Closest-start-wins: picks the workout whose start_date is nearest the route's own start,
# among workouts whose time window overlaps the route's at all.
MATCH_WORKOUT_SQL = """
    SELECT id, start_local_date FROM workouts
    WHERE start_date <= ? AND end_date >= ?
    ORDER BY ABS(start_date - ?)
    LIMIT 1
"""


def _parse_segments(gpx_path: Path) -> tuple[list[list[list[float]]], int | None, int | None]:
    root = ET.parse(gpx_path).getroot()
    segments: list[list[list[float]]] = []
    start_epoch: int | None = None
    end_epoch: int | None = None
    for trkseg in root.findall(".//gpx:trkseg", NS):
        points: list[list[float]] = []
        for trkpt in trkseg.findall("gpx:trkpt", NS):
            lat = trkpt.get("lat")
            lon = trkpt.get("lon")
            if lat is None or lon is None:
                continue
            points.append([float(lat), float(lon)])
            time_el = trkpt.find("gpx:time", NS)
            epoch = parse_fhir_datetime(time_el.text) if time_el is not None else None
            if epoch is not None:
                if start_epoch is None:
                    start_epoch = epoch
                end_epoch = epoch
        if points:
            segments.append(points)
    return segments, start_epoch, end_epoch


def load_workout_routes(conn: sqlite3.Connection, routes_dir: Path) -> tuple[int, int]:
    """Loads every *.gpx route in routes_dir into workout_routes. Drop-and-reload.

    Returns (loaded, skipped). A missing routes_dir is a no-op ((0, 0), leaves existing rows
    alone) -- same as load_clinical_records. A file that fails to parse (corrupt XML, a
    non-numeric lat/lon) or has no usable points/timestamps is skipped and counted, not
    fatal: this whole ingest runs inside one transaction alongside export.xml and
    clinical-records, so one bad route file must not discard everything else already loaded
    (see ADR-0003, where an unhandled per-row error did exactly that to clinical_records).
    """
    if not routes_dir.exists():
        return 0, 0
    conn.execute("DELETE FROM workout_routes")

    rows = []
    skipped = 0
    for path in sorted(routes_dir.glob("*.gpx")):
        try:
            segments, start_epoch, end_epoch = _parse_segments(path)
        except (ET.ParseError, ValueError):
            skipped += 1
            continue
        if not segments or start_epoch is None or end_epoch is None:
            skipped += 1
            continue

        match = conn.execute(MATCH_WORKOUT_SQL, [end_epoch, start_epoch, start_epoch]).fetchone()
        if match:
            workout_id, start_local_date = match["id"], match["start_local_date"]
        else:
            workout_id = None
            # GPX <time> carries no UTC offset, unlike export.xml's own date strings, so
            # there's no way to derive the *actual* local date a route with no matching
            # workout happened on. The ingest machine's own local timezone is a closer guess
            # than UTC for this app's use case (run on the machine where you live), though
            # still wrong if you're ingesting while travelling.
            start_local_date = datetime.fromtimestamp(start_epoch).date().isoformat()

        rows.append(
            (
                workout_id,
                start_epoch,
                end_epoch,
                start_local_date,
                sum(len(seg) for seg in segments),
                json.dumps(segments, separators=(",", ":")),
                path.name,
            )
        )

    conn.executemany(INSERT_SQL, rows)
    return len(rows), skipped
