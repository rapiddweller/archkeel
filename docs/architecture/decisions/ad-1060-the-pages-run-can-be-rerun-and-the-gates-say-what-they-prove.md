# AD-1060 The Pages run can be rerun and the gates say what they prove

**Status.** Accepted. Amends AD-740 and AD-754 (Pages part), AD-674 (point 5). Owner request of 2026-11-23.

**Reason.** Review of the last 40 Pages runs: 3 failed on the artifact. After the upload, `deploy-pages` listed 0 artifacts (actions/deploy-pages#451). A rerun kept the artifact of attempt 1, so it found 2 and failed. The same job that fetches third-party sources held `id-token: write`. The two cache saves in Pages only conflicted with the saves of CI (`Unable to reserve cache`). AD-754 gave a reason that is out of date: CI runs of main no longer cancel (AD-674).

**Decision (Pages).**
1. `pages.yml` has a build job (`contents: read`) and a deploy job (`pages: write`, `id-token: write`). The deploy job needs the build job.
2. The artifact name is `github-pages-<run_attempt>`. The build job passes it to `deploy-pages` as `artifact_name`. "Re-run all jobs" makes a new artifact. "Re-run failed jobs" repeats only the deploy.
3. The concurrency group `github-pages` is on the workflow, with `cancel-in-progress: false`.
4. Pages saves no cache. CI `lint` saves the Rust cache and the core of main. Pages still restores the Rust cache and builds with the gate profile.
5. Pages does not fetch the git history: the gallery only reads `git rev-parse HEAD`.

**Decision (schedule).** `ci.yml` has no `schedule`. `workflow_dispatch` stays. All 11 scheduled runs in the review checked a commit that a push run had already checked: about 48 job-minutes each, no new information. One failed on a commit that had passed, which is a flake, not a finding. The nightly Full run still checks main.

**Decision (nightly).** The ratio tests of the Rust collector (`attributes` and the other shapes) and of the TypeScript records pass take the least CPU time of three runs, with the two sizes alternating (`interleaved_least`, AD-323). The limit stays 3.0. The Full run names the first failing test of each failed test job in its job summary. The chain test and its wall timeout stay as they are: the cost is a quadratic copy in the core, and a CPU measure would hide it.

**Decision (logs).** A CI log has about 18,000 lines for a PR gate run and 26,000 for a Full run. About 60 % are the branch list that `git fetch` prints in the checkout with `fetch-depth: 0` (1,578 lines for each job). About 1,600 lines are cargo `Compiling` and `Downloaded`. Under `CI`, the Makefile sets `CARGO_TERM_QUIET` and `CARGO_TERM_PROGRESS_WHEN=never`; errors and warnings stay. The pytest targets add `--tb=short -rfE`, so the end of a failed log lists each failure. A failed test job writes its first failing test, the repeat command and the artifact name to the job summary (`tools/ci_failure_summary.py`). The PR gate and CI keep `fetch-depth: 0`: they need `origin/main` for the base diff.

**Rejected.** A skip of a scheduled run when the commit has a green push run: each other job would need a skip condition, and no job may skip (`.github/AGENTS.md`). A poll on the artifact count before the deploy: the gap between two jobs is 10 to 20 s and the listing lags 0.6 s. Add the poll (`gh api .../runs/$GITHUB_RUN_ID/artifacts`, at most 60 s, `actions: read`) only if a run shows `Found 0` again. A path filter for Pages: 34 of 40 commits touch the gallery inputs.

**Limit.** Without the Pages saves, a CI `lint` that fails before its build leaves the main cache one push older. The PR gate is then slower, not wrong. "Re-run failed jobs" works for one day: the artifact of `upload-pages-artifact` is kept 1 day. After that, use "Re-run all jobs". A rerun of an old run can take the pending slot and publish an older page; this was so before.

**Tests.** `tests/test_gallery_publication.py`, `tests/test_core_cache.py`, `tests/test_collector_native_rust_scaling.py`, `tests/test_collector_native_records.py`, `tests/test_ci_failure_summary.py`, `tests/test_make_gate.py`.
