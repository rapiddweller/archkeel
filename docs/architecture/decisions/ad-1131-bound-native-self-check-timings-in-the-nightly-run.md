# AD-1131 Bound native self-check timings in the nightly run

**Status.** Accepted. Builds on AD-1120 and AD-878. Closes #2036.

**Decision.** A scheduled Full run checks the native self-check timing sidecar.
It fails with the phase name when a value exceeds its budget. It also fails
when the timing or its result is missing, malformed or refused. PR and main CI
report the same comparison without failing on a timing budget.

The budgets in seconds are: core 1100, prepare 0.1, collect 200, validate 0.4,
evaluate 4, render 0.3 and join 0.1. `core_seconds` includes time that no phase
names. The sidecar stays outside the deterministic result frame.

**Evidence.** Five completed main CI jobs on 2026-11-26, on `ubuntu-24.04`,
ran the native report with `--topology` and the timing sidecar. Their revisions
were `976eb3ab5a`, `b7e0b11c22`, `da5f9e6926`, `3af4cc4c25` and
`f80d029889`. The measured core seconds were 317.850, 347.252, 425.778,
402.505 and 541.473. The maximum seconds per phase were prepare 0.042611,
collect 95.277369, validate 0.183081, evaluate 1.794455, render 0.148510
and join 0.000000.

**Reason.** Five samples do not establish a reliable p95. Each limit is twice
the observed maximum, rounded up. Join uses a 0.1-second floor because every
sample rounded to zero. This leaves room for runner variation.

**Limit.** The samples used the gate profile; Full uses the release profile.
Runner load was not recorded. These are provisional limits, not a speed claim.
All five architecture results were UNKNOWN. A comparison of their timings is
not an architecture PASS or a performance win. There is no total CLI wall-time
budget because the sidecar does not measure it. Review the limits after more
Full runs.

**Check.** `tests/test_native_timing_budget.py` checks missing, malformed,
refused, UNKNOWN and over-budget results, and the CI enforcement scope.
