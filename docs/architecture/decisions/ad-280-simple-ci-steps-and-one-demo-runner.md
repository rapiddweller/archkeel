# AD-280 Named CI jobs, test areas and one demo runner

**Status.** Proposed. The owner approves it.

**Decision.**
1. Each CI job has a name that tells what it checks. `All checks passed` is the one CI aggregate.
2. `tests/areas.py` puts each test file in exactly one named area. Each test job runs one area
   (`Tests: <area>`), never a numbered shard. Measured with 12 areas (run 41022626056): the slowest
   PR job took 10m42 (main: 10.7 min). The current 10-area times are estimates.
3. `make demos` runs every gallery demo in one step of the `Demos` job. The case list comes from
   `gallery_cases()`; no demo name is in a workflow file.
4. `build_demos` is the only demo runner. The Pages gallery uses it and adds only the index. It
   checks the expected exit, the expected rule status, the UML status and the HTML files.
5. A failed demo does not stop the next demo. At the end, the step fails and names each failed
   demo. An expected exit never changes FAIL or UNKNOWN into PASS.
6. Each demo writes one line in a log group and one row in a Markdown table (log and step
   summary). The job uploads only the HTML reports, for one day. JSON stays on the runner disk.
7. Saved-report tests run only in the area test jobs. These jobs hold unit, integration and CLI
   tests, so CI does not call them unit tests.

**Reason.** Numbered shards, 46 hand-written demo steps, a second demo runner and YAML text tests
were hard to read and had to stay in sync.

**Rejected.** One step or one job for each demo: more YAML to keep in sync.

**Limits.** CI no longer prunes artifacts on each push to `main`; the nightly job does, so old
artifacts can stay up to 24 hours. A nightly Pages run builds every demo twice. The demo catalog area takes about
11 minutes, because one file holds it.

**Checks.** `tests/test_report_pages.py` and `tests/test_make_gate.py`.
