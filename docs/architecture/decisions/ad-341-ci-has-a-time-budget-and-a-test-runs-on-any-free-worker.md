# AD-341 CI has a time budget, and a test runs on any free worker

**Status.** Proposed. The owner set the budget on 2026-11-09.

**Decision.**
1. The budget: a PR CI run takes at most 10 minutes of wall time, with a target of 8. Full
   verification takes at most 30 minutes. A PR test job takes at most about 7 minutes.
2. A test without a module, class or package fixture runs on any free worker. The tests that
   use such a fixture stay on one worker (`xdist_group` by file in `tests/conftest.py`), so the
   fixture runs once. This replaces the hand list of files that ran on any worker. Two files keep
   one group of their own: each digest test does a clean `cargo build` that uses every core, and
   the process limit tests of `test_source_trust_boundary.py` bound a wall time.
   The consumers of the self-run come last, so that no worker waits for its lock while another
   worker builds the self report (up to 254 s on a runner).
3. `tests/areas.py` keeps the summed test time of an area below about 24 minutes on the slowest
   runner, so that 4 workers end in about 6 minutes. Three areas are split for this: `collectors`
   (the native TypeScript collector moves out), `CLI, contracts and dependency rules` and
   `type and wire guards` (the `test_typed_*` files move out).
4. Each aggregate job runs `tools/ci_budget.py` on the jobs of its own run. The tool writes a
   table to the job summary and a warning for each job and critical path over its limit. It never
   fails the run: a slow runner must not block a correct change. Limits: CI 7 minutes for a job
   and 10 for the critical path; Full 15 minutes for a job and 30 for the path.
5. Each test job prints the CPU model of its runner, so that a slow job can be put on its runner.
6. The time budget is a target. The job time limits only stop a hung job: each test job has
   `timeout-minutes: 40`, about twice the slowest measured job (20.6 minutes). A PR is never held
   back because a job is slower than the budget. The lead reviews the measured job times
   regularly (after about every ten merges, and whenever `ci_budget` warns). The lead improves the
   slowest parts where the cost and benefit are best: parallel work, no duplicated work, and
   smaller heavy tests that keep their proof.

**Problem.** Measured with `gh api` on 2026-11-09. The last 15 passed CI runs took 8.5 to 25.7
minutes from creation to end. The longest job of a run took 8.5 to 11.6 minutes. Jobs waited up
to 18 minutes in the queue. The last 10 Full runs took 17 to 34 minutes; `Tests: collectors` took
10.6 to 20.6 minutes, and the job limit is 20.

**Cause.**
1. With `--dist=loadgroup`, 421 of 424 test files ran on one worker each. The longest file set
   the least time of its job. In the nightly Full run of d6fa2c4a, `test_collector_native_scaling.py`
   took 17.1 minutes on one worker; its job took 17.6 minutes. In CI, `test_dart_typed_controls.py`
   took 7.8 minutes on one worker.
2. The same tests took up to 2 times as long on one runner as on another, on the same image
   (20261101.360.1). For example, `type and wire guards` summed 16.9 minutes in run 42603282468
   and 33.9 minutes in run 42602934020. The Nov 8 nightly run (4 min 47 s for collectors) had a
   fast runner; the code did not make the same tests 2 times slower.
3. The organization has the Free plan: at most 20 jobs run at the same time. On 2026-11-09, 20
   jobs ran at the peak, and 371 of 953 jobs waited more than 2 minutes. A CI run has 19 jobs and
   a Full run 27, so two runs at the same time always queue.

**Rejected.**
- A job limit as a gate: a slow runner would then block a correct change (item 6).
- `--dist=load` for all tests: a module fixture would run once in each worker.
- Build the native binary once and share it as an artifact: a clean debug build took 17.6 s
  in the native job of run 42603282468. A build job before the test jobs adds a sequential step
  of more than that to the critical path.
- A cargo cache now: only the native area builds the binary, once for each worker lock.

**Limits.** The queue time is outside this repository; only fewer runner minutes reduce it. A
budget warning is not a gate. Moving a test out of the PR gate is an owner decision. The ratio
tests of the native collector stay on all workers: on one worker they took 16.1 minutes in Full.
One ratio reached 3.04 against its bound of 3 on this branch (Full run 42626933584). Full runs
42568311162, 42573462394 and 42584400956 failed on such a ratio before the change.

**Checks.** `tests/test_ci_budget.py` and `tests/test_make_gate.py`.
