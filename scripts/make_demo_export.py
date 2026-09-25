"""Generates a synthetic Apple Health export, so nothing here ever needs a real one.

Run it, ingest the result, and the whole app is populated: every metric group, workouts with
GPS tracks, activity rings, ECG recordings and clinical records. Nobody's actual health data
is involved -- the numbers come out of a seeded PRNG, and the person they describe doesn't
exist.

    uv run python scripts/make_demo_export.py
    uv run pomona ingest demo_health_export/export.xml --db data/demo.db
    POMONA_DB_PATH=data/demo.db uv run pomona serve

Into its own database on purpose: ingest is drop-and-reload, so the default path would replace a
real export you had already imported.

Why generate rather than commit the files: a year of plausible data is ~15MB of XML and a few
hundred GPX tracks, which is a lot of bytes to carry in a repo for something reproducible from
a seed in a few seconds. The seed is fixed, so two people who run this get byte-identical
output and a screenshot stays comparable.

Deliberate properties, because a flat random series makes a bad demo and an easy bug:

- **Shape, not noise.** Values follow a weekday/weekend split and a slow seasonal drift with
  noise on top, so the charts have something to show and bucketing by week or month visibly
  differs from bucketing by day.
- **Gaps.** A handful of days have no data at all, and one stretch is a low-activity week.
  Charts, streaks and "days closed" have to cope with missing days, and they can't be shown to
  cope if nothing is missing.
- **Two sources.** iPhone and Apple Watch both log steps and distance, overlapping in the
  morning, which is exactly what the dedup layer exists for -- a naive SUM over this export
  reports too many steps, and that's the point.
- **A week in another timezone.** Seven days are written at a different UTC offset, so
  `start_local_date` bucketing is exercised rather than assumed.
- **Percentages as fractions.** SpO2 and the gait percentages are written as 0-1 under a "%"
  unit, which is what Apple does and what the frontend's x100 display rule reads.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import quoteattr

# Home offset, and the one week spent somewhere else. Written into every timestamp, since
# that's how Apple's export carries local time -- there is no separate timezone field.
HOME_OFFSET = "-0700"
TRIP_OFFSET = "+0200"
TRIP_LENGTH = 7

# Everything irregular is placed as a fraction of the span, never as a fixed day index. A
# constant falls outside a short `--days` and silently removes the very property the README
# promises -- which is how three separate features here ended up absent from a 30-day run.
TRIP_START_FRACTION = 0.3
GAP_FRACTIONS = (0.10, 0.35, 0.72)
# One of the gaps is two days long, and that is the only way any day ends up with no records at
# all: a single skipped day still receives the tail of the previous night's sleep, which starts
# at ~22:00 and runs past midnight. Adjacency has to be constructed rather than hoped for -- with
# four independent fractions the 400-day default produced zero truly empty days while a 30-day
# run produced one, purely by where the rounding landed.
GAP_PAIR_FRACTION = 0.55
QUIET_WEEK_FRACTION = 0.5
QUIET_WEEK_LENGTH = 9


def span_day(fraction: float, total: int) -> int:
    """A day index at `fraction` through the span, never the first or last day.

    Kept off both ends because the endpoints carry meaning: the last day is what --end-date
    promises and what DataFreshness reports, and an empty first day would just shorten the span
    rather than read as a gap in it.
    """
    return min(max(1, int(total * fraction)), max(1, total - 2))


IPHONE = ("iPhone", "18.1")
WATCH = ("Apple Watch", "11.1")

# Somewhere generic and recognisable, so the tracks read as a plausible city loop with the
# basemap switched on. Not anybody's neighbourhood.
ROUTE_ORIGIN = (37.7749, -122.4194)

# Dropped in the output directory so a re-run can tell its own output from somebody's real
# export. Route filenames carry a workout time and ECG filenames a date, so changing --seed,
# --days or --end-date renames most of them: without clearing first, two runs' files pile up and
# the leftovers match no workout, importing as routes bound to nothing and dated by the ingest
# machine's timezone. Clearing a directory is also the kind of thing that should refuse to guess.
MARKER = ".pomona-demo-export"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("demo_health_export"),
        help="Directory to write the export into (default: demo_health_export)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=400,
        help="How many days of history to generate (default: 400, so the 1-year range is full)",
    )
    parser.add_argument(
        "--end-date",
        type=lambda s: date.fromisoformat(s),
        default=date.today(),
        help="Last day of data, YYYY-MM-DD (default: today, so the short ranges aren't empty). "
        "Pin it to keep screenshots comparable across runs.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260924,
        help="PRNG seed; the same seed gives byte-identical output (default: 20260924)",
    )
    return parser.parse_args()


def prepare_output_dir(out: Path) -> None:
    """Empties a directory this script wrote before, and refuses to touch anything else.

    The refusal is the important half. `--out apple_health_export` would otherwise overwrite a
    real export's export.xml, which is the directory-level version of pointing `ingest` at the
    default database: one flag, no confirmation, and the thing it replaces took an hour to get
    out of the Health app.
    """
    if not out.exists():
        return
    if any(out.iterdir()) and not (out / MARKER).exists():
        raise SystemExit(
            f"{out} already has files in it and wasn't written by this script "
            f"(no {MARKER}). Refusing to touch it -- pass --out somewhere else, or delete it "
            f"yourself if you're sure."
        )
    # Generated filenames encode a date or a time, so stale ones from an earlier --seed or
    # --days would survive a rewrite and import as real data.
    for name in ("workout-routes", "electrocardiograms", "clinical-records"):
        directory = out / name
        if directory.is_dir():
            for path in directory.iterdir():
                if path.is_file():
                    path.unlink()


def hk(when: datetime, offset: str) -> str:
    """Apple's timestamp format: "2026-09-24 08:05:00 -0700"."""
    return f"{when:%Y-%m-%d %H:%M:%S} {offset}"


