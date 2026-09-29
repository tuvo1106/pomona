import pytest

from pomona import fhir


class TestParseResource:
    def test_malformed_json_is_none(self):
        # Both range and component parsing go through parse_resource, which is where a stored
        # payload that isn't a JSON object stops being anyone's problem.
        assert fhir.parse_resource("not json") is None
        assert fhir.parse_resource("[]") is None
        assert fhir.parse_resource(None) is None


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
            ({"referenceRange": [{"low": {"value": True}}]}, None),
            ({"referenceRange": {"low": {"value": 1}}}, None),
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
        ],
    )
    def test_shapes_with_nothing_to_show_are_none(self, resource):
        assert fhir.components(resource) is None

    def test_an_unparseable_resource_is_none(self):
        assert fhir.components(fhir.parse_resource("not json")) is None
        assert fhir.components(None) is None
