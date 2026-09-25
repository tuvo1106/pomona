"""Loads apple_health_export/clinical-records/*.json (FHIR R4 resources) into clinical_records.

Not *every* file: only the resource types in INGESTED_RESOURCE_TYPES are kept, and the row
count this returns is the file count minus whatever else the directory held. See pomona.clinical
for why that is an allowlist rather than a list of things to skip.

Each file is one small, flat FHIR resource (not a Bundle) — plain json.load per file is fine
at this volume (~100 files, well under 1MB total). Only fields useful for filtering/display are
flattened into columns; the full resource is kept in raw_json for anything else (e.g. a chat
question that needs a field we didn't flatten). The one exception is a DiagnosticReport's
result[] references, which are resolved against the other resources in the same directory and
flattened into results_json -- see _resolve_diagnostic_report_results.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

from pomona.clinical import INGESTED_RESOURCE_TYPES
from pomona.ingest.dates import parse_fhir_datetime


def _code_fields(code: dict[str, Any] | None) -> tuple[str | None, str | None, str | None]:
    """Extracts (text, system, value) from a FHIR CodeableConcept."""
    if not code:
        return None, None, None
    text = code.get("text")
    codings = code.get("coding") or []
    if codings:
        first = codings[0]
        return text or first.get("display"), first.get("system"), first.get("code")
    return text, None, None


def _status_code(codeable_concept: dict[str, Any] | None) -> str | None:
    if not codeable_concept:
        return None
    codings = codeable_concept.get("coding") or []
    if codings:
        return codings[0].get("code")
    return codeable_concept.get("text")


def _extract_observation(r: dict[str, Any]) -> dict[str, Any]:
    code_text, code_system, code_value = _code_fields(r.get("code"))
    vq = r.get("valueQuantity") or {}
    categories = r.get("category") or []
    # A narrative/impression Observation (e.g. a radiology report's freeform findings, seen
    # via DiagnosticReport.result[] resolution) carries valueString instead of valueQuantity.
    return {
        "code_text": code_text,
        "code_system": code_system,
        "code_value": code_value,
        "status": r.get("status"),
        "value_num": vq.get("value"),
        "value_unit": vq.get("unit"),
        "value_text": r.get("valueString"),
        "effective_date": parse_fhir_datetime(r.get("effectiveDateTime") or r.get("issued")),
        "recorded_date": parse_fhir_datetime(r.get("issued")),
        "category": categories[0].get("text") if categories else None,
    }


def _extract_condition(r: dict[str, Any]) -> dict[str, Any]:
    code_text, code_system, code_value = _code_fields(r.get("code"))
    return {
        "code_text": code_text,
        "code_system": code_system,
        "code_value": code_value,
        "status": _status_code(r.get("clinicalStatus")),
        "value_num": None,
        "value_unit": None,
        "value_text": None,
        "effective_date": parse_fhir_datetime(r.get("onsetDateTime")),
        "recorded_date": parse_fhir_datetime(r.get("recordedDate")),
        "category": None,
    }


def _extract_immunization(r: dict[str, Any]) -> dict[str, Any]:
    vaccine_text, vaccine_system, vaccine_code = _code_fields(r.get("vaccineCode"))
    return {
        "code_text": vaccine_text,
        "code_system": vaccine_system,
        "code_value": vaccine_code,
        "status": r.get("status"),
        "value_num": None,
        "value_unit": None,
        "value_text": vaccine_text,
        "effective_date": parse_fhir_datetime(r.get("occurrenceDateTime")),
        "recorded_date": None,
        "category": None,
    }


def _resolve_diagnostic_report_results(
    r: dict[str, Any], lookup: dict[tuple[str, str], dict[str, Any]]
) -> str | None:
    """Resolves a DiagnosticReport's result[] references against other resources loaded in
    the same ingest (see ADR note in TODO.md). A reference that doesn't resolve -- the
    referenced Observation isn't in this export, or was dropped -- keeps its `display` text
    with null values rather than being omitted, since that's still useful to show.
    """
    results = r.get("result") or []
    if not results:
        return None
    resolved = []
    for entry in results:
        resource_type, _, resource_id = (entry.get("reference") or "").partition("/")
        observation = lookup.get((resource_type, resource_id), _EMPTY_FIELDS)
        resolved.append(
            {
                "display": entry.get("display"),
                "code_text": observation["code_text"],
                "value_num": observation["value_num"],
                "value_unit": observation["value_unit"],
                "value_text": observation["value_text"],
                "status": observation["status"],
            }
        )
    return json.dumps(resolved)


def _extract_diagnostic_report(r: dict[str, Any]) -> dict[str, Any]:
    code_text, code_system, code_value = _code_fields(r.get("code"))
    return {
        "code_text": code_text,
        "code_system": code_system,
        "code_value": code_value,
        "status": r.get("status"),
        "value_num": None,
        "value_unit": None,
        "value_text": None,
        "effective_date": parse_fhir_datetime(r.get("effectiveDateTime") or r.get("issued")),
        "recorded_date": parse_fhir_datetime(r.get("issued")),
        "category": None,
    }


def _extract_document_reference(r: dict[str, Any]) -> dict[str, Any]:
    type_text, type_system, type_code = _code_fields(r.get("type"))
    return {
        "code_text": type_text,
        "code_system": type_system,
        "code_value": type_code,
        "status": r.get("status") or r.get("docStatus"),
        "value_num": None,
        "value_unit": None,
        "value_text": None,
        "effective_date": parse_fhir_datetime(r.get("date")),
        "recorded_date": None,
        "category": None,
    }


EXTRACTORS = {
    "Observation": _extract_observation,
    "Condition": _extract_condition,
    "Immunization": _extract_immunization,
    "DiagnosticReport": _extract_diagnostic_report,
    "DocumentReference": _extract_document_reference,
}

# The allowlist decides what is stored; this decides what any of it means. Asserted rather than
# assumed, at import, because they are edited in different files and the failure is silent: a type
# added to the allowlist without an extractor here would be stored with all ten flattened columns
# empty -- precisely the outcome ADR-0005 exists to make impossible -- and the only visible
# symptom would be a section of blank rows. ADR-0005 anticipates adding types as the way features
# arrive, so this is a path someone will take.
if set(EXTRACTORS) != INGESTED_RESOURCE_TYPES:
    raise AssertionError(
        "EXTRACTORS and INGESTED_RESOURCE_TYPES disagree: "
        f"allowlisted with no extractor {sorted(INGESTED_RESOURCE_TYPES - set(EXTRACTORS))}, "
        f"extractor for a type never ingested {sorted(set(EXTRACTORS) - INGESTED_RESOURCE_TYPES)}"
    )

_EMPTY_FIELDS: dict[str, Any] = {
    "code_text": None,
    "code_system": None,
    "code_value": None,
    "status": None,
    "value_num": None,
    "value_unit": None,
    "value_text": None,
    "effective_date": None,
    "recorded_date": None,
    "category": None,
}

COLUMNS = [
    "resource_id",
    "resource_type",
    "code_text",
    "code_system",
    "code_value",
    "status",
    "value_num",
    "value_unit",
    "value_text",
    "effective_date",
    "recorded_date",
    "category",
    "results_json",
    "raw_json",
]
INSERT_SQL = (
    f"INSERT INTO clinical_records ({','.join(COLUMNS)}) VALUES ({','.join('?' * len(COLUMNS))})"
)


def load_clinical_records(conn: sqlite3.Connection, clinical_dir: Path) -> int:
    """Loads clinical_dir's *.json FHIR resources into clinical_records. Drop-and-reload.

    Returns the number of rows written, which is *not* the number of files read: only the
    resource types in INGESTED_RESOURCE_TYPES are kept, and the rest are dropped at the door
    and never counted. An export holding other types reports fewer records than files, by
    design.

    A missing clinical_dir is a no-op that leaves existing rows alone: the table is only
    cleared once there's a source directory to reload it from, so a mistyped path can't
    silently wipe previously-ingested clinical data.
    """
    if not clinical_dir.exists():
        return 0
    conn.execute("DELETE FROM clinical_records")

    resources = []
    for path in sorted(clinical_dir.glob("*.json")):
        resource = json.loads(path.read_text())
        resource_type = resource.get("resourceType")
        if resource_type not in INGESTED_RESOURCE_TYPES:
            continue
        resource_id = resource.get("id") or path.stem
        resources.append((resource_id, resource_type, resource))

    # Built upfront so DiagnosticReport.result[] references can resolve against any other
    # resource in this same directory, regardless of file/glob order.
    fields_by_ref = {
        (resource_type, resource_id): EXTRACTORS[resource_type](resource)
        for resource_id, resource_type, resource in resources
    }

    rows = []
    for resource_id, resource_type, resource in resources:
        fields = fields_by_ref[(resource_type, resource_id)]
        results_json = (
            _resolve_diagnostic_report_results(resource, fields_by_ref)
            if resource_type == "DiagnosticReport"
            else None
        )
        rows.append(
            (
                resource_id,
                resource_type,
                fields["code_text"],
                fields["code_system"],
                fields["code_value"],
                fields["status"],
                fields["value_num"],
                fields["value_unit"],
                fields["value_text"],
                fields["effective_date"],
                fields["recorded_date"],
                fields["category"],
                results_json,
                json.dumps(resource),
            )
        )

    conn.executemany(INSERT_SQL, rows)
    return len(rows)