def attrs(pairs: dict[str, object]) -> str:
    """XML attributes, skipping any whose value is None so callers can pass them freely."""
    return " ".join(
        f"{key}={quoteattr(str(value))}" for key, value in pairs.items() if value is not None
    )


def seasonal(day_index: int, total: int, amplitude: float) -> float:
    """One slow cycle across the whole span, so a year of data drifts instead of sitting flat."""
    return amplitude * math.sin(2 * math.pi * day_index / max(total, 1))


class DayShape:
    """The per-day multipliers every metric reads, so they move together the way real ones do.

    A day where the steps are high and the resting heart rate is also high would look wrong to
    anyone who has seen their own data. One shape, shared, keeps them coherent.
    """

    def __init__(self, day: date, day_index: int, total: int, rng: random.Random) -> None:
        self.day = day
        self.offset = HOME_OFFSET
        self.is_weekend = day.weekday() >= 5
        # A quiet stretch: not zero, just visibly less. Something for a "last 90 days" view to
        # have a story in.
        quiet_start = span_day(QUIET_WEEK_FRACTION, total)
        quiet_length = max(3, round(QUIET_WEEK_LENGTH * total / 400))
        self.is_quiet_week = quiet_start <= day_index < quiet_start + quiet_length
        gaps = {span_day(fraction, total) for fraction in GAP_FRACTIONS}
        pair_start = span_day(GAP_PAIR_FRACTION, total)
        gaps.update({pair_start, pair_start + 1})
        # The day the offset changes is empty too, and not only for variety: see the comment on
        # TRIP_OFFSET's use below.
        gaps.add(span_day(TRIP_START_FRACTION, total))
        self.is_gap = day_index in gaps

        activity = 1.25 if self.is_weekend else 1.0
        activity *= 0.55 if self.is_quiet_week else 1.0
        activity *= 1 + seasonal(day_index, total, 0.18) + rng.gauss(0, 0.12)
        self.activity = max(0.25, activity)
        # Fitness improves slowly across the span; the quiet week interrupts it.
        self.fitness = 0.5 + 0.5 * day_index / max(total, 1) - (0.15 if self.is_quiet_week else 0)
        self.rng = rng


def steps_by_hour(shape: DayShape) -> list[tuple[int, int]]:
    """An hourly step profile: a commute, a lunch walk, an evening, and not much overnight."""
    profile = [
        0,
        0,
        0,
        0,
        0,
        20,
        180,
        620,
        900,
        520,
        430,
        480,
        780,
        540,
        430,
        470,
        610,
        880,
        1150,
        760,
        430,
        240,
        90,
        20,
    ]
    out = []
    for hour, base in enumerate(profile):
        if base == 0:
            continue
        value = int(base * shape.activity * shape.rng.uniform(0.6, 1.45))
        if value > 0:
            out.append((hour, value))
    return out


class ExportWriter:
    """Streams export.xml a line at a time. A year of records is too much to build in memory,
    and the ingester streams too, so this mirrors how it will be read."""

    def __init__(self, handle) -> None:
        self.handle = handle
        self.record_count = 0
        # Which local dates actually received a record. Counted rather than assumed, because a
        # skipped day isn't necessarily an empty one: a night's sleep starts at ~22:00 and its
        # later stages land after midnight, so the morning after a skipped day's neighbour still
        # has rows. That's what a real gap looks like, and the summary should say what happened
        # instead of what was intended.
        self.dates_with_records: set[str] = set()

    def line(self, text: str) -> None:
        self.handle.write(text + "\n")

    def record(
        self,
        type_: str,
        value: object,
        *,
        unit: str | None,
        start: datetime,
        end: datetime | None = None,
        offset: str,
        source: tuple[str, str] = WATCH,
        indent: str = " ",
    ) -> None:
        end = end or start
        name, version = source
        self.line(
            f"{indent}<Record "
            + attrs(
                {
                    "type": type_,
                    "sourceName": name,
                    "sourceVersion": version,
                    "unit": unit,
                    "creationDate": hk(end, offset),
                    "startDate": hk(start, offset),
                    "endDate": hk(end, offset),
                    "value": value,
                }
            )
            + "/>"
        )
        self.record_count += 1
        self.dates_with_records.add(start.strftime("%Y-%m-%d"))


