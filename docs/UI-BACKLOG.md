# UI notes

**The backlog this file used to hold is empty.** All twenty-six items from the whole-app
review on 2026-09-19 have shipped; `CHANGELOG.md` is the record of what each one did. What
stays here is the part that wasn't a to-do list: how to check frontend work in a project with
no frontend test suite, and the decisions that look like inconsistencies but are deliberate.

Two source files cite this document by path, `ActivityRingsGlyph.tsx` and `SectionNav.tsx`,
so it keeps its filename even though it is no longer a backlog. (The citation runs the other
way for `lib/chartStyle.ts`: this file points at that one, not the reverse.)

If a new round of UI work starts, a fresh list belongs here under its own heading, in the
same shape as the old one: what was observed, where the code is, what to do, and how to know
it's done.

## Working on the frontend

- One PR per change. Branch prefixes and commit format are in [AGENTS.md](../AGENTS.md) and
  [CONTRIBUTING.md](../CONTRIBUTING.md): never commit to `main`, Conventional Commits, no
  `Co-Authored-By` trailer.
- Add a line to `CHANGELOG.md` under `[Unreleased]` for anything user-visible.
- Line numbers quoted below drift. Search for the quoted symbol rather than trusting the
  number.

## Verifying your work

There is **no frontend test suite** — verification is build + lint + looking at it.

```bash
cd frontend && npm run build && npm run lint   # tsc -b is part of build
uv run pytest                                  # only if you touched src/pomona/
```

Then look at the real app. If ports 8000/5173 are already taken by another project, don't
kill them — run this app on its own port in single-process mode:

```bash
cd frontend && npm run build && cd ..
POMONA_PORT=8765 uv run pomona serve    # run from the repo root
# open http://127.0.0.1:8765
```

Run `serve` **from the repo root**: `POMONA_DB_PATH` defaults to the relative path
`data/health.db`, so starting it from `frontend/` yields 503s on every API route.

Check every change in **both themes** (toggle top-right; cycles light → dark → system) and
at a **narrow width** (~400px). If the default "Last 30 days" is empty because the export
is older than that, switch the range to "Last year".

**A chart or map judged from an automation-driven browser is not evidence.** A tab that is
backgrounded, minimised or fully occluded reports `document.visibilityState === "hidden"`,
and Chrome suspends `requestAnimationFrame` entirely for a hidden document — not throttles
it, stops it. Merely lacking focus is *not* the same thing: a visible but unfocused window
still reports `visible` and still runs rAF, possibly throttled. Check
`document.visibilityState`, not `document.hasFocus()` — the two disagree exactly where it
matters. Measured in one such window: twelve rAF callbacks never arrived in 45 seconds, while
ordinary JS in the same tab ran instantly. Every draw-in animation here is rAF-driven
(recharts' series, Leaflet's zoom), so a screenshot can catch a line a third of the way
across or a tile layer still at a fraction of its final scale, and neither is a defect in
the code you just wrote. Before filing one, take a screenshot, interact with the page, and
take another — or check `document.hidden` and say so in the report. Ranges, colours, text
and layout are all safe to judge this way; only mid-animation geometry is not.

The same applies to **CSS** animations, which is easy to miss because they have nothing to
do with rAF: a hidden document doesn't advance them either. Measured on the content fade
(see `lib/transitions.ts`): eighteen `enter` animations sat at `currentTime` 0 indefinitely,
reporting `playState` "running", so every faded element computed to `opacity: 0` and
`getAnimations()` never emptied. Content that looks *missing* in such a window, not just
half-drawn, can be this. It is not a hazard for a real reader -- the fade uses
`animation-fill-mode: none`, so the animation is the only thing holding the element at zero,
and returning to the tab both resumes it and, on a reduced-motion machine, the rule never
applies at all -- but it does mean the fade cannot be judged from here. Look at it in a real
window.

## Decisions already made — don't undo these

These look like inconsistencies but are deliberate, each documented at the cited spot:

- **Bar charts and sum-mode line charts keep a zero baseline**; only avg-mode lines zoom
  to the data (`lib/chartStyle.ts:27`, `fluctuationDomain`).
