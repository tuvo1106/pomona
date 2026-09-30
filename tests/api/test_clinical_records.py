from pomona.clinical import INGESTED_RESOURCE_TYPES
from tests.conftest import writing


class TestClinical:
    def test_lists_five_rows_from_the_seven_fixture_files(self, client):
        response = client.get("/api/clinical")
        assert response.status_code == 200
        body = response.json()
        # Seven fixture files, five rows: Patient and Procedure are both off the ingest
        # allowlist, so neither reaches the database (see clinical_loader).
        assert len(body) == 5
        assert all(row["resource_type"] != "Patient" for row in body)

    def test_excludes_types_off_the_allowlist_even_from_a_stale_database(
        self, client, seeded_db_path
    ):
        # A database built before a type left the ingest allowlist still holds those rows until
        # the next drop-and-reload. Written straight into the table for that reason: the loader
        # can no longer produce one, which is exactly why the endpoint has to defend itself.
        with writing(seeded_db_path) as conn:
            conn.execute(
                "INSERT INTO clinical_records (resource_id, resource_type, code_text, raw_json)"
                " VALUES ('stale-row', 'SomeUnservedType', 'whatever', '{}')"
            )

        served = {row["resource_type"] for row in client.get("/api/clinical").json()}
        # Non-empty first: `served <= allowlist` is satisfied by the empty set, so on its own it
        # would also pass if /api/clinical returned nothing -- including if the allowlist shrank
        # to nothing, which makes the `IN ()` clause a syntax error and every request a 500.
        assert served, "/api/clinical returned no rows, so the exclusion below proves nothing"
        assert served <= INGESTED_RESOURCE_TYPES, served - INGESTED_RESOURCE_TYPES

        # Not even when asked for by name.
        assert client.get("/api/clinical?resource_type=SomeUnservedType").json() == []

    def test_resource_type_filter(self, client):
        response = client.get("/api/clinical?resource_type=Observation")
        body = response.json()
        assert len(body) == 1
        assert body[0]["code_text"] == "LDL CALCULATED"
        assert body[0]["value_num"] == 95
        assert body[0]["results"] is None

    def test_observation_includes_reference_range(self, client):
        body = client.get("/api/clinical?resource_type=Observation").json()
        assert body[0]["reference_range"] == {
            "low": 0,
            "high": 99,
            "unit": "mg/dL",
            "text": "0-99 mg/dL",
        }

    def test_non_observations_have_no_reference_range(self, client):
        body = client.get("/api/clinical").json()
        others = [row for row in body if row["resource_type"] != "Observation"]
        assert others
        assert all(row["reference_range"] is None for row in others)
        assert all("raw_json" not in row for row in body)

    def test_diagnostic_report_includes_resolved_results(self, client):
        response = client.get("/api/clinical?resource_type=DiagnosticReport")
        body = response.json()
        assert len(body) == 1
        assert body[0]["results"] == [
            {
                "display": None,
                "code_text": "LDL CALCULATED",
                "value_num": 95,
                "value_unit": "mg/dL",
                "value_text": None,
                "status": "final",
            }
        ]

    def test_non_finite_numbers_in_stored_results_read_as_null(self, client, seeded_db_path):
        # What a database ingested before the loader dropped them can hold: json.dumps writes
        # inf and NaN as these bare words, and the response can't encode them.
        with writing(seeded_db_path) as conn:
            conn.execute(
                "UPDATE clinical_records SET results_json = ? "
                "WHERE resource_type = 'DiagnosticReport'",
                ['[{"value_num": Infinity}, {"value_num": NaN}, {"value_num": 95}]'],
            )
        response = client.get("/api/clinical?resource_type=DiagnosticReport")
        assert response.status_code == 200
        assert response.json()[0]["results"] == [
            {"value_num": None},
            {"value_num": None},
            {"value_num": 95},
        ]


# Invented readings, not anyone's: a textbook 120/80 so the assertions read unambiguously.
SYSTOLIC_COMPONENT = {
    "code": {
        "text": "Systolic blood pressure",
        "coding": [
            {"system": "http://snomed.info/sct", "code": "271649006"},
            {"system": "http://loinc.org", "code": "8480-6", "display": "Systolic"},
        ],
    },
    "valueQuantity": {"value": 120, "unit": "mmHg"},
}

DIASTOLIC_COMPONENT = {
    "code": {
        "text": "Diastolic blood pressure",
        "coding": [{"system": "http://loinc.org", "code": "8462-4", "display": "Diastolic"}],
    },
    "valueQuantity": {"value": 80, "unit": "mmHg"},
}


def _panel(*components: dict) -> dict:
    return {
        "resourceType": "Observation",
        "id": "obs-panel",
        "status": "final",
        "code": {"text": "Blood pressure panel"},
        "effectiveDateTime": "2026-05-04T09:00:00Z",
        "component": list(components),
    }


