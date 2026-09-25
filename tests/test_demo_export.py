"""The demo generator has to keep producing something this app's own parser accepts.

It writes Apple's export format by hand, which means it can drift from the ingester with
nothing to catch it: a wrong attribute name or a timestamp in the wrong timezone yields a
smaller import, not an error. These tests run the script the way the README tells a reader to
and then assert on what came out the other end.
"""

import json
import sqlite3
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from pomona import db
from pomona.clinical import INGESTED_RESOURCE_TYPES
from pomona.ingest.clinical_loader import load_clinical_records
from pomona.ingest.ecg_loader import load_ecg_recordings
from pomona.ingest.gpx_loader import load_workout_routes
from pomona.ingest.loader import load_export_xml

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "make_demo_export.py"
END_DATE = date(2026, 6, 15)
# 30 rather than a dozen, deliberately: ECG recordings are placed every 28 days, so only a span
# where `(days - 1) % 28 < 3` can put one past the end. A 12-day fixture emits a single ECG on day
# 3 and cannot exercise that at all -- confirmed by disabling the clamp and watching the test
# still pass. Generation is well under a second either way.
DAYS = 30


@pytest.fixture(scope="module")
def demo_export(tmp_path_factory) -> Path:
    """Generates a short export once, through the real command line."""
    out = tmp_path_factory.mktemp("demo") / "export"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--out",
            str(out),
            "--days",
            str(DAYS),
            "--end-date",
            END_DATE.isoformat(),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return out


@pytest.fixture(scope="module")
def demo_db(demo_export: Path, tmp_path_factory) -> sqlite3.Connection:
    """Ingests it with the same loaders the CLI uses."""
    conn = db.connect(tmp_path_factory.mktemp("demo-db") / "demo.db", isolation_level=None)
    db.init_schema(conn)
    load_export_xml(conn, demo_export / "export.xml", show_progress=False)
    load_clinical_records(conn, demo_export / "clinical-records")
    load_workout_routes(conn, demo_export / "workout-routes")
    load_ecg_recordings(conn, demo_export / "electrocardiograms")
    db.create_indexes(conn)
    db.create_views(conn)
    return conn


def count(conn: sqlite3.Connection, sql: str) -> int:
    return conn.execute(sql).fetchone()[0]


class TestGeneratedTree:
    def test_writes_the_four_things_the_cli_looks_for_as_siblings(self, demo_export: Path):
        # `ingest` finds clinical-records/, workout-routes/ and electrocardiograms/ by looking
        # next to export.xml, so the layout is load-bearing rather than cosmetic.
        assert (demo_export / "export.xml").is_file()
        for name in ("clinical-records", "workout-routes", "electrocardiograms"):
            assert (demo_export / name).is_dir(), name
            assert any((demo_export / name).iterdir()), name

    def test_the_same_seed_gives_identical_bytes(self, demo_export: Path, tmp_path: Path):
        """The docstring promises this, and screenshots depend on it.

        Every generated file, not just export.xml: the GPX tracks and ECG traces are what a
        screenshot of the Routes or ECG page is actually made of, and they come from later draws
        on the same PRNG, so they're the ones that would drift.
        """
        again = tmp_path / "again"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--out",
                str(again),
                "--days",
                str(DAYS),
                "--end-date",
                END_DATE.isoformat(),
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        def tree(root: Path) -> dict[str, bytes]:
            return {
                str(path.relative_to(root)): path.read_bytes()
                for path in sorted(root.rglob("*"))
                if path.is_file()
            }

        original, repeat = tree(demo_export), tree(again)
        assert sorted(repeat) == sorted(original)
        assert repeat == original, [name for name in original if repeat[name] != original[name]]

    def test_it_refuses_to_write_over_a_directory_it_did_not_create(self, tmp_path: Path):
        """`--out apple_health_export` would otherwise replace a real export's export.xml.

        The directory-level version of the `--db` hazard: one flag, no confirmation, and what it
        overwrites took an hour to get out of the Health app.
        """
        target = tmp_path / "looks-real"
        target.mkdir()
        (target / "export.xml").write_text("someone's real export")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--out", str(target), "--days", "3"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert (target / "export.xml").read_text() == "someone's real export"

    def test_a_rerun_does_not_leave_the_previous_run_behind(self, demo_export: Path):
        """Route filenames carry a workout time and ECG filenames a date, so a different --seed
        renames most of them. Leftovers import as routes matching no workout."""
        before = {p.name for p in (demo_export / "workout-routes").iterdir()}
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--out",
                str(demo_export),
                "--days",
                str(DAYS),
                "--end-date",
                END_DATE.isoformat(),
                "--seed",
                "4242",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        after = {p.name for p in (demo_export / "workout-routes").iterdir()}
        assert before != after, "a different seed produced the same route filenames"
        assert not (before & after) or len(after) < len(before | after)
        # Put it back, since the module-scoped fixtures share this directory.
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--out",
                str(demo_export),
                "--days",
                str(DAYS),
                "--end-date",
                END_DATE.isoformat(),
            ],
            capture_output=True,
            text=True,
            check=True,
        )

    def test_generates_allowlisted_types_plus_the_patient_that_proves_the_drop(
        self, demo_export: Path
    ):
        # The generator should not invent sensitive-looking data the app would only throw away,
        # with one deliberate exception named below.
        #
        # Read out of each file rather than inferred from its name: a filename is what the
        # generator chose to call something, and this test is about what it actually wrote. The
        # non-empty assertion matters for the same reason -- a subset check is satisfied by an
        # empty directory, so without it this passes hardest when the generator does nothing.
        generated = {
            json.loads(p.read_text(encoding="utf-8"))["resourceType"]
            for p in (demo_export / "clinical-records").glob("*.json")
        }
        assert generated, "no clinical resources were generated at all"
        # Patient is the deliberate exception, and it earns its place: a real export contains one,
        # the other resources' subject references point at it, and it is the only thing making
        # this demo exercise the ingest allowlist end to end. TestIngestedDemo asserts it does
        # not survive into the database.
        assert generated <= INGESTED_RESOURCE_TYPES | {"Patient"}, (
            generated - INGESTED_RESOURCE_TYPES - {"Patient"}
        )
        assert "Patient" in generated, "nothing here is off the allowlist, so nothing tests it"