def write_day_records(
    w: ExportWriter, shape: DayShape, day_index: int, total: int, is_last_day: bool
) -> int:
    """Every Record element for one day."""
    rng = shape.rng
    offset = shape.offset
    midnight = datetime(shape.day.year, shape.day.month, shape.day.day)

    def at(hour: int, minute: int = 0) -> datetime:
        return midnight + timedelta(hours=hour, minutes=minute)

    # --- Activity -----------------------------------------------------------------------
    hourly_steps = steps_by_hour(shape)
    for hour, value in hourly_steps:
        # Both devices log the morning, overlapping on purpose: this is the case dedup exists
        # for, and an export without it can't demonstrate that the totals are right.
        source = IPHONE if 7 <= hour <= 9 else WATCH
        w.record(
            "HKQuantityTypeIdentifierStepCount",
            value,
            unit="count",
            start=at(hour),
            end=at(hour, 59),
            offset=offset,
            source=source,
        )
        if 7 <= hour <= 9:
            w.record(
                "HKQuantityTypeIdentifierStepCount",
                int(value * rng.uniform(0.7, 0.95)),
                unit="count",
                start=at(hour, 5),
                end=at(hour, 55),
                offset=offset,
                source=WATCH,
            )

    day_steps = sum(value for _, value in hourly_steps)
    for hour, value in hourly_steps:
        w.record(
            "HKQuantityTypeIdentifierDistanceWalkingRunning",
            round(value * 0.00075, 4),
            unit="km",
            start=at(hour),
            end=at(hour, 59),
            offset=offset,
        )
        w.record(
            "HKQuantityTypeIdentifierActiveEnergyBurned",
            round(value * 0.042 + rng.uniform(0, 6), 2),
            unit="kcal",
            start=at(hour),
            end=at(hour, 59),
            offset=offset,
        )
    for hour in (2, 8, 14, 20):
        w.record(
            "HKQuantityTypeIdentifierBasalEnergyBurned",
            round(rng.uniform(370, 420), 1),
            unit="kcal",
            start=at(hour),
            # Clamped inside the day: the 20:00 block would otherwise end at 01:59 tomorrow,
            # which on the final day is a timestamp past --end-date. Harmless while every span
            # query keys on start_local_date, and not worth leaving to depend on that.
            end=at(min(hour + 5, 23), 59),
            offset=offset,
        )
    for hour in (7, 12, 18):
        w.record(
            "HKQuantityTypeIdentifierAppleExerciseTime",
            int(rng.uniform(4, 18) * shape.activity),
            unit="min",
            start=at(hour),
            end=at(hour, 59),
            offset=offset,
        )
        w.record(
            "HKQuantityTypeIdentifierAppleStandTime",
            int(rng.uniform(3, 14)),
            unit="min",
            start=at(hour),
            end=at(hour, 59),
            offset=offset,
        )
    if day_index in {span_day(f, total) for f in (0.25, 0.6, 0.85)}:
        # Cycling distance exists only inside cycling workouts otherwise, and a WorkoutStatistics
        # lands in `workouts` rather than `records` -- so the frontend's "Cycling distance" card
        # read empty while the Workouts tab showed rides. Found by the test below, not by looking.
        w.record(
            "HKQuantityTypeIdentifierDistanceCycling",
            round(rng.uniform(6.5, 24.0), 3),
            unit="km",
            start=at(17),
            end=at(18),
            offset=offset,
        )
    w.record(
        "HKQuantityTypeIdentifierFlightsClimbed",
        int(rng.uniform(2, 18) * shape.activity),
        unit="count",
        start=at(9),
        end=at(20),
        offset=offset,
    )
    w.record(
        "HKQuantityTypeIdentifierTimeInDaylight",
        int(rng.uniform(20, 180) * shape.activity),
        unit="min",
        start=at(9),
        end=at(19),
        offset=offset,
    )
    w.record(
        "HKQuantityTypeIdentifierPhysicalEffort",
        round(rng.uniform(1.8, 5.4), 2),
        unit="kcal/hr·kg",
        start=at(10),
        end=at(11),
        offset=offset,
    )
    # Stand hours, as the category type the frontend counts rather than charts.
    for hour in range(8, 22):
        stood = rng.random() < (0.85 if not shape.is_quiet_week else 0.55)
        w.record(
            "HKCategoryTypeIdentifierAppleStandHour",
            "HKCategoryValueAppleStandHourStood" if stood else "HKCategoryValueAppleStandHourIdle",
            unit=None,
            start=at(hour),
            end=at(hour + 1),
            offset=offset,
        )

    # --- Heart --------------------------------------------------------------------------
    for slot in range(30):
        hour = 6 + slot * 17 // 30
        # Resting-ish overnight and early, higher through the day, spiking around workouts.
        base = 58 + 14 * shape.activity * (0.4 + 0.6 * math.sin(math.pi * slot / 30))
        w.record(
            "HKQuantityTypeIdentifierHeartRate",
            round(base + rng.gauss(0, 5), 3),
            unit="count/min",
            start=at(hour, (slot * 7) % 60),
            offset=offset,
        )
    resting = round(62 - 6 * shape.fitness + rng.gauss(0, 1.6), 3)
    w.record(
        "HKQuantityTypeIdentifierRestingHeartRate",
        resting,
        unit="count/min",
        start=at(4),
        offset=offset,
    )
    w.record(
        "HKQuantityTypeIdentifierWalkingHeartRateAverage",
        round(resting + rng.uniform(22, 34), 3),
        unit="count/min",
        start=at(13),
        offset=offset,
    )
    for hour in (3, 4, 5):
        w.record(
            "HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
            round(38 + 18 * shape.fitness + rng.gauss(0, 7), 3),
            unit="ms",
            start=at(hour),
            offset=offset,
        )
    for hour in (3, 22):
        w.record(
            "HKQuantityTypeIdentifierRespiratoryRate",
            round(rng.uniform(13.5, 16.5), 3),
            unit="count/min",
            start=at(hour),
            offset=offset,
        )
    # Percentages are 0-1 fractions under a "%" unit, which is what Apple writes.
    for hour in (2, 4, 13, 21):
        w.record(
            "HKQuantityTypeIdentifierOxygenSaturation",
            round(rng.uniform(0.95, 0.995), 4),
            unit="%",
            start=at(hour),
            offset=offset,
        )
    if day_index % 7 == 0:
        w.record(
            "HKQuantityTypeIdentifierVO2Max",
            round(38 + 8 * shape.fitness + rng.gauss(0, 0.8), 3),
            unit="mL/min·kg",
            start=at(18),
            offset=offset,
        )

    # --- Mobility, gait, body, environment ----------------------------------------------
    w.record(
        "HKQuantityTypeIdentifierWalkingSpeed",
        round(rng.uniform(4.6, 5.6), 3),
        unit="km/hr",
        start=at(13),
        offset=offset,
    )
    w.record(
        "HKQuantityTypeIdentifierWalkingStepLength",
        round(rng.uniform(68, 78), 1),
        unit="cm",
        start=at(13),
        offset=offset,
    )
    w.record(
        "HKQuantityTypeIdentifierWalkingDoubleSupportPercentage",
        round(rng.uniform(0.25, 0.30), 4),
        unit="%",
        start=at(13),
        offset=offset,
    )
    w.record(
        "HKQuantityTypeIdentifierWalkingAsymmetryPercentage",
        round(rng.uniform(0.0, 0.035), 4),
        unit="%",
        start=at(13),
        offset=offset,
    )
    w.record(
        "HKQuantityTypeIdentifierStairAscentSpeed",
        round(rng.uniform(0.32, 0.46), 3),
        unit="m/s",
        start=at(9),
        offset=offset,
    )
    w.record(
        "HKQuantityTypeIdentifierStairDescentSpeed",
        round(rng.uniform(0.38, 0.55), 3),
        unit="m/s",
        start=at(18),
        offset=offset,
    )
    if day_index % 14 == 0:
        w.record(
            "HKQuantityTypeIdentifierAppleWalkingSteadiness",
            round(rng.uniform(0.72, 0.94), 4),
            unit="%",
            start=at(12),
            offset=offset,
        )
    if day_index % 3 == 0:
        # A slow, unremarkable drift, with the scale's usual jitter.
        w.record(
            "HKQuantityTypeIdentifierBodyMass",
            round(74.5 - 2.2 * day_index / max(total, 1) + rng.gauss(0, 0.35), 2),
            unit="kg",
            start=at(7, 15),
            offset=offset,
            source=IPHONE,
        )
    # Types the frontend has a card for that nothing else here writes. Each is rare in a real
    # export too, which is the point: an empty card in a demo reads as broken, not as "you have
    # never taken this measurement".
    if day_index == 0:
        # Height is measured once and then never again, so there is exactly one.
        w.record(
            "HKQuantityTypeIdentifierHeight",
            round(rng.uniform(1.70, 1.80), 3),
            unit="m",
            start=at(9),
            offset=offset,
            source=IPHONE,
        )
    # Span-relative, like everything else irregular here. `day_index % 90 == 30` looked fine and
    # emitted nothing at all for any span under 31 days -- the fourth instance of that mistake in
    # this file, which is what test_every_type_the_frontend_charts_has_data now exists to catch.
    if day_index in {span_day(0.2, total), span_day(0.8, total)}:
        w.record(
            "HKQuantityTypeIdentifierSixMinuteWalkTestDistance",
            round(rng.uniform(480, 620), 1),
            unit="m",
            start=at(11),
            offset=offset,
        )
    if day_index in {span_day(0.15, total), span_day(0.55, total), span_day(0.9, total)}:
        # A category type with no value, counted rather than averaged.
        w.record(
            "HKCategoryTypeIdentifierHighHeartRateEvent",
            "HKCategoryValueNotApplicable",
            unit=None,
            start=at(15),
            end=at(15, 12),
            offset=offset,
        )
    if day_index % 30 == 0:
        # Not an HKQuantityType at all -- the export writes the sleep goal under its own
        # HKDataType prefix, and the frontend charts it like a quantity.
        w.record(
            "HKDataTypeSleepDurationGoal",
            round(rng.uniform(7.0, 8.0), 2),
            unit="hr",
            start=at(6),
            offset=offset,
            source=IPHONE,
        )
    w.record(
        "HKQuantityTypeIdentifierAppleSleepingWristTemperature",
        round(rng.gauss(0, 0.35), 3),
        unit="degC",
        start=at(3),
        offset=offset,
    )
    for hour in (9, 17):
        w.record(
            "HKQuantityTypeIdentifierHeadphoneAudioExposure",
            round(rng.uniform(58, 78), 2),
            unit="dBASPL",
            start=at(hour),
            end=at(hour + 1),
            offset=offset,
        )
    w.record(
        "HKQuantityTypeIdentifierEnvironmentalAudioExposure",
        round(rng.uniform(45, 72), 2),
        unit="dBASPL",
        start=at(12),
        end=at(13),
        offset=offset,
    )
    for hour in (8, 11, 15, 19):
        w.record(
            "HKQuantityTypeIdentifierDietaryWater",
            round(rng.uniform(0.2, 0.5), 3),
            unit="L",
            start=at(hour),
            offset=offset,
            source=IPHONE,
        )

    # --- Sleep and mindfulness ----------------------------------------------------------
    # A night begins at ~22:00 and runs past midnight, which is what real sleep does and what
    # the aggregation has to handle. Skipped on the final day only: those later stages would
    # start after midnight and put records a day beyond the requested --end-date, making the
    # flag a lie and DataFreshness report a date that was never asked for.
    sleep_start = at(22, rng.randint(0, 50))
    # Totals 6-8.5 hours across the three stages. Worth stating as an intent: an earlier pass
    # summed to about 5.2 hours a night, which every chart rendered happily and which no reader
    # would believe.
    stages = [
        ("HKCategoryValueSleepAnalysisAsleepCore", rng.uniform(3.9, 4.9)),
        ("HKCategoryValueSleepAnalysisAsleepDeep", rng.uniform(0.8, 1.4)),
        ("HKCategoryValueSleepAnalysisAsleepREM", rng.uniform(1.3, 2.1)),
    ]
    cursor = sleep_start
    for value, hours in [] if is_last_day else stages:
        end = cursor + timedelta(hours=hours)
        w.record(
            "HKCategoryTypeIdentifierSleepAnalysis",
            value,
            unit=None,
            start=cursor,
            end=end,
            offset=offset,
        )
        cursor = end
    if rng.random() < 0.4:
        w.record(
            "HKCategoryTypeIdentifierMindfulSession",
            "HKCategoryValueNotApplicable",
            unit=None,
            start=at(7, 30),
            end=at(7, 42),
            offset=offset,
            source=IPHONE,
        )

    # --- Blood pressure, as the Correlation the export actually uses --------------------
    if day_index % 4 == 0:
        systolic = int(rng.gauss(119, 7))
        when = hk(at(7, 40), offset)
        w.line(
            " <Correlation "
            + attrs(
                {
                    "type": "HKCorrelationTypeIdentifierBloodPressure",
                    "sourceName": IPHONE[0],
                    "sourceVersion": IPHONE[1],
                    "creationDate": when,
                    "startDate": when,
                    "endDate": when,
                }
            )
            + ">"
        )
        for type_, value in (
            ("HKQuantityTypeIdentifierBloodPressureSystolic", systolic),
            (
                "HKQuantityTypeIdentifierBloodPressureDiastolic",
                int(systolic * 0.64 + rng.gauss(0, 3)),
            ),
        ):
            w.record(
                type_,
                value,
                unit="mmHg",
                start=at(7, 40),
                offset=offset,
                source=IPHONE,
                indent="  ",
            )
        w.line(" </Correlation>")

    return day_steps


