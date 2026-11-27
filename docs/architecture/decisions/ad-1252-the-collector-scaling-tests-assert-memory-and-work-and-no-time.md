# AD-1252 The collector scaling tests assert memory and work, and no time

**Status.** Accepted. Owner decision of 2026-11-27 (drift gates audit, step E). Amends AD-323, AD-335 and AD-340.

**Reason.** A ratio of CPU times or an absolute time cap depends on the runner and on the build profile. It needs a
"minimum measurable time", a doubling search and interleaved runs to give a stable answer. #363 was real quadratic
code, and the guard against it stays. The guard needs a deterministic quantity, not a clock.

**Decision.**
1. Deleted: every ratio of CPU time, every absolute time cap and the "too short to measure" logic. This removes
   `tests/collector_timing.py` and the three files `test_collector_native_scaling_real.py`,
   `test_collector_native_script_deps_scaling.py` and `test_collector_native_syntax_scaling.py`. They held only
   time assertions.
2. Kept: the peak memory cases (the peak of 2n is at most 2.5 times the peak of n, and the absolute caps), the
   table checks of the shapes and the checks that each shape holds the construct that it claims.
3. Not added: a work counter. The TypeScript `--dump-count` prints the definitions, sites and comparisons that the
   walk found. These are output sizes: they grow with the input by construction and show no quadratic loop. A
   test of a deterministic work count needs a counter of the operations of the walk in the collector.

**Protects -> still covered by -> or none.** A quadratic loop that also uses quadratic memory (the nests of #363:
1.3 GB for 8 000 nested classes) -> the memory cases. A quadratic loop that uses constant memory (time only) ->
none (owner decision). The hang timeout of the CI jobs still stops a run that does not end.

**Tests.** `tests/test_collector_native_scaling.py`, `test_collector_native_scaling_sites.py`,
`test_collector_native_script_scaling.py`, `test_collector_native_rust_scaling.py`, `test_collector_native_records.py`.