class TestIngestedDemo:
    def test_records_land_across_the_requested_span(self, demo_db: sqlite3.Connection):
        row = demo_db.execute(
            "SELECT MIN(start_local_date) lo, MAX(start_local_date) hi FROM records"
        ).fetchone()
        # Exactly the requested end, not a day past it: sleep crosses midnight, and the
        # generator skips the last night for this reason.
        assert row["hi"] == END_DATE.isoformat()
        assert row["lo"] < row["hi"]

    def test_covers_enough_metric_types_to_populate_every_group(self, demo_db: sqlite3.Connection):
        # The frontend groups ~40 types across 8 groups; a demo that filled two of them would
        # look broken rather than empty.
        assert count(demo_db, "SELECT COUNT(DISTINCT type) FROM records") >= 30

    def test_every_route_binds_to_a_workout(self, demo_db: sqlite3.Connection):
        """The match is by overlapping time window, so a GPX written in the wrong timezone
        still imports and simply attaches to nothing. Unbound routes are the symptom."""
        total = count(demo_db, "SELECT COUNT(*) FROM workout_routes")
        bound = count(demo_db, "SELECT COUNT(*) FROM workout_routes WHERE workout_id IS NOT NULL")
        assert total > 0
        assert bound == total

    def test_workouts_include_both_the_old_and_the_modern_shape(self, demo_db: sqlite3.Connection):
        # Modern (watchOS 9+) workouts carry totals only in nested WorkoutStatistics. Both
        # shapes are generated so the parser's fallback is exercised; either way the totals
        # have to arrive.
        assert count(demo_db, "SELECT COUNT(*) FROM workouts") > 0
        missing_energy = count(
            demo_db, "SELECT COUNT(*) FROM workouts WHERE total_energy_burned IS NULL"
        )
        assert missing_energy == 0

    def test_two_sources_overlap_so_dedup_has_something_to_do(self, demo_db: sqlite3.Connection):
        sources = {
            row[0]
            for row in demo_db.execute(
                "SELECT DISTINCT source_name FROM records"
                " WHERE type = 'HKQuantityTypeIdentifierStepCount'"
            )
        }
        assert sources == {"iPhone", "Apple Watch"}

    def test_percentage_types_are_written_as_fractions(self, demo_db: sqlite3.Connection):
        # Apple labels these "%" while storing 0-1, and the frontend multiplies by 100 only
        # when the whole series is <= 1. Writing 0-100 here would silently disable that.
        worst = demo_db.execute("SELECT MAX(value_num) FROM records WHERE unit = '%'").fetchone()[0]
        assert worst is not None
        assert worst <= 1

    def test_ecg_recordings_parse_with_a_full_waveform(self, demo_db: sqlite3.Connection):
        row = demo_db.execute(
            "SELECT sample_rate, sample_count, classification FROM ecg_recordings LIMIT 1"
        ).fetchone()
        assert row["sample_rate"] == 512
        assert row["sample_count"] == 512 * 30
        assert row["classification"]

    def test_clinical_records_include_a_component_only_observation(
        self, demo_db: sqlite3.Connection
    ):
        # A blood-pressure panel has no top-level value, only component[]. It read as "—" on the
        # clinical page until that was handled, so the demo should contain one.
        types = {
            row[0] for row in demo_db.execute("SELECT DISTINCT resource_type FROM clinical_records")
        }
        assert {"Condition", "Immunization", "Observation", "DiagnosticReport"} <= types
        # The export writes a Patient; the database must not have one. Together with the generator
        # test above, that is the allowlist proven end to end on a real-shaped export.
        assert "Patient" not in types
        assert types <= INGESTED_RESOURCE_TYPES, types - INGESTED_RESOURCE_TYPES
        panels = count(
            demo_db,
            "SELECT COUNT(*) FROM clinical_records"
            " WHERE resource_type = 'Observation' AND raw_json LIKE '%\"component\"%'",
        )
        assert panels > 0

    def test_at_least_one_day_in_the_span_has_no_records_at_all(self, demo_db: sqlite3.Connection):
        """Charts and streaks have to cope with gaps, and can't be shown to if nothing is
        missing.

        An earlier version of this compared the distinct-date count against the span length,
        which is true of any dataset and so could not fail -- and at the time the generator
        produced no gaps at all in a span this short, because they were pinned to absolute day
        indices. Both are fixed; this asserts the outcome rather than an identity.
        """
        present = {
            row[0] for row in demo_db.execute("SELECT DISTINCT start_local_date FROM records")
        }
        first, last = date.fromisoformat(min(present)), date.fromisoformat(max(present))
        whole_span = {
            (first + timedelta(days=offset)).isoformat()
            for offset in range((last - first).days + 1)
        }
        assert whole_span - present, f"every day from {first} to {last} has records"

    def test_the_quiet_week_lands_inside_a_short_span(self, demo_db: sqlite3.Connection):
        """The quiet stretch is positioned as a fraction of the span, so `--days 12` gets one.

        Asserted through its effect rather than its dates: the lowest daily step total should sit
        well under the median. A fixed day index would put it outside a span this short and this
        would read as a flat series.
        """
        totals = sorted(
            row[0]
            for row in demo_db.execute(
                "SELECT SUM(value_num) FROM records"
                " WHERE type = 'HKQuantityTypeIdentifierStepCount'"
                " GROUP BY start_local_date"
            )
        )
        median = totals[len(totals) // 2]
        assert totals[0] < median * 0.75, f"lowest {totals[0]:.0f} vs median {median:.0f}"

    def test_nothing_is_dated_past_the_requested_end(self, demo_db: sqlite3.Connection):
        """`latest_data_date` takes the max across records, workouts *and* ECG recordings, so any
        one of the three overshooting makes DataFreshness report a date nobody asked for."""
        for table, column in (
            ("records", "start_local_date"),
            ("workouts", "start_local_date"),
            ("ecg_recordings", "recorded_local_date"),
        ):
            newest = demo_db.execute(f"SELECT MAX({column}) FROM {table}").fetchone()[0]
            assert newest is not None, table
            assert newest <= END_DATE.isoformat(), f"{table}.{column} = {newest}"


# Every HK identifier the frontend has a card for. Parsed from the source rather than restated
# here, so a new card added there starts failing this until the generator writes it -- which is
# the whole bug class these tests are about. Four separate metrics were absent from a short span
# because they were emitted on fixed day indices, and nothing noticed.
FRONTEND_GROUPS = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib" / "metricGroups.ts"
)


