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

**Rejected.** A skip of a scheduled run when the commit has a green push run: each other job would need a skip condition, and no job may skip (`.github/AGENTS.md`). A poll on the artifact count before the deploy: the gap between two jobs is 10 to 20 s and the listing lags 0.6 s. Add the poll (`gh api .../runs/$GITHUB_RUN_ID/artifacts`, at most 60 s, `actions: read`) only if a run shows `Found 0` again. A path filter for Pages: 34 of 40 commits touch the gallery inputs.

**Limit.** Without the Pages saves, a CI `lint` that fails before its build leaves the main cache one push older. The PR gate is then slower, not wrong. The removal of `Install Node` is not tested; the review only suspects that the report needs no Node.

**Tests.** `tests/test_gallery_publication.py`, `tests/test_core_cache.py`.
