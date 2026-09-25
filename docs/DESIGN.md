# Design

## Goal

Pomona is a local personal dashboard for Apple Health data: trends over time, backed by a database
persisted locally for fast querying. Single-user, runs entirely on one machine. Natural-language
questions about the data are answered by asking Claude directly against the local SQLite file
(e.g. in a Claude Code session) rather than through an in-app chat feature — see
`docs/adr/0002-sqlite-storage-streaming-ingestion-no-in-app-chat.md`.

## v1 scope

**In scope**, from `apple_health_export/`:
- `export.xml` — all `<Record>` elements (steps, heart rate, sleep, weight, HRV, blood pressure,
  active/resting energy, distance, SpO2, etc.), `<Workout>` elements, `<ActivitySummary>` elements.
- `clinical-records/` — FHIR R4 JSON: Observation (labs), Condition, Immunization,
  DiagnosticReport, DocumentReference. That list is an **allowlist**
  (`INGESTED_RESOURCE_TYPES` in `clinical.py`): a provider's export can hold other resource
  types, and anything the app has no view for is dropped as the directory is read rather than
  stored and then rendered as a raw-named pane. See
  [ADR-0005](adr/0005-ingest-only-the-clinical-types-the-app-renders.md).
- `workout-routes/` — GPX tracks for outdoor workouts, matched to their `workouts` row by time
  overlap and rendered on a map (Leaflet + OpenStreetMap tiles — the one exception to this
  app's otherwise fully local/offline design; see
  `docs/adr/0004-openstreetmap-tiles-for-routes-map.md`).
- `electrocardiograms/` — single-lead Apple Watch ECG recordings (CSV), charted as a
  downsampled waveform (see `waveform.py`) with per-recording classification/device metadata.

**Out of scope for v1** (tracked in `TODO.md`): `export_cda.xml`, `Correlation` elements,
materialized rollup tables.

## Architecture

```
apple_health_export/           uv run pomona ingest
  export.xml            ─────┐
  clinical-records/*.json ───┤
  workout-routes/*.gpx    ───┼──►  SQLite (data/health.db)
  electrocardiograms/*.csv ──┘
                                       │
                              FastAPI (src/pomona/api/)
                                       │
                                 /api/* (JSON)
                                       │
                    React (frontend/, Vite + Recharts + TanStack Query + Leaflet)
```

- **Ingest** (`src/pomona/ingest/`): one-time (rerunnable) CLI command. Streams
  `export.xml` with `iterparse` (memory-safe at 1.5GB), batches inserts into SQLite inside a
  single transaction. `clinical-records/*.json`, `workout-routes/*.gpx`, and
  `electrocardiograms/*.csv` are each loaded separately (small files; GPX routes are matched
  to their `workouts` row by time overlap, not by filename). Drop-and-reload on each run — see
  `docs/adr/0002-sqlite-storage-streaming-ingestion-no-in-app-chat.md`.
- **Storage**: SQLite, six tables — `records`, `workouts`, `activity_summaries`,
  `clinical_records`, `workout_routes`, `ecg_recordings` — with composite indexes for
  `(type, date)` filtering. No ORM.
- **API** (`src/pomona/api/`): FastAPI, JSON routes for metric time series, workouts,
  activity summaries, clinical records, GPS routes, ECG recordings, and an overview. Serves the
  built React app as static files in "just run it" mode.
- **Frontend** (`frontend/`): React + TypeScript, Vite, Recharts, TanStack Query, Leaflet. Four
  tabs: the main dashboard (overview strip, per-metric trend charts, workouts list, clinical
  records list), a clinical-records page, a routes map, and an ECG waveform viewer.

## Schema

See `docs/adr/0002-sqlite-storage-streaming-ingestion-no-in-app-chat.md` for the rationale and
`src/pomona/db.py` for the authoritative DDL.
`docs/adr/0003-synthetic-row-ids-and-no-schema-migrations.md` covers why `clinical_records` is
keyed on a synthetic row id rather than the FHIR resource id, and why there are no migrations.
`docs/adr/0004-openstreetmap-tiles-for-routes-map.md` covers the routes map's one departure
from this app's otherwise fully local/offline design.
