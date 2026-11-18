# Reference run for the phase timings of the core

The nightly run (Full verification, area "CLI and core") scans an unchanged public Python project and
keeps the seconds of each phase (#659, AD-878). It adds no pipeline: it is one test of the existing
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
  (offline replay).
- `ARCHKEEL_TIMINGS_RUNS=N` sets the number of runs (default 5). `ARCHKEEL_TIMINGS_DIR=DIR` sets the
  output folder (default `test-artifacts/phase-timings`).
- Each run writes its own file `run-N.timings.json` (the file of `--timings`, never replaced). The test
  adds `summary.json` (the pin, the machine, each run and the spread) and `summary.md` (the table, also
  written to the job summary of CI).

## What is measured, and what is not

- `cli_wall_seconds`: the command from start to exit. `core_seconds` and `phases`: inside the core.
  `outside_core_seconds`: the difference. `peak_rss_bytes`: the largest resident set of one process of the
  command (the core), not a sum. The three are never mixed.
- The test checks that all runs give one exit code and one frame, that each timings file keeps the
  protocol, and that the core time lies inside the command time.

## Not set yet

- **No limit.** No budget per phase, no ratchet, no ratio. The spread of one laptop run (load about
  9) was 8 to 16 % of the median for the wall time, and 1 % for the memory; small figures such as
  `outside_core_seconds` spread over 160 %. The spread on the CI runner is not known.
- Open before a limit: how many nights give a stable spread, whether a limit uses the median or the
  largest of the runs of one night, and whether it is a ratio to the previous nights. Decide it from the
  artifacts (`phase-timings-CLI and core`, kept 30 days) and the job summaries, not before.
- One project, one language. Another pinned project (a larger one, or TypeScript) is a later step.
