import sqlite3
from pathlib import Path

from tqdm import tqdm

from pomona.ingest.dates import parse_apple_date
from pomona.ingest.xml_parser import count_elements, iter_health_elements

BATCH_SIZE = 10_000

RECORD_COLUMNS = [
    "type",
    "value_text",
    "value_num",
    "unit",
    "source_name",
    "source_version",
    "device",
    "creation_date",
    "start_date",
    "end_date",
    "start_local_date",
]
WORKOUT_COLUMNS = [
    "activity_type",
    "duration",
    "duration_unit",
    "total_distance",
    "total_distance_unit",
    "total_energy_burned",
    "total_energy_burned_unit",
    "source_name",
    "source_version",
    "device",
    "creation_date",
    "start_date",
    "end_date",
    "start_local_date",
]
ACTIVITY_SUMMARY_COLUMNS = [
    "date",
    "active_energy_burned",
    "active_energy_burned_goal",
    "active_energy_burned_unit",
    "apple_move_time",
    "apple_move_time_goal",
    "apple_exercise_time",
    "apple_exercise_time_goal",
    "apple_stand_hours",
    "apple_stand_hours_goal",
]


def _insert_sql(table: str, columns: list[str], *, or_replace: bool = False) -> str:
    placeholders = ",".join("?" * len(columns))
    verb = "INSERT OR REPLACE INTO" if or_replace else "INSERT INTO"
    return f"{verb} {table} ({','.join(columns)}) VALUES ({placeholders})"


RECORD_SQL = _insert_sql("records", RECORD_COLUMNS)
WORKOUT_SQL = _insert_sql("workouts", WORKOUT_COLUMNS)
# activity_summaries.date is the primary key, and exports restored from a backup or merged
# across devices can repeat a day. OR REPLACE keeps the last entry for the day instead of
# aborting the transaction (and with it the entire ingest) on a duplicate.
ACTIVITY_SUMMARY_SQL = _insert_sql("activity_summaries", ACTIVITY_SUMMARY_COLUMNS, or_replace=True)


def _parse_value(raw: str | None) -> tuple[str | None, float | None]:
    if raw is None:
        return None, None
    try:
        return raw, float(raw)
    except ValueError:
        return raw, None


def _optional_float(attrib: dict[str, str], key: str) -> float | None:
    raw = attrib.get(key)
    return float(raw) if raw else None


def _optional_epoch(attrib: dict[str, str], key: str) -> int | None:
    raw = attrib.get(key)
    return parse_apple_date(raw)[0] if raw else None


def _record_row(attrib: dict[str, str]) -> tuple:
    start_epoch, start_local = parse_apple_date(attrib["startDate"])
    end_epoch, _ = parse_apple_date(attrib["endDate"])
    value_text, value_num = _parse_value(attrib.get("value"))
    return (
        attrib["type"],
        value_text,
        value_num,
        attrib.get("unit"),
        attrib.get("sourceName"),
        attrib.get("sourceVersion"),
        attrib.get("device"),
        _optional_epoch(attrib, "creationDate"),
        start_epoch,
        end_epoch,
        start_local,
    )


def _workout_row(attrib: dict[str, str]) -> tuple:
    start_epoch, start_local = parse_apple_date(attrib["startDate"])
    end_epoch, _ = parse_apple_date(attrib["endDate"])
    return (
        attrib["workoutActivityType"],
        _optional_float(attrib, "duration"),
        attrib.get("durationUnit"),
        _optional_float(attrib, "totalDistance"),
        attrib.get("totalDistanceUnit"),
        _optional_float(attrib, "totalEnergyBurned"),
        attrib.get("totalEnergyBurnedUnit"),
        attrib.get("sourceName"),
        attrib.get("sourceVersion"),
        attrib.get("device"),
        _optional_epoch(attrib, "creationDate"),
        start_epoch,
        end_epoch,
        start_local,
    )


def _activity_summary_row(attrib: dict[str, str]) -> tuple:
    return (
        attrib["dateComponents"],
        _optional_float(attrib, "activeEnergyBurned"),
        _optional_float(attrib, "activeEnergyBurnedGoal"),
        attrib.get("activeEnergyBurnedUnit"),
        _optional_float(attrib, "appleMoveTime"),
        _optional_float(attrib, "appleMoveTimeGoal"),
        _optional_float(attrib, "appleExerciseTime"),
        _optional_float(attrib, "appleExerciseTimeGoal"),
        _optional_float(attrib, "appleStandHours"),
        _optional_float(attrib, "appleStandHoursGoal"),
    )


def load_export_xml(
    conn: sqlite3.Connection, xml_path: Path, *, show_progress: bool = True
) -> dict[str, int]:
    """Streams export.xml into records/workouts/activity_summaries. Drop-and-reload.

    Runs inside whatever transaction the caller has open on `conn` (see cli.py) so
    the whole ingest is atomic: a crash partway through leaves the previous good
    database untouched.
    """
    totals = count_elements(xml_path) if show_progress else {}
    counts = {"Record": 0, "Workout": 0, "ActivitySummary": 0}

    conn.execute("DELETE FROM records")
    conn.execute("DELETE FROM workouts")
    conn.execute("DELETE FROM activity_summaries")

    record_batch: list[tuple] = []
    workout_batch: list[tuple] = []
    summary_batch: list[tuple] = []

    progress = tqdm(total=sum(totals.values()) or None, unit="el", disable=not show_progress)
    try:
        for tag, attrib in iter_health_elements(xml_path):
            if tag == "Record":
                record_batch.append(_record_row(attrib))
                if len(record_batch) >= BATCH_SIZE:
                    conn.executemany(RECORD_SQL, record_batch)
                    record_batch.clear()
            elif tag == "Workout":
                workout_batch.append(_workout_row(attrib))
                if len(workout_batch) >= BATCH_SIZE:
                    conn.executemany(WORKOUT_SQL, workout_batch)
                    workout_batch.clear()
            elif tag == "ActivitySummary":
                summary_batch.append(_activity_summary_row(attrib))
                if len(summary_batch) >= BATCH_SIZE:
                    conn.executemany(ACTIVITY_SUMMARY_SQL, summary_batch)
                    summary_batch.clear()
            counts[tag] += 1
            progress.update(1)
    finally:
        progress.close()

    if record_batch:
        conn.executemany(RECORD_SQL, record_batch)
    if workout_batch:
        conn.executemany(WORKOUT_SQL, workout_batch)
    if summary_batch:
        conn.executemany(ACTIVITY_SUMMARY_SQL, summary_batch)

    return counts
