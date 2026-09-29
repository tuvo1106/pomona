import json

from pomona.clinical import INGESTED_RESOURCE_TYPES
from pomona.ingest.clinical_loader import load_clinical_records
from tests.conftest import CLINICAL_FIXTURES_DIR


def _load(conn):
    return load_clinical_records(conn, CLINICAL_FIXTURES_DIR)


def _row(conn, resource_id):
    return conn.execute(
        "SELECT * FROM clinical_records WHERE resource_id = ?", [resource_id]
    ).fetchone()


class TestLoadClinicalRecords:
    def test_loads_every_fixture_file_except_the_skipped_type(self, writable_conn):
        # Seven files in the fixture dir, five rows: Patient and Procedure are both off the
        # allowlist, so neither is stored.
        loaded, skipped = _load(writable_conn)
        assert (loaded, skipped) == (5, 0)
        assert writable_conn.execute("SELECT COUNT(*) FROM clinical_records").fetchone()[0] == 5

    def test_observation_fields(self, writable_conn):
        _load(writable_conn)
        row = _row(writable_conn, "obs-1")
        assert row["resource_type"] == "Observation"
        assert row["code_text"] == "LDL CALCULATED"
        assert row["code_system"] == "http://loinc.org"
        assert row["code_value"] == "13457-7"
        assert row["value_num"] == 95
        assert row["value_unit"] == "mg/dL"
        assert row["status"] == "final"
        assert row["category"] == "Laboratory"
        assert row["effective_date"] is not None

    def test_observation_with_value_string_instead_of_quantity(self, writable_conn, tmp_path):
        # A narrative/impression Observation (e.g. a radiology report's freeform findings,
        # commonly referenced from a DiagnosticReport's result[]) carries valueString rather
        # than valueQuantity.
        clinical_dir = tmp_path / "clinical-records"
        clinical_dir.mkdir()
        (clinical_dir / "Observation-1.json").write_text(
            json.dumps(
                {
                    "resourceType": "Observation",
                    "id": "obs-narrative",
                    "status": "final",
                    "code": {"text": "Narrative"},
                    "valueString": "No acute fracture or dislocation.",
                }
            )
        )
        load_clinical_records(writable_conn, clinical_dir)
        row = _row(writable_conn, "obs-narrative")
        assert row["value_num"] is None
        assert row["value_text"] == "No acute fracture or dislocation."

    def test_condition_fields(self, writable_conn):
        _load(writable_conn)
        row = _row(writable_conn, "cond-1")
        assert row["code_text"] == "Essential hypertension"
        assert row["code_system"] == "http://hl7.org/fhir/sid/icd-10-cm"
        assert row["status"] == "active"
        assert row["value_num"] is None

    def test_types_off_the_allowlist_are_not_ingested(self, writable_conn):
        # The Procedure fixture stays in the directory on purpose: it is the only thing proving
        # the allowlist is applied. Without a resource to look for, the check could be dropped
        # and every test here would still pass while a re-ingest quietly stored everything.
        _load(writable_conn)
        assert _row(writable_conn, "procedure-1") is None
        stored = {
            row[0]
            for row in writable_conn.execute("SELECT DISTINCT resource_type FROM clinical_records")
        }
        # Non-empty first: the subset assertion below is true of an empty table, so alone it
        # would pass if the loader stored nothing at all.
        assert stored, "nothing was ingested, so the subset check below proves nothing"
        assert stored <= INGESTED_RESOURCE_TYPES, stored - INGESTED_RESOURCE_TYPES

    def test_immunization_fields(self, writable_conn):
        _load(writable_conn)
        row = _row(writable_conn, "imm-1")
        assert row["code_text"] == "Influenza, seasonal, injectable"
        assert row["value_text"] == "Influenza, seasonal, injectable"
        assert row["status"] == "completed"

    def test_diagnostic_report_has_no_own_value(self, writable_conn):
        _load(writable_conn)
        row = _row(writable_conn, "diag-1")
        assert row["code_text"] == "TSH"
        assert row["value_num"] is None
        assert row["value_text"] is None
        raw = json.loads(row["raw_json"])
        assert raw["result"][0]["reference"] == "Observation/obs-1"

    def test_diagnostic_report_resolves_result_references(self, writable_conn):
        _load(writable_conn)
        row = _row(writable_conn, "diag-1")
        results = json.loads(row["results_json"])
        assert results == [
            {
                "display": None,
                "code_text": "LDL CALCULATED",
                "value_num": 95,
                "value_unit": "mg/dL",
                "value_text": None,
                "status": "final",
            }
        ]

    def test_diagnostic_report_unresolvable_reference_keeps_display_with_null_values(
        self, writable_conn, tmp_path
    ):
        clinical_dir = tmp_path / "clinical-records"
        clinical_dir.mkdir()
        (clinical_dir / "DiagnosticReport-1.json").write_text(
            json.dumps(
                {
                    "resourceType": "DiagnosticReport",
                    "id": "diag-orphan",
                    "result": [
                        {"display": "Component (1): Missing Test", "reference": "Observation/gone"}
                    ],
                }
            )
        )
        load_clinical_records(writable_conn, clinical_dir)
        row = _row(writable_conn, "diag-orphan")
        results = json.loads(row["results_json"])
        assert results == [
            {
                "display": "Component (1): Missing Test",
                "code_text": None,
                "value_num": None,
                "value_unit": None,
                "value_text": None,
                "status": None,
            }
        ]

    def test_diagnostic_report_with_no_results_has_null_results_json(self, writable_conn, tmp_path):
        clinical_dir = tmp_path / "clinical-records"
        clinical_dir.mkdir()
        (clinical_dir / "DiagnosticReport-1.json").write_text(
            json.dumps({"resourceType": "DiagnosticReport", "id": "diag-empty"})
        )
        load_clinical_records(writable_conn, clinical_dir)
        row = _row(writable_conn, "diag-empty")
        assert row["results_json"] is None

    def test_non_diagnostic_report_has_null_results_json(self, writable_conn):
        _load(writable_conn)
        row = _row(writable_conn, "obs-1")
        assert row["results_json"] is None

    def test_document_reference_has_no_clinical_value(self, writable_conn):
        _load(writable_conn)
        row = _row(writable_conn, "docref-1")
        assert row["code_text"] == "Progress Notes"
        assert row["value_num"] is None
        assert row["value_text"] is None
        assert row["status"] == "current"

    def test_the_patient_demographics_row_is_not_stored(self, writable_conn):
        # It used to be, with the full name in code_text, gender in status and date of birth in
        # value_text -- the single most identifying row in the database, written on every ingest
        # and read by nothing. This is the inverse of the test that used to assert those columns.
        _load(writable_conn)
        assert _row(writable_conn, "patient-1") is None
        assert (
            writable_conn.execute(
                "SELECT COUNT(*) FROM clinical_records WHERE resource_type = 'Patient'"
            ).fetchone()[0]
            == 0
        )

    def test_raw_json_round_trips_the_full_original_resource(self, writable_conn):
        _load(writable_conn)
        row = _row(writable_conn, "obs-1")
        raw = json.loads(row["raw_json"])
        assert raw["resourceType"] == "Observation"
        assert raw["valueQuantity"]["value"] == 95

    def test_reingesting_is_idempotent(self, writable_conn):
        first = _load(writable_conn)
        second = _load(writable_conn)
        assert first == second == (5, 0)

    def test_missing_clinical_dir_returns_zero_without_raising(self, writable_conn, tmp_path):
        assert load_clinical_records(writable_conn, tmp_path / "does-not-exist") == (0, 0)

    def test_missing_clinical_dir_leaves_existing_rows_intact(self, writable_conn, tmp_path):
        # A mistyped --clinical-dir must not wipe previously-ingested clinical data: the
        # table is cleared only once there's a directory to reload it from.
        _load(writable_conn)
        load_clinical_records(writable_conn, tmp_path / "typo-clinical-records")
        assert writable_conn.execute("SELECT COUNT(*) FROM clinical_records").fetchone()[0] == 5

    def test_same_fhir_id_across_resource_types_both_load(self, writable_conn, tmp_path):
        # FHIR ids are only unique per resource type per issuing server, so two resources
        # can legitimately share one. Both must land instead of raising IntegrityError and
        # rolling back the entire ingest.
        clinical_dir = tmp_path / "clinical-records"
        clinical_dir.mkdir()
        (clinical_dir / "Condition-1.json").write_text(
            json.dumps({"resourceType": "Condition", "id": "1"})
        )
        (clinical_dir / "Observation-1.json").write_text(
            json.dumps({"resourceType": "Observation", "id": "1"})
        )
        loaded, _ = load_clinical_records(writable_conn, clinical_dir)
        assert loaded == 2
        rows = writable_conn.execute(
            "SELECT id, resource_id, resource_type FROM clinical_records ORDER BY resource_type"
        ).fetchall()
        assert [r["resource_type"] for r in rows] == ["Condition", "Observation"]
        assert [r["resource_id"] for r in rows] == ["1", "1"]
        # The exposed id stays unique, since the frontend keys table rows on it.
        assert len({r["id"] for r in rows}) == 2

    def test_unknown_resource_type_is_dropped_rather_than_stored_empty(
        self, writable_conn, tmp_path
    ):
        # It used to be stored with every flattened column empty, on the grounds that keeping the
        # raw payload cost nothing. It costs something: a stored row can be queried, logged or
        # end up in a backup, and the clinical page renders a type it doesn't recognise as its
        # own raw-named section -- so an unanticipated type arrived *more* prominent than the
        # designed ones. An allowlist means a new resource type is a no-op until it has a view.
        unknown_dir = tmp_path / "clinical-records"
        unknown_dir.mkdir()
        (unknown_dir / "Weird-1.json").write_text(
            json.dumps({"resourceType": "SomethingNew", "id": "weird-1"})
        )
        assert load_clinical_records(writable_conn, unknown_dir) == (0, 0)
        assert _row(writable_conn, "weird-1") is None

    def test_unusable_files_are_skipped_not_fatal(self, writable_conn, tmp_path, caplog):
        # The whole ingest is one transaction, so a raise here would roll back export.xml
        # and every other side-loader too. Each of these must be skipped, counted and named.
        clinical_dir = tmp_path / "clinical-records"
        clinical_dir.mkdir()
        (clinical_dir / "Observation-good.json").write_text(
            json.dumps({"resourceType": "Observation", "id": "good", "code": {"text": "LDL"}})
        )
        (clinical_dir / "truncated.json").write_text('{"resourceType": "Observ')
        (clinical_dir / "not-utf8.json").write_bytes(b"\xff\xfe\x00garbage")
        (clinical_dir / "top-level-array.json").write_text("[]")
        (clinical_dir / "a-directory.json").mkdir()

        loaded, skipped = load_clinical_records(writable_conn, clinical_dir)

        assert (loaded, skipped) == (1, 4)
        assert _row(writable_conn, "good")["code_text"] == "LDL"
        for name in ["truncated.json", "not-utf8.json", "top-level-array.json", "a-directory.json"]:
            assert name in caplog.text

    def test_utf8_bom_is_read_not_skipped(self, writable_conn, tmp_path):
        clinical_dir = tmp_path / "clinical-records"
        clinical_dir.mkdir()
        (clinical_dir / "Observation-bom.json").write_bytes(
            b"\xef\xbb\xbf"
            + json.dumps(
                {"resourceType": "Observation", "id": "bom", "valueQuantity": {"unit": "\u00b5g"}}
            ).encode()
        )
        assert load_clinical_records(writable_conn, clinical_dir) == (1, 0)
        assert _row(writable_conn, "bom")["value_unit"] == "\u00b5g"

    def test_wrong_typed_fields_flatten_to_none_and_the_rest_loads(self, writable_conn, tmp_path):
        # Every one of these used to raise (in the extractor, or binding the value to SQLite).
        # The resource is still worth keeping: its well-typed fields and its raw_json.
        clinical_dir = tmp_path / "clinical-records"
        clinical_dir.mkdir()
        (clinical_dir / "Observation-odd.json").write_text(
            json.dumps(
                {
                    "resourceType": "Observation",
                    "id": "odd",
                    "code": "LDL",
                    "status": {"a": 1},
                    "valueQuantity": {"value": [95], "unit": "mg/dL"},
                    "valueString": ["x"],
                    "category": ["Laboratory"],
                    "effectiveDateTime": 20260101,
                    "issued": "2026-01-02T00:00:00Z",
                }
            )
        )
        (clinical_dir / "Observation-list-id.json").write_text(
            json.dumps({"resourceType": "Observation", "id": ["a"], "valueQuantity": {"value": 1}})
        )
        (clinical_dir / "Observation-huge.json").write_text(
            json.dumps(
                {"resourceType": "Observation", "id": "huge", "valueQuantity": {"value": 10**30}}
            )
        )
        (clinical_dir / "DiagnosticReport-odd.json").write_text(
            json.dumps(
                {
                    "resourceType": "DiagnosticReport",
                    "id": "dr-odd",
                    "result": ["x", {"reference": 5, "display": "HDL"}],
                }
            )
        )
        (clinical_dir / "list-type.json").write_text(json.dumps({"resourceType": ["Observation"]}))

        assert load_clinical_records(writable_conn, clinical_dir) == (4, 0)

        odd = _row(writable_conn, "odd")
        assert odd["code_text"] is None
        assert odd["status"] is None
        assert odd["value_num"] is None
        assert odd["value_unit"] == "mg/dL"
        assert odd["value_text"] is None
        assert odd["category"] is None
        assert odd["effective_date"] is None
        assert odd["recorded_date"] is not None
        assert json.loads(odd["raw_json"])["code"] == "LDL"
        # A non-string id falls back to the filename stem, like a missing one.
        assert _row(writable_conn, "Observation-list-id")["value_num"] == 1
        assert _row(writable_conn, "huge")["value_num"] == 1e30
        results = json.loads(_row(writable_conn, "dr-odd")["results_json"])
        assert [r["display"] for r in results] == [None, "HDL"]

    def test_numbers_no_float_can_hold_load_as_none(self, writable_conn, tmp_path):
        # Written as raw text: both are valid JSON that json.dumps can't produce. 1e999
        # parses to inf, which would ride along in results_json and 500 the clinical API;
        # a 400-digit int used to raise converting to float and abort the whole ingest.
        clinical_dir = tmp_path / "clinical-records"
        clinical_dir.mkdir()
        for resource_id, value in [("inf", "1e999"), ("vast", "1" + "0" * 400)]:
            (clinical_dir / f"Observation-{resource_id}.json").write_text(
                f'{{"resourceType": "Observation", "id": "{resource_id}",'
                f' "valueQuantity": {{"value": {value}, "unit": "mg"}}}}'
            )
        (clinical_dir / "DiagnosticReport-1.json").write_text(
            json.dumps(
                {
                    "resourceType": "DiagnosticReport",
                    "id": "dr",
                    "result": [{"reference": "Observation/inf"}],
                }
            )
        )

        assert load_clinical_records(writable_conn, clinical_dir) == (3, 0)
        assert _row(writable_conn, "inf")["value_num"] is None
        assert _row(writable_conn, "vast")["value_num"] is None
        results = json.loads(_row(writable_conn, "dr")["results_json"])
        assert results[0]["value_num"] is None
        assert results[0]["value_unit"] == "mg"

    def test_duplicate_type_and_id_each_keep_their_own_fields(self, writable_conn, tmp_path):
        # Two providers can both export Observation/1 (ADR-0003). Each row must carry its
        # own flattened values, not the last file's.
        clinical_dir = tmp_path / "clinical-records"
        clinical_dir.mkdir()
        for name, text in [("a", "LDL"), ("b", "HDL")]:
            (clinical_dir / f"Observation-{name}.json").write_text(
                json.dumps({"resourceType": "Observation", "id": "1", "code": {"text": text}})
            )
        load_clinical_records(writable_conn, clinical_dir)
        rows = writable_conn.execute(
            "SELECT code_text, raw_json FROM clinical_records ORDER BY id"
        ).fetchall()
        assert [(r["code_text"], json.loads(r["raw_json"])["code"]["text"]) for r in rows] == [
            ("LDL", "LDL"),
            ("HDL", "HDL"),
        ]
