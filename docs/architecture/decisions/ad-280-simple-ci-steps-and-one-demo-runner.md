# AD-280 Named CI jobs, test areas and one demo runner

**Status.** Proposed. The owner approves it.

**Decision.**
1. Each CI job has a name that tells what it checks. No job has a condition that can skip it.
   An aggregate (`All checks passed`, `All Full checks passed`) runs `always()`, because GitHub
   counts a skipped aggregate as passed.
2. CI runs on each pull request and runs the same fixed set: lint, types and architecture, the
   test areas, the report tests, the docs diagrams and the demos. No file classifier selects jobs.
3. Full verification runs nightly, on dispatch and before a release. `full-on-ci-change.yml`
   calls it for a PR that changes a CI path. It runs all tests, the compatibility jobs and the demos.
4. `pages.yml` publishes the gallery after a Full run on `main`. It publishes only when that run
   passed and its commit is the current `main`. It uses the report and the demo build of that run.
5. `maintenance.yml` prunes workflow registrations and report artifacts nightly. CI no longer
   prunes on each push to `main`, so old artifacts can stay up to 24 hours.
6. `tests/areas.py` puts each test file in exactly one named area. Each test job runs one area
   (`Tests: <area>`), never a numbered shard.
7. `make demos` runs every gallery demo through `build_demos`, the only demo runner. It checks the
   expected exit, the expected rule status, the UML status and the HTML files. A failed demo does
   not stop the next one; at the end, the step fails and names each failed demo. An expected exit
   never changes FAIL or UNKNOWN into PASS. One Markdown table goes to the log and the step summary.
8. Saved-report tests run only in the area test jobs. These jobs hold unit, integration and CLI
   tests, so CI does not call them unit tests.

**Reason.** Numbered shards, skipped jobs, 46 hand-written demo steps, a second demo runner and
YAML text tests were hard to read and had to stay in sync.

**Rejected.** One step or one job for each demo: more YAML to keep in sync. Pages deploy inside
Full: it needs a job condition, because a PR and a release also run Full.

**Limits.** Measured on head 4ebae76f (run 41024475883, 10 areas): the slowest PR job took 9m48
(`main`: 10.7 min). Four Full areas took more than 10 minutes, at most 14m46; Full is not a PR gate.
PR runner minutes grow, because seven area jobs build the self report and each PR runs the demos.
A CI-change PR runs the PR tests and Full.

**Checks.** `tests/test_report_pages.py` and `tests/test_make_gate.py`.
