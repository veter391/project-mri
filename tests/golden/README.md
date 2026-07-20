# Golden baseline

`baseline_report.json` is the reference output of a full scan over a fixed
fixture repository (built in code by `build_fixture_repo`). `test_golden.py`
rebuilds that fixture, scans it, and asserts the analysis still matches. An
unintended change to any analyzer's numbers fails there — this is the regression
net the whole rebuilding plan leans on (Phase 0.3, Phase 11.2).

## What is compared

The scan report, with volatile fields scrubbed and path separators normalised
(see `normalize` in `__init__.py`), so only the *analysis* is compared — never
the environment it ran in:

- timestamps, durations, and the scan UUID → `<volatile>`
- the absolute repo path → `<volatile>`
- backslashes → forward slashes

Determinism is engineered so the same bytes are produced on every OS: fixture
files are written with an explicit `\n`, commits use fixed author/committer
dates, and every analyzer orders its output lists with a stable secondary key
(the module name) so equal-valued entries never reorder.

## When the scan output changes on purpose

1. Confirm the change is intended and understood — this is the "document every
   intentional metric change" discipline.
2. Regenerate the baseline:

   ```
   MRI_UPDATE_GOLDEN=1 pytest tests/test_golden.py -q
   ```

3. Add a dated line to the changelog below describing the delta and its cause,
   then commit the new `baseline_report.json` together with the code change.

A baseline regeneration with no matching code change and no changelog entry is a
red flag in review — it usually means real drift was rubber-stamped.

## Changelog

- 2026-07-20 — Initial baseline captured (Phase 0.3). Fixture: two-commit Python
  repo (`app.py` with a branch + a growing function, `util.py`). Established
  alongside the analyzer determinism fix (stable secondary sort keys), so the
  baseline is reproducible across runs and platforms.
