# AD-280 Simple CI steps and one demo runner

**Status.** Proposed. The owner approves it.

**Decision.**
1. Each CI job has a name that tells what it checks. A job splits its make target into named steps.
   The steps run the same commands as the local target (`make ci-pr-static`,
   `make ci-pr-report-check`, `make ci-check`).
2. `make demos` runs every gallery demo in one step of the full-verification `demos` job.
   The case list comes from `gallery_cases()`. No demo name is in a workflow file.
3. `build_demos` is the only demo runner. The Pages gallery uses it and adds only the index.
   It checks the expected exit, the expected rule status, the UML status and the HTML files.
4. A failed demo does not stop the next demo. At the end, the step fails and names each failed demo.
   An expected exit never changes FAIL or UNKNOWN into PASS.
5. Each demo writes one line in a log group. One Markdown table goes to the log and the step
   summary. The job uploads only the HTML reports, for one day. JSON stays on the runner disk.
6. `--timings` also writes phase times when the report has violations (exit 2). A run without an
   architecture artifact writes no timings.
7. Saved-report tests run only in the Python test shards, not again in the report job. The shards
   hold unit, integration and CLI tests, so CI does not call them unit tests.

**Reason.** 46 hand-written demo steps, a second demo runner and a YAML text test had to stay in
sync with the catalog. Large JSON in logs and artifacts was hard to read.

**Rejected.** One step or one job for each demo, because each adds YAML to keep in sync.

**Limits.** A nightly Pages run builds every demo twice: in the `demos` job and in `report-pages`.

**Checks.** `tests/test_report_pages.py`, `tests/test_make_gate.py` and
`tests/test_phase_timings.py`.