# Outdoor types get a GPS track; the indoor ones deliberately don't, so the Routes tab has a
# reason to say "indoor workouts have no route to show" and mean it.
WORKOUT_KINDS = [
    ("HKWorkoutActivityTypeRunning", "km", 0.09, True),
    ("HKWorkoutActivityTypeWalking", "km", 0.05, True),
    ("HKWorkoutActivityTypeCycling", "km", 0.03, True),
    ("HKWorkoutActivityTypeTraditionalStrengthTraining", None, 0.0, False),
    ("HKWorkoutActivityTypeYoga", None, 0.0, False),
    ("HKWorkoutActivityTypeHighIntensityIntervalTraining", None, 0.0, False),
]


def write_workout(
    w: ExportWriter, shape: DayShape, day_index: int
) -> tuple[datetime, datetime, str] | None:
    """Writes one workout for the day, if there is one. Returns the window a route must fall in."""
    rng = shape.rng
    if rng.random() > (0.62 if not shape.is_quiet_week else 0.2):
        return None

    kind, distance_unit, km_per_min, outdoors = rng.choice(WORKOUT_KINDS)
    minutes = round(rng.uniform(22, 78), 1)
    midnight = datetime(shape.day.year, shape.day.month, shape.day.day)
    start = midnight + timedelta(hours=7 if not shape.is_weekend else 9, minutes=rng.randint(0, 50))
    end = start + timedelta(minutes=minutes)
    energy = round(minutes * rng.uniform(7.5, 11.5), 1)
    distance = round(minutes * km_per_min * rng.uniform(0.9, 1.1), 3) if km_per_min else None

    # Half the workouts use the modern format -- no inline totals, only nested
    # WorkoutStatistics -- because that is the shape watchOS 9+ writes and the parser has a
    # fallback for it that an export of only the old shape would never exercise.
    modern = day_index % 2 == 0
    header = {
        "workoutActivityType": kind,
        "duration": minutes,
        "durationUnit": "min",
        "sourceName": WATCH[0],
        "sourceVersion": WATCH[1],
        "creationDate": hk(end, shape.offset),
        "startDate": hk(start, shape.offset),
        "endDate": hk(end, shape.offset),
    }
    if not modern:
        header["totalEnergyBurned"] = energy
        header["totalEnergyBurnedUnit"] = "kcal"
        if distance is not None:
            header["totalDistance"] = distance
            header["totalDistanceUnit"] = distance_unit
    w.line(" <Workout " + attrs(header) + ">")

    def statistic(type_: str, **extra: object) -> None:
        w.line(
            "  <WorkoutStatistics "
            + attrs(
                {
                    "type": type_,
                    "startDate": hk(start, shape.offset),
                    "endDate": hk(end, shape.offset),
                    **extra,
                }
            )
            + "/>"
        )

    statistic("HKQuantityTypeIdentifierActiveEnergyBurned", sum=energy, unit="kcal")
    statistic("HKQuantityTypeIdentifierBasalEnergyBurned", sum=round(minutes * 1.2, 1), unit="kcal")
    if distance is not None:
        statistic(
            "HKQuantityTypeIdentifierDistanceWalkingRunning"
            if kind != "HKWorkoutActivityTypeCycling"
            else "HKQuantityTypeIdentifierDistanceCycling",
            sum=distance,
            unit=distance_unit,
        )
    statistic(
        "HKQuantityTypeIdentifierHeartRate",
        average=round(rng.uniform(128, 158), 1),
        minimum=round(rng.uniform(88, 104), 0),
        maximum=round(rng.uniform(168, 186), 0),
        unit="count/min",
    )
    if outdoors:
        w.line(
            "  <WorkoutRoute "
            + attrs(
                {
                    "sourceName": WATCH[0],
                    "sourceVersion": WATCH[1],
                    "creationDate": hk(end, shape.offset),
                    "startDate": hk(start, shape.offset),
                    "endDate": hk(end, shape.offset),
                }
            )
            + "/>"
        )
    w.line(" </Workout>")

    # Heart rate recovery only exists after a workout, which is the point of putting it here.
    w.record(
        "HKQuantityTypeIdentifierHeartRateRecoveryOneMinute",
        round(rng.uniform(18, 42), 1),
        unit="count/min",
        start=end,
        end=end + timedelta(minutes=1),
        offset=shape.offset,
    )
    if kind == "HKWorkoutActivityTypeRunning":
        for type_, value, unit in (
            ("HKQuantityTypeIdentifierRunningSpeed", round(rng.uniform(9.5, 13.5), 2), "km/hr"),
            ("HKQuantityTypeIdentifierRunningPower", round(rng.uniform(210, 310), 1), "W"),
            ("HKQuantityTypeIdentifierRunningStrideLength", round(rng.uniform(0.95, 1.25), 3), "m"),
            (
                "HKQuantityTypeIdentifierRunningGroundContactTime",
                round(rng.uniform(220, 280), 1),
                "ms",
            ),
            (
                "HKQuantityTypeIdentifierRunningVerticalOscillation",
                round(rng.uniform(6.5, 10.5), 2),
                "cm",
            ),
        ):
            w.record(
                type_, value, unit=unit, start=start + timedelta(minutes=5), offset=shape.offset
            )

    return (start, end, shape.offset) if outdoors else None


