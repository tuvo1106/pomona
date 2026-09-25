---
name: Bug report
about: Something isn't working
labels: bug
---

<!-- ───────────────────────────────────────────────────────────────────────────
     Please don't paste your own health data.

     This is a health dashboard, so the natural way to report a bug is to show
     the chart or the export rows that produced it. Anything you put in an issue
     is public and permanent, including in screenshots.

     Instead, reproduce it against the synthetic export:

         uv run python scripts/make_demo_export.py
         uv run pomona ingest demo_health_export/export.xml --db data/demo.db

     If it reproduces there, say so and give the --seed, --days AND --end-date
     you used. All three: --end-date defaults to today, so the same seed on a
     different day produces a dataset shifted by the difference -- different
     weekday alignment, different range boundaries, and anything that depends on
     the last-day-of-data edge may not reproduce at all. Passing an explicit
     --end-date makes the run repeatable for good.

     If it only happens with your own data, describe the shape of it -- "a day
     with two sources logging overlapping steps", "a workout with no distance" --
     rather than the values, and redact any screenshot.
     ─────────────────────────────────────────────────────────────────────── -->

**What happened**

**Expected**

**Steps to reproduce**

1.

**Does it reproduce with the demo export?**

<!-- Yes / No / Haven't tried. If yes, the exact command -- all of --seed, --days and
     --end-date, since --end-date defaults to today and the dataset moves with it. -->

**Environment**

- Pomona version or commit:
- OS:
- Python (`uv run python --version`) and Node (`node --version`):
- Browser, if it's a display problem:

**Anything in the logs**

<!-- The terminal running `pomona serve`, and the browser console for display problems.
     Check these for file paths and dates before pasting. -->
