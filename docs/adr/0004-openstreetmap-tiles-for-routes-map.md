# ADR-0004: OpenStreetMap tiles for the routes map

- **Status:** Accepted
- **Date:** 2026-08-19

## Context

`apple_health_export/workout-routes/` (GPX tracks for outdoor workouts) was deliberately
out of scope for v1 (`TODO.md`, `docs/DESIGN.md`). Real data confirms it's worth building:
every outdoor workout in the export has a matching route, and there's enough volume (447
files, ~26MB for the current year) to make a map view worthwhile.

Every other part of this app runs fully local and offline: SQLite storage, no in-app chat
(ADR-0002 chose local Claude Code over any external API), and the frontend has never made
a single request outside its own origin -- even the UI font is bundled via
`@fontsource-variable/geist` rather than loaded from Google Fonts. A route map needs a
basemap to be useful (a bare polyline of lat/lon points, with no streets or geography, tells
you almost nothing about where a run actually was), and no basemap exists without fetching
map tile images from somewhere. This is the first feature in the app that has a real reason
to reach outside localhost.

## Decision

**Render the Routes tab with Leaflet + OpenStreetMap's public raster tile servers**
(`{s}.tile.openstreetmap.org`), fetched live in the browser each time the tab is viewed.
No API key, no account, no cost. GPX points themselves never leave the browser -- only the
tile *images* are requested, addressed by generic `{z}/{x}/{y}` map-grid coordinates, not
by any of the actual route coordinates.

**Dark theme is a CSS filter over the same OSM tiles** (`invert` + `hue-rotate(180deg)`
plus brightness/contrast/saturation tuning, in `RoutesMap.css`), applied to Leaflet's tile
pane only so route polylines and popups keep their real colors. It's keyed off the app's
resolved theme (`useResolvedTheme` in `hooks/useTheme.tsx`), so the map matches the rest of
the UI, including "system" on a dark OS.

*Amended 2026-09-19:* dark mode originally used a second tile source, CARTO's `dark_all`
basemap (`{s}.basemaps.cartocdn.com/dark_all`). CARTO has since started stamping "API KEY
REQUIRED" across every keyless tile, which breaks this ADR's no-key/no-account rule. Rather
than swap in another third-party dark source whose keyless access could change the same
way, dark mode now filters the one tile source this decision already depends on. The
trade-off: a filtered basemap is less polished than a purpose-designed dark style (label
halos and some fills look slightly off).

*Amended 2026-09-24:* **the basemap is now off until switched on**, per-browser, remembered
(`hooks/useBasemap.ts`); the `TileLayer` is not mounted while it is off, so nothing is
requested. Two things forced this. The privacy consequence below was recorded here but the
README claimed the opposite ("no external services"), so the honest default is the one that
makes the claim true. And this decision weighed OSM's tiles as free "for this kind of
low-volume personal use" — which is what one person's dashboard is, and what a published
project installed by strangers is not. OSM offers those tiles for the former. Off by default
means most installs never request one, which keeps the project inside the terms it relies on
rather than quietly depending on donated infrastructure at unknown scale.

The tile URL and its attribution are also overridable at build time
(`VITE_TILE_URL` / `VITE_TILE_ATTRIBUTION`, see `frontend/.env.example`) for anyone who would
rather use their own provider — including a paid one with a key. That does not change this
ADR's no-key rule: no key is required, and none can become required, because the default
source still needs none. Attribution is overridable alongside the URL because it is not
transferable; OSM's credit applies to OSM's tiles.

## Alternatives considered

| Option | Why not |
|---|---|
| Vector-only route shapes, no basemap | Fully offline, matches the app's design exactly, and was the first option raised. Rejected because it throws away the one thing that makes a map useful here -- knowing *where* a route was, not just its shape. A shape-only view answers "what does my Tuesday run look like" but not "where do I usually run," which is the more interesting question. |
| Self-hosted / bundled offline vector tiles | Keeps everything local. Rejected as far too much setup for what this feature is worth: a real offline basemap means shipping or downloading a vector tile dataset (hundreds of MB to GBs depending on coverage), plus a tile-serving or client-side rendering pipeline this project has no other reason to carry. |
| Paid tile provider (Mapbox, Google Maps, etc.) | Adds an API key, a account, and a cost to a project whose whole premise is "free, local, no accounts." OSM's tiles are free for this kind of low-volume personal use and need none of that. |

## Consequences

Viewing the Routes tab requires internet access; without it, the tab still lists routes and
draws them, but with a blank/gray basemap. Viewing it reveals the approximate lat/lon
bounding box of your routes to OpenStreetMap's tile infrastructure -- ordinary map-tile
traffic, not your health data, but a real departure from "nothing ever leaves this
machine." If that tradeoff stops being acceptable, revisit in favor of the self-hosted
tile alternative above; the frontend only touches this decision in one place
(`RoutesMap.tsx`'s `TileLayer` URL), so swapping it later is a small, contained change.
