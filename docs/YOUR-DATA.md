# Getting your own data in

Pomona reads an Apple Health export. This is how to get one, where to put it, and what happens
to it. If you only want to see the app work, you don't need any of this — generate a synthetic
export instead (see the README) and come back later.

Nothing here uploads anything. The export comes off your phone, onto your computer, into a
SQLite file on your own disk, and stays there.

## 1. Export from the Health app

On the iPhone that has your health data:

1. Open **Health**.
2. Tap your **profile picture**, top right.
3. Scroll to the bottom and tap **Export All Health Data**.
4. Confirm **Export**.
5. Wait, with the Health app left open. This takes several minutes for a long history.
6. When the share sheet appears, send `export.zip` to your computer: AirDrop, Save to Files or
   iCloud Drive. It can be a few hundred megabytes, so pick a route that handles that.

Apple moves this button between iOS versions. If it isn't at the bottom of the profile screen,
it's the only thing in Health called "Export", so search the Settings within Health for it.

There is no way to export a date range or a subset. It is all of it or none of it.

## 2. What you get

Unzipping `export.zip` gives a folder called `apple_health_export`. For a nine-year history with
daily Apple Watch use, that folder is around 2.2GB:

| Path | Size | What Pomona does with it |
|---|---|---|
| `export.xml` | ~1.4GB | **Everything.** Metric records, workouts, daily activity summaries. |
| `workout-routes/` | ~235MB | GPS tracks for outdoor workouts, drawn on the Routes tab. |
| `electrocardiograms/` | ~2MB | Single-lead ECG recordings, drawn on the ECG tab. |
| `clinical-records/` | ~500KB | FHIR records from providers: labs, conditions, immunizations. |
| `export_cda.xml` | ~520MB | **Nothing.** Ignored entirely — see below. |

Your sizes will differ, mostly with how long you've had a watch. `export.xml` is a single XML
file with millions of `<Record>` elements, which is why ingest streams it rather than loading it.

**`export_cda.xml` is ignored.** It's a second copy of some of the same data in HL7 CDA format,
for sending to a doctor's system. Pomona never opens it, so you can delete it and reclaim the
~520MB. Nothing will notice.

**Only some of `clinical-records/` is read.** That directory is FHIR JSON, and what a provider
puts there varies. Five resource types are ingested — labs (`Observation`), `Condition`,
`Immunization`, `DiagnosticReport` and `DocumentReference` — and every other type is dropped as
the directory is read rather than stored. Pomona keeps what it has a screen for, so a type it
doesn't recognise is a no-op rather than a pane headed by a FHIR type name listing rows it can't
format.

That means some of what your provider sent won't appear: medication resources, procedures,
coverage and encounter records are all common in these exports and none are ingested. Neither is
the `Patient` record holding your name and date of birth — nothing in the app read it, so it
isn't stored. None of this is deleted from your export; it just isn't copied into the database.
See [ADR-0005](adr/0005-ingest-only-the-clinical-types-the-app-renders.md).

## 3. Put it where the command expects

Move the unzipped folder to the root of this repo:

```
pomona/
├── apple_health_export/      <- here
│   ├── export.xml
│   ├── clinical-records/
│   ├── electrocardiograms/
│   └── workout-routes/
├── data/
└── src/
```

`apple_health_export/` is gitignored, so it cannot be committed by accident.

It doesn't have to live here — every path is a flag (see below). This is just the layout the
commands in the README assume.

## 4. Ingest

```bash
uv run pomona ingest apple_health_export/export.xml
```

That's the whole command. The three subdirectories are found automatically as siblings of
`export.xml`, so you only name them if your layout differs:

```bash
uv run pomona ingest path/to/export.xml \
  --clinical-dir path/to/clinical-records \
  --routes-dir   path/to/workout-routes \
  --ecg-dir      path/to/electrocardiograms \
  --db           data/health.db
```

**How long:** about **a minute** for 3.4 million records — roughly nine years of continuous
Apple Watch use. A progress bar with an ETA shows the XML pass; `--fast` skips the pre-count that
the ETA needs and just shows a running counter, which is slightly quicker and much less useful.

**What it produces:** one SQLite file, `data/health.db` by default, around the same size as
`export.xml`. Also gitignored.

**It's safe to re-run.** Ingest is drop-and-reload: it rebuilds every table from scratch inside a
single transaction, so running it twice is the same as running it once, and a crash halfway
leaves the previous database untouched. There is no partial or incremental import.

**One thing to know:** because it's drop-and-reload, pointing `--db` at an existing database
replaces it. That matters mainly if you've been looking at the demo data — keep the two in
separate files (`--db data/demo.db`) rather than overwriting one with the other.

## 5. Look at it

```bash
cd frontend && npm run build && cd ..
uv run pomona serve
# http://127.0.0.1:8000
```

## 6. Getting fresh data later

Export again from the phone and re-ingest. Same command, no cleanup needed.

Until you do, **the app's date ranges end on your most recent day of data, not today.** "Last 30
days" means the 30 days up to the last day in your export, which is deliberate: anchoring to
today would silently shrink every range as the export aged, and a chart labelled "last 30 days"
would quietly be showing you twelve. The header tells you which date that is, and suggests
re-exporting once the data is more than a week old.

## 7. If something goes wrong

**`No health database at data/health.db`** — the server is running but nothing has been
ingested, or `--db` and `POMONA_DB_PATH` disagree about where the database is. The page says
which path it looked at.

**`table X has no column named Y`, or `no such column`** — you pulled a newer version of Pomona
whose schema differs from the database you already built. There is no migration system on
purpose ([ADR-0003](adr/0003-synthetic-row-ids-and-no-schema-migrations.md)): the database is a
derived artifact, so the fix is to delete it and ingest again. The CLI says this when it
happens rather than leaving you with the raw SQLite error.

**A whole tab is empty, but the header date looks current** — the date in the header is the
newest day across *all* your data: metric records, workouts and ECG recordings together. Each
tab's relative range is anchored to that one date, so a tab whose own data stopped earlier shows
nothing while the header still reads today. If your last ECG was two years ago, the ECG tab's
"Last year" is a year of nothing; same for Routes if you haven't recorded an outdoor workout in
a while. Switch that tab to **All time** to see what it does have.

This is the one case where the anchoring in §6 doesn't help: it keeps the window on the end of
your data rather than on today, but "your data" is global, and a tab only knows about its own.

**A card says "No data in this range."** — Pomona builds the card list from the types actually
present, so a type your export has never contained gets no card at all rather than an empty one.
A card that appears and then says this means the type exists somewhere in your history but not in
the range you're looking at — the list is held over from the previous range while the new one
loads, so switching ranges can leave a card behind for a moment. Widening the range fills it in.

**Routes are missing** — a GPX track is matched to a workout by overlapping timestamps. Tracks
that match nothing are still imported and still drawn, but dated by your computer's timezone
rather than the workout's, so they can land on the wrong day.

## What leaves your machine

Nothing, with one exception, which is off by default: the Routes tab can draw a street map
behind your tracks, and those tiles come from OpenStreetMap — so turning it on tells that
server which map squares you're looking at. It ships off, there's a toggle on the page, and
with it off the app makes no request outside its own origin.
See [ADR-0004](adr/0004-openstreetmap-tiles-for-routes-map.md).

There is no account, no telemetry, no analytics, no crash reporting, and no API key.