def frontend_charted_types() -> set[str]:
    import re

    source = FRONTEND_GROUPS.read_text(encoding="utf-8")
    # The identifiers appear as string literals; KNOWN_TYPES is built from the same ones.
    return set(re.findall(r"'(HK(?:Quantity|Category)TypeIdentifier\w+|HKDataType\w+)'", source))


def test_the_frontend_group_file_is_where_we_think_it_is():
    """A regex over a file in another language is only as good as the file existing."""
    assert FRONTEND_GROUPS.is_file(), FRONTEND_GROUPS
    found = frontend_charted_types()
    assert len(found) >= 30, f"only parsed {len(found)} identifiers; the pattern probably broke"


def test_every_type_the_frontend_charts_has_data(demo_db: sqlite3.Connection):
    """No empty cards in a demo whose stated purpose is to fill every screen.

    Blood pressure and sleep are excluded: the frontend charts those through dedicated
    endpoints (/blood-pressure, /sleep) rather than as metric cards, and blood pressure arrives
    in the export as a Correlation rather than a bare Record.
    """
    charted = frontend_charted_types()
    stored = {row[0] for row in demo_db.execute("SELECT DISTINCT type FROM records")}
    missing = charted - stored
    assert not missing, (
        f"the frontend charts these but the demo never writes them: {sorted(missing)}"
    )
