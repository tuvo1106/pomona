# Pomona

**Pomona** — after the Roman goddess of orchards — is a local dashboard for your Apple
Health export: trends over time, backed by a local SQLite database for fast querying. It
runs on your machine, and your health data stays there — there is no server to send it to,
no account, and no API key.

One deliberate exception, stated here rather than buried: the Routes tab can draw a street
basemap behind your GPS tracks, and those map tiles come from OpenStreetMap. **It is off
until you turn it on.** Requesting a tile tells that server which map square you're looking
at, which is roughly where you walk and run — no health data, but not nothing. With the
basemap off, the app makes no request outside its own origin at all; your tracks still draw,
on a plain surface. See [ADR-0004](docs/adr/0004-openstreetmap-tiles-for-routes-map.md).

To ask natural-language questions about your data, just ask Claude (e.g. in a Claude Code
session) directly against `data/health.db` — no separate chat feature or API key needed here.

> **This is a personal project, not a medical device.** Nothing here is medical advice, and
> the numbers are not validated against Apple's own aggregations — this app buckets and
> averages raw records with its own rules, so a figure may legitimately differ from what the
> Health app shows for the same range. Use it to look at your data, not to make decisions
> about your health.
>
> **Not affiliated with, endorsed by, or connected to Apple.** Apple, Apple Health, Apple
> Watch and HealthKit are Apple's trademarks, and they appear here only to say what this app
> reads — see [ADR-0006](docs/adr/0006-rename-the-project-to-pomona.md).

## Install

Needs [uv](https://docs.astral.sh/uv/), which fetches the Python it needs (3.12+) itself, and
Node **20.19+ or 22.12+** — the range Vite requires, so 20.18 and 21.x won't work.

```bash
git clone https://github.com/tuvo1106/pomona.git
cd pomona
uv sync
cd frontend && npm install && cd ..
```

Then pick one of the next two sections. You do not need your own health data to start.

## Try it with demo data

This generates a synthetic export — a fictional person, a seeded PRNG, no real health data
anywhere near it — and runs the app on it:

```bash
uv run python scripts/make_demo_export.py
uv run pomona ingest demo_health_export/export.xml --db data/demo.db
cd frontend && npm run build && cd ..
POMONA_DB_PATH=data/demo.db uv run pomona serve
# open http://127.0.0.1:8000
```

About a second each for the first two, and it fills everything: a year-plus of all 44 charted
metrics, ~230 workouts with GPS tracks, activity rings, ECG recordings and a set of FHIR clinical
records.

Note the separate `--db`. Ingest is drop-and-reload, so pointing it at the default database would
replace a real export you'd already imported. Keeping the demo in its own file lets you switch
between them by changing one variable.

The output is gitignored and reproducible: the same `--seed` and `--end-date` give the same bytes
on any machine, which is what makes screenshots comparable. `--days` and `--out` exist too, and
`--help` lists them. It clears its own output between runs and refuses to write into a directory
it didn't create, so `--out apple_health_export` can't land on a real export.

It's deliberately not a clean dataset. Some days are missing entirely, one stretch is a quiet
week, two devices log overlapping steps so deduplication has something to do, and a week is
recorded in another timezone. Data that behaves is data that hides bugs.

## Use your own data

**[docs/YOUR-DATA.md](docs/YOUR-DATA.md) is the walkthrough** — how to get the export off your
phone, what's in it, what's ignored, how long ingest takes, and what to do when something looks
wrong. The short version, once `apple_health_export/` is sitting in the repo root:

```bash
uv run pomona ingest apple_health_export/export.xml
cd frontend && npm run build && cd ..
uv run pomona serve
# open http://127.0.0.1:8000
```

The subdirectories (`clinical-records/`, `workout-routes/`, `electrocardiograms/`) are found
automatically as siblings of `export.xml`. Ingest takes about a minute for 3.4 million records,
and it's safe to re-run whenever you have a fresh export.

`.env.example` has optional overrides for the database path, host and port (`cp .env.example .env`
to use them). None are required.

## Stack

- **Backend**: Python, FastAPI, SQLite (stdlib `sqlite3`, no ORM) — a one-time ingest of `export.xml` and `clinical-records/` into a local DB, then fast indexed queries.
- **Frontend**: React + TypeScript via Vite, Tailwind CSS + shadcn/ui for components, Recharts for charts, TanStack Query for data fetching. A global time-range filter — Today, last 7 / 30 / 90 days, last year, all time, or a custom range — drives every chart and list, and lives in the URL.
- **Tooling**: `uv` for Python deps/env, `ruff` for lint/format, `pytest` for tests, `lefthook` for git hooks.

## Working on it

Once, after cloning — this installs the `commit-msg` hook that enforces the commit convention.
[lefthook](https://lefthook.dev/) is a separate binary, not a project dependency, so install it
first (`brew install lefthook`, or see their docs):

```bash
lefthook install
```

Two long-running servers, one per terminal:

```bash
# terminal 1 — API, reloads on change
uv run fastapi dev src/pomona/api/app.py

# terminal 2 — frontend dev server on http://localhost:5173
cd frontend && npm run dev
```

Tests and checks, from the repo root:

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
cd frontend && npm run build && npm run lint && cd ..
```

[CONTRIBUTING.md](CONTRIBUTING.md) has the commit, PR and ADR conventions; [AGENTS.md](AGENTS.md)
has how to work in the code.

## License

[MIT](LICENSE)

The app's mark -- one ECG deflection -- was drawn for this repo and is covered by that
licence along with everything else. It is not derived from anyone else's mark. It lives in
`frontend/public/favicon.svg` (the tab) and `frontend/src/components/AppMark.tsx` (the
header); the home-screen PNGs beside it are generated from the same geometry by
`frontend/icons/render.py`.
