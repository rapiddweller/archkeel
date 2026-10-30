# AD-278 Verify each gallery demo in one job

Full verification runs all gallery entries in one demo job. Each entry has a named
step, so its log is easy to find. A test compares the steps with the gallery catalog.
Each step checks the expected exit and records coverage, rule results, output sizes,
phase times and counters. The job retains the reports and results as one artifact.
A failed demo does not skip later demos, but it fails the job and the aggregate.

A report with incomplete coverage can still produce an architecture artifact.
`--timings` writes phase times for that artifact even when its exit is 2. A run that
produces no architecture artifact writes no timings. An expected exit does not
change FAIL or UNKNOWN into PASS.

The gallery build remains separate. It runs on scheduled and manual Main verification
before Pages deployment. No phase or size budget is introduced without measurements.

Rejected: one job per demo, because it adds runner setup and makes the run hard to scan.
Rejected: one unnamed loop, because individual demo logs are harder to find.

Checks: `tests/test_demo_ci.py`, `tests/test_phase_timings.py` and
`tests/test_make_gate.py`.
