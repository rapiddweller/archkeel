# Reference run for the phase timings of the core

The nightly run (Full verification, area "CLI and core") scans an unchanged public Python project and
keeps separate `validate` and HTML `report` measurements (#659, AD-878). It adds no pipeline: it is one test of the existing
nightly (`tests/test_cli_phase_timings_reference.py`, in `SLOW_FILES`) and one upload step.

## The pinned project

`sympy/` holds our files only: `archkeel.toml` and `architecture-contract.json` (drafted by
`archkeel init`, not edited) and `SOURCE.json`. The source is never committed. The pin is SymPy tag
`sympy-1.13.3`, commit `b4ce69ad5d40e4e545614b6c76ca9b0be0b98f0b`, BSD-3-Clause, about 850 modules of
`sympy/` without tests. `tools/fixture_source.py` fetches exactly that commit and refuses another.

## Run it

```sh
make core
ARCHKEEL_FETCH_SOURCES=1 uv run pytest -q -n 0 -s tests/test_cli_phase_timings_reference.py
```

- `ARCHKEEL_SOURCE_CACHE=DIR` keeps the checkout. With the checkout in `DIR` the run needs no network
  (offline replay). A cached checkout is **verified before use** (`tools/fixture_source.verify_checkout`):
  the object store must be sound (`git fsck`, no borrowed objects, replacement refs ignored), `HEAD` must
  be the pin, and the files of the folder must be exactly the files of that commit: the same type (a
  link only for a link, read with `lstat` and the exact bytes of its target; a regular file only for a
  file), the hash of each blob, and the executable bit where the checkout records it (`core.filemode`,
  POSIX). A wrong folder, another commit, a changed, added or deleted file, a link in place of a file
  (or the reverse) with the same bytes, or a damaged store is an error. The copy takes a link as a
  link and refuses one that points outside the fixture, so no byte from outside the verified tree
  comes in (the one link of the pinned Dart fixture points inside). The cache is not repaired, not deleted and not fetched again.
- `ARCHKEEL_TIMINGS_RUNS=N` sets the number of validate runs (default 5). The report series uses
  two runs to limit additional runner work until its cost is measured.
- `ARCHKEEL_TIMINGS_DIR=DIR` sets the output folder (default `test-artifacts/phase-timings`). Each run
  of the test makes **a new folder of its own** `run-<UTC time>-<random>` below it, after the source is
  verified. Nothing in `DIR` is ever deleted or reused, so a folder with your files, or a second run at
  the same time, is safe.
- Each series has its own `validate/` or `report/` folder. The run folder holds `run-N.timings.json`
  for each run (the file of `--timings`, which never replaces one). The report series also holds
  `run-N.timings.html` for each run. Both series have `summary.json` (the pin, the command, the
  machine, each run and the spread) and
  `summary.md` (the table, also written to the job summary of CI). CI uploads the whole output folder.

## What is measured, and what is not

- `cli_wall_seconds`: the command from start to exit. `core_seconds` and `phases`: inside the core.
  `outside_core_seconds`: the difference. `peak_rss_bytes`: the largest resident set of one process of the
  command (the core), not a sum. The three are never mixed.
- The test checks that all runs give one exit code and one frame, that each timings file keeps the
  protocol, and that the core time lies inside the command time.

## Not set yet

- **No limit.** No budget per phase, no ratchet, no ratio. The two time limits that exist are safety
  limits against a hang, not budgets: 600 s for one core run (`native_scan.py`) and 40 minutes for a
  Full job. The spread of one laptop run (load about
  9) was 8 to 16 % of the median for the wall time, and 1 % for the memory; small figures such as
  `outside_core_seconds` spread over 160 %. The spread on the CI runner is not known.
- Open before a limit: how many nights give a stable spread, whether a limit uses the median or the
  largest of the runs of one night, and whether it is a ratio to the previous nights. Decide it from the
  artifacts (`phase-timings-CLI and core`, kept 30 days) and the job summaries, not before.
- One project, one language. Another pinned project (a larger one, or TypeScript) is a later step.
