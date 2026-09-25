"""Loads apple_health_export/electrocardiograms/*.csv (single-lead Apple Watch ECG
recordings) into ecg_recordings.

Each file is three blank-line-separated CSV blocks: metadata (Name, Date of Birth,
Recorded Date, Classification, Symptoms, Software Version, Device, Sample Rate), a
Lead/Unit pair, then one raw voltage sample (uV) per line -- ~15,360 lines for a ~30s
recording at 512Hz. Filenames (ecg_YYYY-MM-DD[_N].csv) aren't parsed for data, just kept
as source_file, matching workout_routes.source_file.
"""

import csv
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from pomona.ingest.dates import parse_apple_date

COLUMNS = [
    "recorded_date",
    "recorded_local_date",
    "classification",
    "symptoms",
    "software_version",
    "device",
    "sample_rate",
    "lead",
    "unit",
    "sample_count",
    "samples_json",
    "source_file",
]
INSERT_SQL = (
    f"INSERT INTO ecg_recordings ({','.join(COLUMNS)}) VALUES ({','.join('?' * len(COLUMNS))})"
)


def _blocks(rows: list[list[str]]) -> Iterator[list[list[str]]]:
    """Splits CSV rows into blank-line-separated blocks. csv.reader yields [] for a blank
    line, so a block boundary is any [] row (one or more in a row, e.g. between the header
    block and the Lead/Unit block there may be exactly one).
    """
    i = 0
    n = len(rows)
    while i < n:
        block = []
        while i < n and rows[i]:
            block.append(rows[i])
            i += 1
        if block:
            yield block
        while i < n and not rows[i]:
            i += 1


def _row_dict(rows: list[list[str]]) -> dict[str, str]:
    return {row[0]: (row[1] if len(row) > 1 else "") for row in rows}


def _parse_ecg_csv(path: Path) -> tuple:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    block_iter = _blocks(rows)
    meta = _row_dict(next(block_iter))
    lead_meta = _row_dict(next(block_iter))
    samples = [float(row[0]) for row in next(block_iter)]
    if not samples:
        raise ValueError("no samples")

    recorded_epoch, recorded_local = parse_apple_date(meta["Recorded Date"])
    sample_rate = float(meta["Sample Rate"].split()[0])

    return (
        recorded_epoch,
        recorded_local,
        meta.get("Classification") or None,
        meta.get("Symptoms") or None,
        meta.get("Software Version") or None,
        meta.get("Device") or None,
        sample_rate,
        lead_meta.get("Lead") or None,
        lead_meta.get("Unit") or None,
        len(samples),
        json.dumps(samples, separators=(",", ":")),
        path.name,
    )


def load_ecg_recordings(conn: sqlite3.Connection, ecg_dir: Path) -> tuple[int, int]:
    """Loads every *.csv ECG recording in ecg_dir into ecg_recordings. Drop-and-reload.

    Returns (loaded, skipped). A missing ecg_dir is a no-op ((0, 0), leaves existing rows
    alone) -- same as load_workout_routes/load_clinical_records. A file that fails to parse
    (missing Recorded Date/Sample Rate, a non-numeric sample, an empty sample block) is
    skipped and counted, not fatal: this whole ingest runs inside one transaction alongside
    export.xml and the other side-loaders, so one bad file must not discard everything else
    already loaded.
    """
    if not ecg_dir.exists():
        return 0, 0
    conn.execute("DELETE FROM ecg_recordings")

    rows = []
    skipped = 0
    for path in sorted(ecg_dir.glob("*.csv")):
        try:
            rows.append(_parse_ecg_csv(path))
        except (KeyError, ValueError, StopIteration):
            skipped += 1
            continue

    conn.executemany(INSERT_SQL, rows)
    return len(rows), skipped
