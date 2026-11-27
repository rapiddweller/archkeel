# AD-674 Three gate tiers, and a merge only on green

**Status.** Accepted. Owner decision of 2026-11-16. Part of #880. It amends AD-348 and AD-341. The merge-tool part (`tools/merge_pr.py` refuses a red check) is superseded by [AD-1270](ad-1270-the-merge-tools-are-deleted-and-github-enforces-the-pr-gate.md): the merge tools are deleted.

**Reason.** From 2026-11-15 19:45Z no area test ran on CI for 19 hours (the pytest list named deleted files), and red merged anyway: pipelines ran on `main` only, merges used `--admin`, and the lead fixed forward. A gate that does not block prevents nothing.

**Decision.**
1. Three tiers with time budgets on GitHub runners:
   - **PR gate** (`pr-gate.yml`, one job named `PR gate`, at most 3 minutes): `make ci-pr-static`, the cached core build, `make self-validate` (native, shell, system, with the ratchet of AD-672), and the fast tests of the areas that the change selects (`tools/select_areas.py`, rules in `tests/areas.py`). One job, because the free plan runs 20 jobs at once.
   - **Main** (`ci.yml`, at most 15 minutes): the whole fast suite in area jobs, `make native-check`, lint, diagrams.
   - **Nightly** (`full-verification.yml`, at most 45 minutes): every test including `SLOW_FILES`, Windows, the Python matrix, wheels.
2. `SLOW_FILES` (scaling, memory, large scans) carry the marker `slow`; PR and main run `-m "not slow"`. No guarantee is dropped: the nightly run runs all.
3. A change selects areas by path. A path that no rule names selects every area. `tests/area_floors.json` gives each area a floor of fast tests; a selection below its floor fails (pytest exit 5 can no longer pass unseen).
4. The check `PR gate` is a required status check of the branch `main`, with no bypass. `tools/merge_pr.py` merges only when it is green.

5. Main runs queue (owner decision of 2026-11-17, after 38 of 40 runs on main were cancelled). `ci.yml` has the concurrency group `ci-main` with `cancel-in-progress: false`: the running run finishes, only the newest waiting run is kept, older waiting runs drop. Pull requests keep being cancelled (`pr-gate.yml`). AD-1060 removes the schedule of `ci.yml`. The nightly Full run is unchanged.

**Rejected.** A matrix of area jobs on each PR (20-job limit, queue wait); keeping `PR_TEST_FILES` by hand (it named deleted files).

**Limit.** The 3-minute budget holds with a warm Rust cache. A PR that changes `native/` core code rebuilds the core. Wall times are in the PR text that introduced the tiers. Scaling tests still assert time and memory; asserting work counters instead is open.

**Tests.** `tests/test_area_selection.py`, `tests/test_make_gate.py`, `tests/test_native_ci.py`.
