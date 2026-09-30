"""ECG recordings: the list, and one recording's downsampled waveform."""

import json

from fastapi import APIRouter, HTTPException, Query

from pomona.api.dependencies import DbDep
from pomona.api.query import where_clause
from pomona.waveform import downsample_minmax

router = APIRouter(prefix="/api", tags=["ecg"])


@router.get("/ecg")
def ecg_recordings(conn: DbDep, start: str | None = None, end: str | None = None) -> list[dict]:
    """Light list of ECG recordings -- no samples_json, unlike /api/routes' segments. Each
    recording's raw samples are a fixed ~100-150KB regardless of range width, and only the
    one selected recording is ever charted at a time, so inlining every recording's waveform
    into a range-filtered list would bloat the payload for data that's never rendered. See
    /api/ecg/{recording_id} for the downsampled waveform of a single recording.
    """
    where_sql, params = where_clause("recorded_local_date", start, end)
    rows = conn.execute(
        f"""
        SELECT id, recorded_date, recorded_local_date, classification, symptoms,
               sample_rate, lead, device, sample_count
        FROM ecg_recordings
        {where_sql}
        ORDER BY recorded_date DESC
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


@router.get("/ecg/{recording_id}")
def ecg_recording(
    conn: DbDep,
    recording_id: int,
    max_points: int = Query(2000, ge=100, le=10000),
) -> dict:
    row = conn.execute("SELECT * FROM ecg_recordings WHERE id = ?", [recording_id]).fetchone()
    if row is None:
        raise HTTPException(404, f"No ECG recording with id {recording_id}")

    samples = json.loads(row["samples_json"])
    sample_rate = row["sample_rate"]
    points = [
        {"t": index / sample_rate, "value": value}
        for index, value in downsample_minmax(samples, max_points)
    ]
    return {
        "id": row["id"],
        "recorded_date": row["recorded_date"],
        "recorded_local_date": row["recorded_local_date"],
        "classification": row["classification"],
        "symptoms": row["symptoms"],
        "software_version": row["software_version"],
        "device": row["device"],
        "sample_rate": sample_rate,
        "lead": row["lead"],
        "unit": row["unit"],
        "sample_count": row["sample_count"],
        "points": points,
    }
