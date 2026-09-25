"""Memory-safe streaming parser for Apple Health's export.xml.

export.xml can be 1.5GB+ with millions of <Record> elements, so this uses
iterparse rather than DOM parsing. Root DTD shape:
  HealthData(ExportDate, Me, (Record|Correlation|Workout|ActivitySummary|
                               ClinicalRecord|Audiogram|VisionPrescription)*)
Only Record/Workout/ActivitySummary are ingested (v1 scope). ClinicalRecord,
Audiogram, and VisionPrescription are skipped entirely, as are most non-Record
children nested inside other elements (MetadataEntry, WorkoutRoute,
WorkoutEvent). Correlation itself contributes nothing as a container (its own
attributes are never emitted) — but a <Record> nested inside a Correlation
(e.g. the systolic/diastolic pair inside a blood pressure Correlation) is
still emitted like any other Record, since matching is by tag name, not
nesting depth. That's deliberate: it captures those readings without any
Correlation-specific grouping logic.

Workout's <WorkoutStatistics> children ARE read, as a fallback only: modern
exports (watchOS 9+, this export included) no longer set totalEnergyBurned /
totalDistance as attributes directly on <Workout> -- that data moved into
per-metric <WorkoutStatistics type="..." sum="..." unit="..."/> children
instead. When a Workout has no inline totalEnergyBurned/totalDistance
attribute, its energy is backfilled from the ActiveEnergyBurned statistic and
its distance from whichever HKQuantityTypeIdentifierDistance* statistic is
present (Cycling, WalkingRunning, Swimming, ...). When a workout logs several
kinds of distance, only the ones sharing the first statistic's unit are summed
-- there's no unit conversion here, so adding yd to mi would be meaningless.
Rate-like statistics (HeartRate, RunningPower, ...) use average/minimum/maximum
rather than sum and are ignored.
"""

import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

RELEVANT_TAGS = {"Record", "Workout", "ActivitySummary"}

# All direct children of the HealthData root, per the embedded DTD. Used to know
# when it's safe to clear the root's accumulated child list without disturbing
# an element that's still being built (XML is well-nested, so a top-level tag's
# "end" event only fires once everything nested inside it has already closed).
TOP_LEVEL_TAGS = RELEVANT_TAGS | {
    "Correlation",
    "ClinicalRecord",
    "Audiogram",
    "VisionPrescription",
    "Me",
    "ExportDate",
}

ENERGY_STATISTIC_TYPE = "HKQuantityTypeIdentifierActiveEnergyBurned"
DISTANCE_STATISTIC_PREFIX = "HKQuantityTypeIdentifierDistance"


def _apply_workout_statistics_fallback(
    attrib: dict[str, str], sums: dict[str, float], units: dict[str, str]
) -> None:
    if "totalEnergyBurned" not in attrib and ENERGY_STATISTIC_TYPE in sums:
        attrib["totalEnergyBurned"] = str(sums[ENERGY_STATISTIC_TYPE])
        if ENERGY_STATISTIC_TYPE in units:
            attrib["totalEnergyBurnedUnit"] = units[ENERGY_STATISTIC_TYPE]

    if "totalDistance" not in attrib:
        distance_types = [t for t in sums if t.startswith(DISTANCE_STATISTIC_PREFIX)]
        if distance_types:
            # A workout can carry several distance statistics at once (a swim leg in yd
            # alongside a run leg in mi). Adding those together would produce a total that
            # means nothing under either label, and there's no unit conversion here to make
            # them comparable -- not even to decide which is "bigger". So: take the unit of
            # the first distance statistic logged, sum only the statistics that share it,
            # and ignore the rest. Identical to plain summing in the overwhelmingly common
            # case of a workout with a single kind of distance. A statistic can also arrive
            # with a sum but no unit at all; that's its own group, stored unlabelled rather
            # than borrowing another group's unit.
            unit = units.get(distance_types[0])
            total = sum(sums[t] for t in distance_types if units.get(t) == unit)
            attrib["totalDistance"] = str(total)
            if unit:
                attrib["totalDistanceUnit"] = unit


def iter_health_elements(xml_path: Path) -> Iterator[tuple[str, dict[str, str]]]:
    """Streams (tag, attrib) for each Record/Workout/ActivitySummary in export.xml."""
    context = ET.iterparse(xml_path, events=("start", "end"))
    _, root = next(context)  # first event is the root element's own start

    in_workout = False
    statistic_sums: dict[str, float] = {}
    statistic_units: dict[str, str] = {}

    for event, elem in context:
        if event == "start":
            if elem.tag == "Workout":
                in_workout = True
                statistic_sums = {}
                statistic_units = {}
            continue

        # event == "end"
        if elem.tag == "WorkoutStatistics" and in_workout:
            stat_type = elem.get("type")
            stat_sum = elem.get("sum")
            if stat_type and stat_sum is not None:
                statistic_sums[stat_type] = statistic_sums.get(stat_type, 0.0) + float(stat_sum)
                if unit := elem.get("unit"):
                    statistic_units[stat_type] = unit
            continue

        if elem.tag in RELEVANT_TAGS:
            attrib = dict(elem.attrib)
            if elem.tag == "Workout":
                in_workout = False
                _apply_workout_statistics_fallback(attrib, statistic_sums, statistic_units)
            yield elem.tag, attrib
        if elem.tag in TOP_LEVEL_TAGS:
            elem.clear()
            root.clear()


def count_elements(xml_path: Path) -> dict[str, int]:
    """Cheap approximate counts of each relevant tag, for a progress bar's total/ETA.

    A byte-scan, not a real parse — good enough for progress display; the actual
    ingest counts (used for verification) come from the real streaming parse.
    """
    tags = sorted(RELEVANT_TAGS)
    markers = [f"<{tag} ".encode() for tag in tags]
    counts = dict.fromkeys(tags, 0)
    chunk_size = 8 * 1024 * 1024
    with open(xml_path, "rb") as f:
        while chunk := f.read(chunk_size):
            for tag, marker in zip(tags, markers, strict=True):
                counts[tag] += chunk.count(marker)
    return counts
