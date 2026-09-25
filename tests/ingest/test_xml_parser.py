from pomona.ingest.xml_parser import count_elements, iter_health_elements
from tests.conftest import SAMPLE_EXPORT_XML


def _collect():
    return list(iter_health_elements(SAMPLE_EXPORT_XML))


class TestIterHealthElements:
    def test_yields_expected_tag_counts(self):
        elements = _collect()
        tags = [tag for tag, _ in elements]
        # 5 top-level Records (2 steps, sleep, heart rate, steps-with-+0100-offset)
        # + 2 nested inside the Correlation (systolic/diastolic)
        # + 2 mindful sessions + 3 apple-stand-hours (2 Stood + 1 Idle)
        # + 3 overlapping-source step records + 3 overlapping-source sleep records = 18.
        assert tags.count("Record") == 18
        assert tags.count("Workout") == 2
        assert tags.count("ActivitySummary") == 2

    def test_correlation_container_itself_is_never_yielded(self):
        elements = _collect()
        assert all(tag != "Correlation" for tag, _ in elements)

    def test_nested_records_inside_correlation_are_still_captured_individually(self):
        elements = _collect()
        record_types = [attrib["type"] for tag, attrib in elements if tag == "Record"]
        assert "HKQuantityTypeIdentifierBloodPressureSystolic" in record_types
        assert "HKQuantityTypeIdentifierBloodPressureDiastolic" in record_types

    def test_record_nested_metadata_entry_does_not_break_parsing(self):
        elements = _collect()
        heart_rate = next(
            attrib
            for tag, attrib in elements
            if tag == "Record" and attrib["type"] == "HKQuantityTypeIdentifierHeartRate"
        )
        assert heart_rate["value"] == "62"
        # Only the three relevant tags are ever yielded -- MetadataEntry (a child of
        # this Record) must never itself surface as a top-level yielded element.
        assert {tag for tag, _ in elements} == {"Record", "Workout", "ActivitySummary"}

    def test_workout_nested_children_are_not_yielded_and_dont_pollute_attribs(self):
        elements = _collect()
        workout_type, workout_attrib = next((t, a) for t, a in elements if t == "Workout")
        assert workout_type == "Workout"
        assert workout_attrib["workoutActivityType"] == "HKWorkoutActivityTypeCycling"
        assert workout_attrib["totalEnergyBurned"] == "420"
        # WorkoutStatistics/WorkoutRoute attributes (e.g. "sum") must not leak into
        # the Workout's own attrib.
        assert "sum" not in workout_attrib

    def test_workout_with_inline_totals_is_not_overridden_by_statistics_fallback(self):
        # The first Workout has both an inline totalDistance and a matching
        # WorkoutStatistics child -- the inline attribute must win, not get summed twice.
        elements = _collect()
        _, workout_attrib = next((t, a) for t, a in elements if t == "Workout")
        assert workout_attrib["totalDistance"] == "15.2"
        assert workout_attrib["totalDistanceUnit"] == "km"

    def test_workout_without_inline_totals_falls_back_to_statistics(self):
        # The second Workout (modern watchOS 9+ format) has no inline totalDistance/
        # totalEnergyBurned attributes at all -- only nested WorkoutStatistics.
        elements = _collect()
        workouts = [a for t, a in elements if t == "Workout"]
        modern = next(
            a for a in workouts if a["workoutActivityType"] == "HKWorkoutActivityTypeRunning"
        )
        # Energy comes from ActiveEnergyBurned (310.5), not Basal (45.2).
        assert modern["totalEnergyBurned"] == "310.5"
        assert modern["totalEnergyBurnedUnit"] == "Cal"
        # Distance comes from DistanceWalkingRunning.
        assert modern["totalDistance"] == "3.1"
        assert modern["totalDistanceUnit"] == "mi"
        # The HeartRate statistic (average/min/max, no "sum") must not pollute totals.
        assert "sum" not in modern

    def test_distance_statistic_without_a_unit_still_yields_the_workout(self, tmp_path):
        # A WorkoutStatistics element can carry a sum but no unit attribute. That must not
        # abort the parse (and with it the whole ingest) -- the sum is still usable.
        xml_path = tmp_path / "export.xml"
        xml_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<HealthData>\n"
            '  <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="30"\n'
            '           startDate="2024-01-01 08:00:00 -0800"\n'
            '           endDate="2024-01-01 08:30:00 -0800">\n'
            '    <WorkoutStatistics type="HKQuantityTypeIdentifierDistanceWalkingRunning"\n'
            '                       sum="3.1"/>\n'
            "  </Workout>\n"
            "</HealthData>\n"
        )
        elements = list(iter_health_elements(xml_path))
        _, workout = next((t, a) for t, a in elements if t == "Workout")
        assert workout["totalDistance"] == "3.1"
        assert "totalDistanceUnit" not in workout

    def test_distance_statistics_in_different_units_are_not_summed_together(self, tmp_path):
        # A workout logging a swim leg (yd) next to bike/run legs (mi) must never report
        # 500 + 12 + 3.1 under either label. The first statistic's unit sets the group;
        # only statistics sharing it are added, and the rest are dropped.
        xml_path = tmp_path / "export.xml"
        xml_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<HealthData>\n"
            '  <Workout workoutActivityType="HKWorkoutActivityTypeSwimBikeRun" duration="90"\n'
            '           startDate="2024-01-01 08:00:00 -0800"\n'
            '           endDate="2024-01-01 09:30:00 -0800">\n'
            '    <WorkoutStatistics type="HKQuantityTypeIdentifierDistanceCycling"\n'
            '                       sum="12" unit="mi"/>\n'
            '    <WorkoutStatistics type="HKQuantityTypeIdentifierDistanceWalkingRunning"\n'
            '                       sum="3.1" unit="mi"/>\n'
            '    <WorkoutStatistics type="HKQuantityTypeIdentifierDistanceSwimming"\n'
            '                       sum="500" unit="yd"/>\n'
            "  </Workout>\n"
            "</HealthData>\n"
        )
        elements = list(iter_health_elements(xml_path))
        _, workout = next((t, a) for t, a in elements if t == "Workout")
        # The two mi legs are comparable and add up; the 500 yd swim is left out entirely
        # rather than inflating a mile count by 500.
        assert float(workout["totalDistance"]) == 15.1
        assert workout["totalDistanceUnit"] == "mi"

    def test_start_local_date_derivation_is_left_to_the_loader_not_the_parser(self):
        # The parser yields raw attrib strings; date parsing happens in loader.py.
        elements = _collect()
        _, attrib = elements[0]
        assert attrib["startDate"] == "2026-08-01 08:00:00 -0700"

    def test_records_with_two_different_utc_offsets_are_both_present_raw(self):
        elements = _collect()
        start_dates = {attrib["startDate"] for tag, attrib in elements if tag == "Record"}
        assert "2026-08-01 08:00:00 -0700" in start_dates
        assert "2026-03-10 07:00:00 +0100" in start_dates


class TestCountElements:
    def test_counts_are_at_least_the_direct_top_level_occurrences(self):
        # This is a cheap byte-scan estimate (used only for a progress bar), so it's
        # allowed to differ slightly from the real parse -- but it must be in the ballpark.
        counts = count_elements(SAMPLE_EXPORT_XML)
        assert counts["Record"] >= 4
        assert counts["Workout"] == 2
        assert counts["ActivitySummary"] == 2