class TestObservationComponents:
    def test_blood_pressure_panel_exposes_both_parts(self, clinical_client):
        client = clinical_client(_panel(SYSTOLIC_COMPONENT, DIASTOLIC_COMPONENT))
        body = client.get("/api/clinical").json()
        assert len(body) == 1
        # The row itself has no value -- that's the bug this fixes.
        assert body[0]["value_num"] is None
        assert body[0]["value_text"] is None
        assert body[0]["components"] == [
            {
                "label": "Systolic blood pressure",
                "code": "8480-6",
                "value_num": 120,
                "value_unit": "mmHg",
                "value_text": None,
                "reference_range": None,
            },
            {
                "label": "Diastolic blood pressure",
                "code": "8462-4",
                "value_num": 80,
                "value_unit": "mmHg",
                "value_text": None,
                "reference_range": None,
            },
        ]

    def test_parts_are_identified_by_code_when_diastolic_comes_first(self, clinical_client):
        # FHIR puts no order on component[], so the codes -- not the positions -- have to
        # carry which part is which.
        client = clinical_client(_panel(DIASTOLIC_COMPONENT, SYSTOLIC_COMPONENT))
        components = client.get("/api/clinical").json()[0]["components"]
        by_code = {c["code"]: c["value_num"] for c in components}
        assert by_code == {"8462-4": 80, "8480-6": 120}

    def test_a_third_part_is_returned_rather_than_dropped(self, clinical_client):
        # The page only collapses a panel to one reading when it is exactly the pair; an
        # extra part has to reach it so it can fall back to the labelled list.
        mean = {
            "code": {"text": "Mean blood pressure"},
            "valueQuantity": {"value": 93, "unit": "mm[Hg]"},
        }
        client = clinical_client(_panel(SYSTOLIC_COMPONENT, DIASTOLIC_COMPONENT, mean))
        components = client.get("/api/clinical").json()[0]["components"]
        assert [c["label"] for c in components] == [
            "Systolic blood pressure",
            "Diastolic blood pressure",
            "Mean blood pressure",
        ]

    def test_a_record_with_both_a_value_and_components_keeps_both(self, clinical_client):
        panel = _panel(SYSTOLIC_COMPONENT, DIASTOLIC_COMPONENT)
        panel["valueQuantity"] = {"value": 5, "unit": "kg"}
        body = clinical_client(panel).get("/api/clinical").json()
        assert body[0]["value_num"] == 5
        assert len(body[0]["components"]) == 2

    def test_ordinary_observation_has_no_components(self, client):
        body = client.get("/api/clinical?resource_type=Observation").json()
        assert body[0]["value_num"] == 95
        assert body[0]["components"] is None

    def test_non_observations_have_no_components(self, client):
        body = client.get("/api/clinical").json()
        others = [row for row in body if row["resource_type"] != "Observation"]
        assert others
        assert all(row["components"] is None for row in others)

    def test_component_reference_range_and_text_value(self, clinical_client):
        client = clinical_client(
            _panel(
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "1111-1"}]},
                    "valueQuantity": {"value": 7, "unit": "mmol/L"},
                    "referenceRange": [
                        {"low": {"value": 4, "unit": "mmol/L"}, "high": {"value": 6}}
                    ],
                },
                {"code": {"text": "Interpretation"}, "valueString": "Within expected limits"},
            )
        )
        components = client.get("/api/clinical").json()[0]["components"]
        assert components[0]["label"] is None
        assert components[0]["reference_range"] == {
            "low": 4,
            "high": 6,
            "unit": "mmol/L",
            "text": None,
        }
        assert components[1] == {
            "label": "Interpretation",
            "code": None,
            "value_num": None,
            "value_unit": None,
            "value_text": "Within expected limits",
            "reference_range": None,
        }

    def test_label_falls_back_to_a_coding_display(self, clinical_client):
        client = clinical_client(
            _panel(
                {"code": SYSTOLIC_COMPONENT["code"] | {"text": ""}, "valueQuantity": {"value": 1}}
            )
        )
        components = client.get("/api/clinical").json()[0]["components"]
        assert components[0]["label"] == "Systolic"
        assert components[0]["value_unit"] is None

    def test_loinc_code_is_read_from_the_oid_spelling_of_the_system(self, clinical_client):
        # Older interfaces identify LOINC by OID rather than by its URL; both name the same
        # code system, and the page needs the code to recognise a blood pressure.
        oid_systolic = {
            "code": {
                "text": "Systolic blood pressure",
                "coding": [{"system": "urn:oid:2.16.840.1.113883.6.1", "code": "8480-6"}],
            },
            "valueQuantity": {"value": 120, "unit": "mm[Hg]"},
        }
        client = clinical_client(_panel(oid_systolic, DIASTOLIC_COMPONENT))
        components = client.get("/api/clinical").json()[0]["components"]
        assert components[0]["code"] == "8480-6"

    def test_a_malformed_panel_does_not_break_the_endpoint(self, clinical_client):
        client = clinical_client(
            _panel(
                "not an object",
                {"code": "not an object", "valueQuantity": {"value": True}},
                # A non-list `coding` is iterated over if it isn't guarded, which would
                # raise out of the flattener and 500 the whole clinical page.
                {"code": {"coding": 7}, "valueQuantity": {"value": True}},
                {"code": {"text": "Kept"}, "valueQuantity": {"value": 2, "unit": "kg"}},
            )
        )
        response = client.get("/api/clinical")
        assert response.status_code == 200
        # The three unusable entries are dropped; the last still renders.
        assert response.json()[0]["components"] == [
            {
                "label": "Kept",
                "code": None,
                "value_num": 2,
                "value_unit": "kg",
                "value_text": None,
                "reference_range": None,
            }
        ]