def write_gpx(path: Path, start: datetime, end: datetime, offset: str, rng: random.Random) -> None:
    """One GPX track for a workout window.

    Times are written in UTC, which is what Apple does, so the offset has to be undone here --
    the ingester matches a route to a workout by overlapping instants, and a track written in
    local time would attach to the wrong workout or to none.
    """
    sign = 1 if offset[0] == "-" else -1
    utc_shift = timedelta(hours=sign * int(offset[1:3]), minutes=sign * int(offset[3:5]))
    duration = (end - start).total_seconds()
    points = max(40, int(duration / 12))

    # A rough loop back to where it started, with a heading that wanders. Not a straight line,
    # and not a circle either.
    lat, lon = (
        ROUTE_ORIGIN[0] + rng.uniform(-0.02, 0.02),
        ROUTE_ORIGIN[1] + rng.uniform(-0.02, 0.02),
    )
    heading = rng.uniform(0, 2 * math.pi)
    elevation = rng.uniform(4, 60)

    # One pause partway, so the multi-<trkseg> case is in the demo rather than only in tests.
    pause_at = points // 2 if rng.random() < 0.35 else None

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="Apple Health Export"'
        ' xmlns="http://www.topografix.com/GPX/1/1">',
        "  <metadata>",
        f"    <time>{(end + utc_shift):%Y-%m-%dT%H:%M:%SZ}</time>",
        "  </metadata>",
        "  <trk>",
        f"    <name>Route {start:%Y-%m-%d %I.%M%p}</name>",
        "    <trkseg>",
    ]
    for index in range(points):
        heading += rng.gauss(0, 0.28) + (0.06 if index > points * 0.5 else -0.06)
        step = rng.uniform(0.00012, 0.00028)
        lat += step * math.cos(heading)
        lon += step * math.sin(heading) * 1.26
        elevation += rng.gauss(0, 0.6)
        when = start + timedelta(seconds=duration * index / points) + utc_shift
        lines.append(
            f'      <trkpt lon="{lon:.6f}" lat="{lat:.6f}">'
            f"<ele>{elevation:.1f}</ele><time>{when:%Y-%m-%dT%H:%M:%SZ}</time></trkpt>"
        )
        if index == pause_at:
            lines.extend(["    </trkseg>", "    <trkseg>"])
    lines.extend(["    </trkseg>", "  </trk>", "</gpx>", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


# Weighted the way a real set is -- mostly sinus rhythm -- but interleaved rather than sorted,
# because a short `--days` only reaches the first few and would otherwise show one classification
# repeated. The ECG list styles each of these differently, so all four want to be visible.
ECG_CLASSIFICATIONS = [
    "Sinus Rhythm",
    "Sinus Rhythm",
    "Atrial Fibrillation",
    "Sinus Rhythm",
    "Inconclusive, Poor Recording",
    "Sinus Rhythm",
    "Inconclusive, High Heart Rate",
]


def ecg_samples(bpm: float, seconds: int, rate: int, rng: random.Random) -> list[float]:
    """A single-lead trace in µV, built from P-QRS-T bumps rather than noise.

    It has to actually look like an ECG: the ECG page draws it on paper-grid axes at a fixed
    mm/mV, so a flat or random series would make that page meaningless as a demo.
    """

    def bump(t: float, centre: float, width: float, height: float) -> float:
        return height * math.exp(-(((t - centre) / width) ** 2))

    beat_length = 60.0 / bpm
    out = []
    for index in range(seconds * rate):
        t = index / rate
        phase = t % beat_length
        value = (
            bump(phase, 0.16, 0.024, 90)  # P
            + bump(phase, 0.30, 0.008, -110)  # Q
            + bump(phase, 0.32, 0.009, 1020)  # R
            + bump(phase, 0.35, 0.011, -230)  # S
            + bump(phase, 0.54, 0.042, 220)  # T
        )
        # Mains hum and a slow wander, which every real recording has.
        value += 6 * math.sin(2 * math.pi * 60 * t) + 14 * math.sin(2 * math.pi * 0.23 * t)
        out.append(round(value + rng.gauss(0, 7), 3))
    return out


def write_ecg(path: Path, when: datetime, classification: str, rng: random.Random) -> None:
    rate = 512
    bpm = rng.uniform(52, 74) if "High Heart Rate" not in classification else rng.uniform(112, 138)
    header = [
        "Name,Demo Person",
        'Date of Birth,"Jan 1, 1990"',
        f"Recorded Date,{hk(when, HOME_OFFSET)}",
        f"Classification,{classification}",
        "Symptoms,",
        "Software Version,2.1",
        'Device,"Watch7,2"',
        f"Sample Rate,{rate} hertz",
        "",
        "Lead,Lead I",
        "Unit,µV",
        "",
    ]
    samples = ecg_samples(bpm, 30, rate, rng)
    path.write_text("\n".join(header + [str(v) for v in samples]) + "\n", encoding="utf-8")


def write_clinical_records(directory: Path, end: date, rng: random.Random) -> int:
    """A small FHIR set: demographics, two conditions, immunizations and two lab panels.

    Every value is invented. Only the resource types the app ingests are written -- anything
    else is dropped at ingest anyway (ADR-0005), and generating it would mean inventing data
    in the repo for no gain.
    """
    directory.mkdir(parents=True, exist_ok=True)
    written: list[tuple[str, dict]] = []

    written.append(
        (
            "Patient-1",
            {
                "resourceType": "Patient",
                "id": "demo-patient",
                "name": [{"given": ["Demo"], "family": "Person"}],
                "gender": "unknown",
                "birthDate": "1990-01-01",
            },
        )
    )

    for index, (text, code, onset) in enumerate(
        [
            ("Essential hypertension", "I10", "2021-03-14"),
            ("Vitamin D deficiency", "E55.9", "2023-11-02"),
        ],
        start=1,
    ):
        written.append(
            (
                f"Condition-{index}",
                {
                    "resourceType": "Condition",
                    "id": f"demo-cond-{index}",
                    "clinicalStatus": {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                                "code": "active",
                            }
                        ]
                    },
                    "code": {
                        "text": text,
                        "coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": code}],
                    },
                    "subject": {"reference": "Patient/demo-patient"},
                    "onsetDateTime": onset,
                    "recordedDate": onset,
                },
            )
        )

    for index, (text, offset_days) in enumerate(
        [
            ("Influenza, seasonal, injectable", 330),
            ("Tdap", 900),
            ("COVID-19, mRNA", 250),
            ("Pneumococcal conjugate", 1400),
        ],
        start=1,
    ):
        occurred = end - timedelta(days=offset_days)
        written.append(
            (
                f"Immunization-{index}",
                {
                    "resourceType": "Immunization",
                    "id": f"demo-imm-{index}",
                    "status": "completed",
                    "vaccineCode": {"text": text},
                    "patient": {"reference": "Patient/demo-patient"},
                    "occurrenceDateTime": f"{occurred.isoformat()}T10:00:00{HOME_OFFSET[:3]}:00",
                    "route": {"text": "Intramuscular"},
                    "site": {"text": "Left arm"},
                },
            )
        )

    # Two panels, a year apart, so the clinical page has a repeated measure to show.
    panel = [
        ("LDL Cholesterol", "13457-7", 96, "mg/dL", 0, 99),
        ("HDL Cholesterol", "2085-9", 58, "mg/dL", 40, 200),
        ("Triglycerides", "2571-8", 104, "mg/dL", 0, 149),
        ("Glucose", "2345-7", 91, "mg/dL", 70, 99),
        ("Hemoglobin A1c", "4548-4", 5.3, "%", 4.0, 5.6),
        ("TSH", "3016-3", 2.1, "uIU/mL", 0.45, 4.5),
        ("Vitamin D, 25-Hydroxy", "1989-3", 27, "ng/mL", 30, 100),
        ("Creatinine", "2160-0", 0.94, "mg/dL", 0.6, 1.3),
    ]
    observation_index = 0
    for panel_number, days_ago in enumerate((30, 395), start=1):
        drawn = end - timedelta(days=days_ago)
        effective = f"{drawn.isoformat()}T09:00:00{HOME_OFFSET[:3]}:00"
        references = []
        for name, loinc, centre, unit, low, high in panel:
            observation_index += 1
            value = round(centre * rng.uniform(0.9, 1.1), 2 if centre < 10 else 0)
            written.append(
                (
                    f"Observation-{observation_index}",
                    {
                        "resourceType": "Observation",
                        "id": f"demo-obs-{observation_index}",
                        "status": "final",
                        "category": [{"text": "Laboratory"}],
                        "code": {
                            "text": name,
                            "coding": [
                                {"system": "http://loinc.org", "code": loinc, "display": name}
                            ],
                        },
                        "subject": {"reference": "Patient/demo-patient"},
                        "effectiveDateTime": effective,
                        "valueQuantity": {"value": value, "unit": unit},
                        "referenceRange": [
                            {
                                "low": {"value": low, "unit": unit},
                                "high": {"value": high, "unit": unit},
                                "text": f"{low}-{high} {unit}",
                            }
                        ],
                    },
                )
            )
            references.append({"reference": f"Observation/demo-obs-{observation_index}"})

        # A blood pressure as a component panel, which is the case with no top-level value --
        # the clinical page renders it as "118/76 mmHg" and would show "—" if it regressed.
        observation_index += 1
        systolic = int(rng.gauss(120, 6))
        written.append(
            (
                f"Observation-{observation_index}",
                {
                    "resourceType": "Observation",
                    "id": f"demo-obs-{observation_index}",
                    "status": "final",
                    "category": [{"text": "Vital Signs"}],
                    "code": {
                        "text": "Blood pressure panel",
                        "coding": [{"system": "http://loinc.org", "code": "85354-9"}],
                    },
                    "subject": {"reference": "Patient/demo-patient"},
                    "effectiveDateTime": effective,
                    "component": [
                        {
                            "code": {
                                "text": "Systolic blood pressure",
                                "coding": [{"system": "http://loinc.org", "code": "8480-6"}],
                            },
                            "valueQuantity": {"value": systolic, "unit": "mm[Hg]"},
                            "referenceRange": [{"high": {"value": 120, "unit": "mm[Hg]"}}],
                        },
                        {
                            "code": {
                                "text": "Diastolic blood pressure",
                                "coding": [{"system": "http://loinc.org", "code": "8462-4"}],
                            },
                            "valueQuantity": {"value": int(systolic * 0.64), "unit": "mm[Hg]"},
                            "referenceRange": [{"high": {"value": 80, "unit": "mm[Hg]"}}],
                        },
                    ],
                },
            )
        )
        references.append({"reference": f"Observation/demo-obs-{observation_index}"})

        written.append(
            (
                f"DiagnosticReport-{panel_number}",
                {
                    "resourceType": "DiagnosticReport",
                    "id": f"demo-diag-{panel_number}",
                    "status": "final",
                    "code": {
                        "text": "Comprehensive metabolic and lipid panel",
                        "coding": [{"system": "http://loinc.org", "code": "24331-1"}],
                    },
                    "subject": {"reference": "Patient/demo-patient"},
                    "effectiveDateTime": effective,
                    "issued": effective,
                    "result": references,
                },
            )
        )

    for name, resource in written:
        (directory / f"{name}.json").write_text(
            json.dumps(resource, indent=2) + "\n", encoding="utf-8"
        )
    return len(written)


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)
    out = args.out
    routes_dir = out / "workout-routes"
    ecg_dir = out / "electrocardiograms"
    prepare_output_dir(out)
    for directory in (out, routes_dir, ecg_dir):
        directory.mkdir(parents=True, exist_ok=True)
    (out / MARKER).write_text(
        "Written by scripts/make_demo_export.py. Synthetic data; safe to delete.\n",
        encoding="utf-8",
    )

    start_day = args.end_date - timedelta(days=args.days - 1)
    exported_at = datetime(args.end_date.year, args.end_date.month, args.end_date.day, 9)
    trip_start = start_day + timedelta(days=span_day(TRIP_START_FRACTION, args.days))
    route_windows: list[tuple[datetime, datetime, str]] = []
    summaries: list[str] = []
    gap_days = 0

    export_xml = out / "export.xml"
    with export_xml.open("w", encoding="utf-8") as handle:
        w = ExportWriter(handle)
        w.line('<?xml version="1.0" encoding="UTF-8"?>')
        w.line('<HealthData locale="en_US">')
        w.line(
            " <!-- Synthetic data from scripts/make_demo_export.py. Not a real person's export. -->"
        )
        w.line(" <ExportDate " + attrs({"value": hk(exported_at, HOME_OFFSET)}) + "/>")
        w.line(
            " <Me "
            + attrs(
                {
                    "HKCharacteristicTypeIdentifierDateOfBirth": "1990-01-01",
                    "HKCharacteristicTypeIdentifierBiologicalSex": "HKBiologicalSexNotSet",
                }
            )
            + "/>"
        )

        for day_index in range(args.days):
            day = start_day + timedelta(days=day_index)
            shape = DayShape(day, day_index, args.days, rng)
            if trip_start <= day < trip_start + timedelta(days=TRIP_LENGTH):
                # The first day of this window is a gap day (see DayShape), which is load-bearing
                # rather than decorative. Every day is written at local 05:00-23:59, so changing
                # the offset from -0700 to +0200 without an empty day between rewinds that day's
                # UTC instants by nine hours, straight into the previous evening's. The dedup
                # layer reads the collision as two devices logging the same window and discards
                # one side: measured at 27% of a day's steps dropped against the ~15% the
                # intentional iPhone/Watch overlap costs elsewhere. A day in transit having no
                # data is also just what happens.
                shape.offset = TRIP_OFFSET
            if shape.is_gap:
                # No records at all: the app has to render a missing day rather than a zero.
                gap_days += 1
                continue

            day_steps = write_day_records(
                w, shape, day_index, args.days, is_last_day=day_index == args.days - 1
            )
            window = write_workout(w, shape, day_index)
            if window:
                route_windows.append(window)

            # Rings: the Move goal is personal so it comes from the export, and Exercise/Stand
            # use the stock goals the frontend falls back to anyway.
            energy = round(day_steps * 0.042 + rng.uniform(80, 260), 0)
            summaries.append(
                " <ActivitySummary "
                + attrs(
                    {
                        "dateComponents": day.isoformat(),
                        "activeEnergyBurned": energy,
                        "activeEnergyBurnedGoal": 520,
                        "activeEnergyBurnedUnit": "kcal",
                        "appleMoveTime": 0,
                        "appleMoveTimeGoal": 0,
                        "appleExerciseTime": min(90, int(rng.uniform(8, 55) * shape.activity)),
                        "appleExerciseTimeGoal": 30,
                        "appleStandHours": min(
                            14, int(rng.uniform(7, 14) * (0.7 if shape.is_quiet_week else 1))
                        ),
                        "appleStandHoursGoal": 12,
                    }
                )
                + "/>"
            )

        for line in summaries:
            w.line(line)
        w.line("</HealthData>")
        record_count = w.record_count
        empty_days = sum(
            1
            for offset_days in range(args.days)
            if (start_day + timedelta(days=offset_days)).isoformat() not in w.dates_with_records
        )

    for start, end, offset in route_windows:
        name = f"route_{start:%Y-%m-%d_%I.%M%p}".replace("AM", "am").replace("PM", "pm")
        write_gpx(routes_dir / f"{name}.gpx", start, end, offset, rng)

    ecg_count = 0
    for week in range(0, args.days, 28):
        recorded_on = start_day + timedelta(days=week + 3)
        # Clamped, not assumed to fit. `latest_data_date` takes the max across records, workouts
        # *and* ecg_recordings, so a recording three days into a final partial month would set
        # the app's data span past --end-date and make DataFreshness report a date nobody asked
        # for -- the same lie the last night's sleep is skipped to avoid.
        if recorded_on > args.end_date:
            break
        when = datetime.combine(recorded_on, datetime.min.time()) + timedelta(
            hours=8, minutes=rng.randint(0, 50)
        )
        classification = ECG_CLASSIFICATIONS[ecg_count % len(ECG_CLASSIFICATIONS)]
        write_ecg(ecg_dir / f"ecg_{when:%Y-%m-%d}.csv", when, classification, rng)
        ecg_count += 1

    clinical_count = write_clinical_records(out / "clinical-records", args.end_date, rng)

    size_mb = export_xml.stat().st_size / 1_000_000
    print(f"Wrote {out}/ from seed {args.seed}:")
    print(
        f"  export.xml            {record_count:,} records, "
        f"{len(summaries):,} daily summaries, {size_mb:.1f} MB"
    )
    print(f"  workout-routes/       {len(route_windows):,} GPX tracks")
    print(f"  electrocardiograms/   {ecg_count} recordings")
    print(f"  clinical-records/     {clinical_count} FHIR resources")
    print(
        f"  {start_day} to {args.end_date}: {gap_days} days skipped, "
        f"{empty_days} with no records at all"
    )
    print()
    print("Next:")
    # Its own database, not the default one. Ingest is drop-and-reload, so suggesting the
    # default here would hand someone a command that replaces the real export they had
    # already imported.
    print(f"  uv run pomona ingest {export_xml} --db data/demo.db")
    print("  POMONA_DB_PATH=data/demo.db uv run pomona serve")


if __name__ == "__main__":
    main()
