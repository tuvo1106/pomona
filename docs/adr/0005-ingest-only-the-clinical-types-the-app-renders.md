# ADR-0005: Ingest only the clinical resource types the app renders

- **Status:** Accepted
- **Date:** 2026-09-25

## Context

This repo is being published. The plan is not to flip this one public but to seed a fresh
public repository from the finished tree, under a new name, with its own history — so
whatever the code does on the day it is copied is what strangers see, and a personal export
is the thing it is pointed at on first run.

`clinical-records/` is the most sensitive part of an Apple Health export. It is FHIR R4, and
what a provider puts in it is not this project's decision: the directory holds whatever
resource types that provider exports, which can include categories this app has no view for
and would not choose to store.

The loader originally kept everything it found. An unrecognised type became a row with every
flattened column empty, on the reasoning that the raw payload cost nothing to keep. Two things
make that wrong, both found while reducing what the app stores:

- A row that exists can be queried, logged, or end up in a backup. "We don't display it" is
  not the same claim as "we don't have it", and only the second one is worth making.
- The clinical page renders any resource type missing from its `SECTION_ORDER` as a section of
  its own, titled with the raw type name. `orderedTypes` in `pages/ClinicalPage.tsx` puts the
  known types first and everything else after them, so it lands at the bottom rather than up
  top — but it is still a titled pane carrying an internal identifier as a heading, and since
  there is no extractor for it every flattened column is empty. So the page acquires a section
  labelled with a FHIR type name, listing rows with nothing in them, for data the app never
  meant to hold.

## Decision

**The resource-type list is an allowlist, not a skip-list.** `INGESTED_RESOURCE_TYPES` in
`pomona/clinical.py` names the types the app has a view for; everything else in
`clinical-records/` is dropped as the directory is read. A new resource type appearing in
someone's export is a no-op until somebody gives it a place to be displayed.

Two layers apply it, and both are load-bearing:

- `ingest/clinical_loader.py` keeps only allowlisted types, before anything downstream sees
  them — including the `DiagnosticReport` reference map built from the same set.
- `api/dashboard.py` serves only `INGESTED_RESOURCE_TYPES`, as a SQL `IN` rather than a
  `NOT IN`, reading that same constant rather than repeating it. This matters separately:
  a database built before a type left the list still holds those rows until the next
  drop-and-reload, and this is what stops them being served in the meantime.

The boundary is the resource type, not the subject matter. A provider that returns a panel
result as an `Observation`, or a diagnosis recorded as a `Condition`, is unaffected and still
displays — the app cannot and does not attempt to judge the contents of a type it renders.

There is one list, not an ingest list and a serve list. A second constant briefly held
`Patient` — the export's own demographics record — as ingested-but-not-served, on the stated
grounds that the loader read the patient reference from it. Nothing read it. The row stored a
full name in `code_text`, gender in `status` and date of birth in `value_text`, which made it
the most identifying row in the database, written on every ingest and queried by nothing. In a
decision about storing less, that was the row to remove; a type with no reader doesn't need a
policy. The demo generator still writes a `Patient` resource, because a real export has one and
it is what makes the tests exercise the allowlist end to end.

## Alternatives considered

| Option | Why not |
|---|---|
| Keep the skip-list, name each excluded type | Every exclusion has to be thought of in advance, and the failure mode for one nobody thought of is storage plus a raw-named pane. An allowlist fails the other way: the cost of forgetting a type is that a feature doesn't appear, which somebody notices and nothing leaks. |
| Ingest everything, filter in the page | The row still exists, and a row that exists can be queried, logged or backed up. It also puts the guarantee in the layer most likely to be restyled by someone who doesn't know it is load-bearing. |
| Allowlist at ingest only, no API change | Correct for a fresh ingest and wrong for every existing database, which keeps its rows until the next drop-and-reload. Since the page renders unrecognised types, those users would see the raw-named pane described above. Both layers, or neither. |
| Make it configurable | A setting is a thing to get wrong once, and its safe default would have to be the allowlist anyway — at which point it is a switch whose only purpose is to make the app store more than it can show. |
| Drop the whole clinical tab | Considered, and deferred rather than rejected: conditions and lab results are sensitive too. Kept for now because the tab is genuinely useful and these are the types the app actually renders. Revisit if that judgement changes. |

## Consequences

A resource type absent from `INGESTED_RESOURCE_TYPES` is invisible to this app, and
re-ingesting removes any such rows an older database already holds. There is no setting to
bring one back; adding a type is a code change under review, alongside the section entry and
title that give it somewhere to go.

Adding a type means touching four places: `INGESTED_RESOURCE_TYPES`, `EXTRACTORS` in
`ingest/clinical_loader.py`, and `SECTION_ORDER` plus `SECTION_TITLES` in
`pages/ClinicalPage.tsx`. That is the intended friction, and the page's comment points at the
allowlist so the connection isn't guesswork.

`EXTRACTORS` is the one that bites if it is missed, and it is checked rather than documented:
`clinical_loader.py` compares the two sets at import and raises if they disagree, because a type
on the allowlist with no extractor is stored with every flattened column empty — the outcome this
ADR exists to prevent. That check fires at import, so it takes out `ingest` and `serve` alike with
a traceback rather than a message; that is the intended trade for an invariant which is either
true at startup or not at all, but it is the reason this list says four and not three.

Three tests hold this in place (`tests/ingest/test_clinical_loader.py`,
`tests/api/test_dashboard_routes.py`, `tests/test_demo_export.py`), and the `Procedure`
fixture stays in `tests/fixtures/clinical-records/` on purpose: without a resource to look
for, the check could be removed with every test still passing.
