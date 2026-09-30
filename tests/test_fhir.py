import pytest

from pomona import fhir


class TestAccessors:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (95, 95),
            (4.5, 4.5),
            (True, None),
            ("95", None),
            (None, None),
            (float("inf"), None),
            (float("nan"), None),
            (2**63, float(2**63)),
            (10**400, None),
        ],
    )
    def test_as_number(self, value, expected):
        assert fhir.as_number(value) == expected

    @pytest.mark.parametrize(
        ("code", "expected"),
        [
            ({"text": "Text", "coding": [{"display": "Display"}]}, "Text"),
            ({"text": "", "coding": [{"display": ""}, {"display": "Second"}]}, "Second"),
            ({"coding": [{"code": "1"}, "junk", {"display": "Later"}]}, "Later"),
            ({"text": ""}, None),
            ("not an object", None),
            ({"coding": 7}, None),
        ],
    )
    def test_code_label(self, code, expected):
        assert fhir.code_label(code) == expected

    def test_shape_helpers(self):
        assert fhir.as_dict([1]) == {}
        assert fhir.first_dict([{"a": 1}, {"b": 2}]) == {"a": 1}
        assert fhir.first_dict(["x"]) == {}
        assert fhir.first_dict([]) == {}
        assert fhir.as_str(5) is None
        assert fhir.as_nonempty_str("") is None


class TestParseResource:
    def test_malformed_json_is_none(self):
        # Both range and component parsing go through parse_resource, which is where a stored
        # payload that isn't a JSON object stops being anyone's problem.
        assert fhir.parse_resource("not json") is None
        assert fhir.parse_resource("[]") is None
        assert fhir.parse_resource(None) is None

    def test_a_resource_nested_past_the_recursion_limit_is_none(self):
        assert fhir.parse_resource("[" * 100_000 + "]" * 100_000) is None

    def test_an_object_is_returned(self):
        assert fhir.parse_resource('{"resourceType": "Observation"}') == {
            "resourceType": "Observation"
        }


class TestReferenceRange:
    @pytest.mark.parametrize(
        ("resource", "expected"),
        [
            ({}, None),
            ({"referenceRange": []}, None),
            ({"referenceRange": [{}]}, None),
            (
                {"referenceRange": [{"text": "Negative"}]},
                {"low": None, "high": None, "unit": None, "text": "Negative"},
            ),
            (
                {"referenceRange": [{"low": {"value": 3.5, "unit": "g/dL"}}]},
                {"low": 3.5, "high": None, "unit": "g/dL", "text": None},
            ),
            (
                {"referenceRange": [{"high": {"value": "<200"}, "text": "<200"}]},
                {"low": None, "high": None, "unit": None, "text": "<200"},
            ),
            (
                {"referenceRange": [{"low": {"value": 4}, "high": {"value": 6, "unit": "mmol/L"}}]},
                {"low": 4, "high": 6, "unit": "mmol/L", "text": None},
            ),
            ({"referenceRange": [{"low": {"value": True}}]}, None),
            ({"referenceRange": {"low": {"value": 1}}}, None),
            # A bound too large for a float -- parsed from 1e999 -- can't be encoded in the
            # response, so it's dropped rather than let one record 500 the page.
            ({"referenceRange": [{"high": {"value": float("inf")}}]}, None),
            ({"referenceRange": [{"high": {"value": 10**400}}]}, None),
            (
                {"referenceRange": [{"low": {"value": 1, "unit": {"code": "mg"}}}]},
                {"low": 1, "high": None, "unit": None, "text": None},
            ),
        ],
    )
    def test_flattens_first_range(self, resource, expected):
        assert fhir.reference_range(resource) == expected

    def test_no_resource_is_none(self):
        assert fhir.reference_range(None) is None


class TestComponents:
    @pytest.mark.parametrize(
        "resource",
        [
            {},
            {"component": []},
            {"component": {}},
            {"component": "systolic"},
            {"component": [{}]},
            {"component": [{"code": {}, "valueQuantity": {"value": None}}]},
            {"component": [{"code": {"coding": 7}}]},
            {"component": [{"code": {"text": "", "coding": [{"display": ""}]}}]},
            {"component": [{"code": {"text": ""}, "valueString": ""}]},
            {"component": [{"valueQuantity": {"value": float("nan")}}]},
        ],
    )
    def test_shapes_with_nothing_to_show_are_none(self, resource):
        assert fhir.components(resource) is None

    def test_an_unparseable_resource_is_none(self):
        assert fhir.components(fhir.parse_resource("not json")) is None
        assert fhir.components(None) is None

    def test_flattens_each_part(self):
        resource = {
            "component": [
                {
                    "code": {
                        "text": "Systolic blood pressure",
                        "coding": [
                            {"system": "http://snomed.info/sct", "code": "271649006"},
                            {"system": "http://loinc.org", "code": "8480-6"},
                        ],
                    },
                    "valueQuantity": {"value": 120, "unit": "mmHg"},
                    "referenceRange": [{"high": {"value": 130, "unit": "mmHg"}}],
                },
                {"code": {"text": "Interpretation"}, "valueString": "Within expected limits"},
            ]
        }
        assert fhir.components(resource) == [
            {
                "label": "Systolic blood pressure",
                "code": "8480-6",
                "value_num": 120,
                "value_unit": "mmHg",
                "value_text": None,
                "reference_range": {"low": None, "high": 130, "unit": "mmHg", "text": None},
            },
            {
                "label": "Interpretation",
                "code": None,
                "value_num": None,
                "value_unit": None,
                "value_text": "Within expected limits",
                "reference_range": None,
            },
        ]

    @pytest.mark.parametrize("system", sorted(fhir.LOINC_SYSTEMS))
    def test_loinc_code_is_read_from_every_spelling_of_the_system(self, system):
        resource = {
            "component": [
                {
                    "code": {"coding": [{"system": system, "code": "8480-6"}]},
                    "valueQuantity": {"value": 1},
                }
            ]
        }
        assert fhir.components(resource)[0]["code"] == "8480-6"

    def test_label_falls_back_past_an_empty_display_to_the_first_real_one(self):
        resource = {
            "component": [
                {
                    "code": {"text": "", "coding": [{"display": ""}, {"display": "Systolic"}]},
                    "valueQuantity": {"value": 1},
                }
            ]
        }
        assert fhir.components(resource)[0]["label"] == "Systolic"
