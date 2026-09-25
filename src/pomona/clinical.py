"""Policy about clinical record types, shared by the ingest and API layers.

It lives here rather than in `ingest/clinical_loader.py` because the API has to apply the
same policy and the API layer doesn't import from `ingest` -- it reads from `db`, `dedup`,
`metrics` and `waveform`, all top-level like this one. A copy in each place would be the
failure this module exists to prevent: see ADR-0005.
"""

# An allowlist, not a skip-list: only these resource types are ingested, and anything else in
# `clinical-records/` is dropped at the door.
#
# A FHIR export can contain resource types this app has no view for, and some of them are the
# most sensitive material in the whole export. A skip-list would have to name each one to
# exclude it, which means an export containing a type nobody thought of gets it stored and then
# rendered -- the clinical page gives any type it doesn't recognise its own section, titled with
# the raw resource-type string and holding rows the app has no extractor for, so every flattened
# column is empty. Inverting that is the whole point: a type earns its way in by having
# somewhere to be displayed.
#
# One list, not an ingest list and a serve list. There was briefly a second constant for types
# ingested but not served, holding `Patient` -- the export's own demographics record. Nothing
# ever read it: the row stored a full name, gender and date of birth, which made it the single
# most identifying row in the database, written on every ingest and queried by nothing. A type
# with no reader does not need a policy, it needs deleting.
#
# The boundary is the resource type, not the subject matter. A provider that returns a panel
# result as an Observation, or a diagnosis recorded as a Condition, is unaffected by this.
INGESTED_RESOURCE_TYPES = frozenset(
    {
        "Condition",
        "Immunization",
        "Observation",
        "DiagnosticReport",
        "DocumentReference",
    }
)