- **The ECG trace is `type="linear"`**, not `monotone` (`EcgWaveformChart.tsx:86`).
- **Tooltip and label text never takes the series color**; identity is a line swatch
  (`ChartTooltip.tsx:5`).
- **Only the last point of a series is labelled** (`ChartEndLabels.tsx:3`).
- **`prefers-reduced-motion` is recharts' job, not ours** — it defaults `isAnimationActive`
  to `'auto'` and resolves that as `!isSsr && !prefersReducedMotion`, so the preference is
  already honoured. Pass `animationDuration` only (`lib/chartStyle.ts`); passing a boolean
  replaces `'auto'` and makes the app re-derive, per series, an answer the library has.
- **Gridlines are horizontal-only and solid**, axis/tick lines are off
  (`lib/chartStyle.ts`, `CHART_GRID_PROPS`). Dashing is reserved for partial buckets.
- **Sum-mode lines are `linear`, avg-mode `monotone`** (`MetricChart.tsx`): a bucket total
  is discrete, so a smooth curve would invent values between buckets.
- **Dates are never rendered as ISO strings** — format through `lib/formatDate.ts`, which
  parses `YYYY-MM-DD` by splitting it rather than via `new Date()`.
- **Every chart has a table twin** so no value is hover-only (`ExpandableChartCard.tsx:17`).
- **A skeleton matches its content's height only where that height is fixed**
  (`AllCharts.tsx`, `Overview.tsx`, `DataCard.tsx`): a chart card is 268px whatever the data, because
  the chart is always drawn at a 200px preview height, so its skeleton is 268px exactly.
  The table cards are not -- "Recent workouts" measures ~77px over a week and ~372px over a
  year, and the activity card grows ~85px when its calendar wraps to its own row -- so those
  skeleton heights are a chosen middle. Where a placeholder *can* match, it does it by
  mirroring the real thing's box rather than by carrying a copy of its measurement:
  `StatCardSkeleton` has StatCard's own three rows, and the dashboard renders that same
  component rather than a block with the number pasted into it. Don't "fix" them to one range's measurement, and
  don't pin the cards to their tallest form to make the numbers match.
- **An untouched picker writes nothing to the URL, but a choice always does**
  (`hooks/useSearchParamState.ts`): the *absence* of `?range=` is what lets Dashboard mean 30
  days and Routes mean a year while sharing the key, so the default is never written on its
  own — but deleting the key when the chosen value equals the default would make a
  deliberate "Last 30 days" indistinguishable from an untouched picker, and whether a choice
  survived the nav would depend on what the page you left defaulted to. Only
  `range`/`from`/`to`/`bucket` travel across the nav and only while valid (`navSearch`);
  `from`/`to` travel only with `range=custom`; a selected row stays on its page, except on
  the link to the page you're already on, which keeps the whole query. Param writes are
  `replace`, not `push` — Back returns to the page you came from, and the custom-date inputs
  fire per keystroke.
- **The palette is measured, not chosen by eye** (`frontend/src/index.css`): one hue per
  metric group mirroring the Health app, a green light-to-deep ramp for the activity
  calendar, and the ring trio in Apple's red/green/cyan. The comments there carry the
  contrast ratios and the colour-vision numbers, including a deliberate trade -- the group
  hues sit near 2:1 on the page because fidelity to Apple's steps was chosen over the 3:1
  WCAG asks for a meaningful graphic, which is safe only because no chart uses colour as
  its only channel. Re-measure rather than eyeball if you change a value, and sanity-check
  whatever tool you measure with (pure red against pure green must come out as the closest
  pair under deuteranopia -- a simulation that says otherwise is misapplying its matrices).
- **Map tiles must be free, keyless, account-less**
  ([ADR-0004](adr/0004-openstreetmap-tiles-for-routes-map.md)).
- **Clinical dates render in UTC** (`ClinicalPage.tsx:37`).
- **No schema migrations** — if a change needs a `SCHEMA` change, read the "Database schema"
  section of AGENTS.md first. No frontend work so far has needed one.
