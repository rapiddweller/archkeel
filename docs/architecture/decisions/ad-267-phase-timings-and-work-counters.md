# AD-267 Phase timings and work counters beside the report

**Decision.**
- `archkeel report --timings PATH` writes one JSON file with two parts: `phases` (wall-clock
  seconds) and `counters` (deterministic numbers). The report, the HTML pages and the `--json`
  result do not change. Without the flag, nothing is measured and nothing is written.
- Phases: `providers` (the survey pass of the Python collector), `collect`, `decode`
  (decompress, decode, validate once), `assemble` (including rule evaluation), `result`,
  `encode` (`architecture.json` bytes), `render` (both pages). A phase that did not run is
  absent, never zero. A collector without a subprocess (Dart) has no `providers` and no `decode`.
- Counters: files parsed, modules, calls analyzed, records, evidence records, collector wire
  bytes, `architecture.json` bytes, report page bytes. The same input gives the same counters.
- One `PhaseClock` is created by the CLI and passed on as a parameter: to the observer, so the
  collector times `providers`, `collect` and `decode` around its own work, and to the report and
  render calls. No global recorder and no environment switch.
- `tools/report_timing.py` passes `--timings`, copies both parts into its receipt
  (`phase_seconds`, `counters`) and, when `GITHUB_STEP_SUMMARY` is set, appends a Markdown table
  of both. A failed Full verification then shows which phase grew, with no log reading.
- No phase budget yet. The total budget stays the gate. Counter budgets come first, because
  counters do not depend on the runner. Phase budgets follow when CI receipts show the spread.

**Reason.** #659. #648 found a 4 times slower collector on a large project only after a crash.
AD-259 needed a separate sampling profiler to find where the time goes. On CI the same commit
ran 2.3 to 2.9 times slower than on a laptop, so one total cannot say if the runner or one phase
changed. The scaling run on 9 projects showed that the main-process phases grow linearly with
the record count, and that the collector has a fixed floor from its two passes. Counters let a
reviewer tell "the input grew" from "the code got slower".

**Rejected.**
- Timings inside `architecture.json`: they break byte-identical output.
- A module-level recorder or an environment variable: hidden state, hard to test.
- A profiler in CI: cProfile distorts the shares, and py-spy needs root.
- Phase budgets now: a budget needs measured spread, and we have one CI sample.

**Not in this decision.** The nightly benchmark on a pinned public project stays in #659.

**Check.**
- `--timings` writes the seven phases for a Python run and only the phases that ran otherwise.
- All seconds are finite and not negative. Their sum is at most the wall time of the run.
- `architecture.json`, both pages and the `--json` result are identical with and without
  `--timings`.
- Two runs on the same input give the same `counters`.
- The receipt has `phase_seconds` and `counters`. With `GITHUB_STEP_SUMMARY` set, the table is appended.
- A run that fails before a phase writes no timings file.
