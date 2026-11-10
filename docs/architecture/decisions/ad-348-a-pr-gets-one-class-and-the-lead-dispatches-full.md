# AD-348 A PR gets one class, and the lead dispatches Full

**Status.** Accepted. The owner decided on 2026-11-10, after Fable 5.2. It amends AD-341
(merge rules) and replaces the rule "run Full once for each PR that changes an output".

**Decision.**
1. Each PR gets exactly one independent review. A PASS-relevant PR also gets the false-PASS probes.
   The author fixes the findings, the lead checks the fixes, and the PR merges. There is no second
   review round; a problem found later becomes a follow-up issue. The goal is a good solution, not
   a perfect one (owner, 2026-11-10).
2. Each PR has a class. A: no change to an output, golden bytes, a published schema, packaging or
   a workflow. B: such a change, or a protocol version. C: Windows-sensitive paths, wheel or
   packaging, `Cargo.lock`, toolchain, `Makefile` or `.github/`.
3. Before the push, the local gate is green on the final head, rebased on `main`
   (see `CONTRIBUTING.md`). A PR in a fix loop is a draft.
4. A needs the review, the local gate and green PR CI. When CI is not finished 15 minutes after
   the push, the lead may merge and read the result afterwards. B also needs one Full run on the
   final reviewed SHA. C needs green CI and the Full run of B.
5. One branch Full runs at a time. The lead dispatches it; an agent does not.
6. Full runs on `main` every night and after every 3 merges (the lead dispatches this one).
7. A red `main` stops the line. Only the fix merges. The lead reverts the suspect merge when
   no fix is green locally within 60 minutes.
8. A draft PR runs no job in `ci.yml` and `full-verification.yml`. `ready_for_review` starts CI.
9. `tools/ci_daily.py` prints the daily line: CI wall, CI queue wait (median, p90 and maximum of
   the slowest-starting job), Full wall on `main`, Full runs, re-runs and red-main hours. It leaves
   re-runs and all-skipped draft runs out of wall and queue. Targets: CI at most 10 minutes, queue at most 3, Full at most 30.

**Problem.** Measured on 2026-11-10. Full on `main` took 40.5 minutes of wall time; the longest
job took 18.5 minutes. PR CI took 25 to 30 minutes against 7.3 to 8.2 minutes without a queue.

**Cause.** The queue, not the checks. The Free plan runs 20 jobs at the same time. Five PRs ran
CI and Full at once, about 230 jobs. A CI run has 19 jobs and a Full run 27. All 7 defects of the
day came from reviews and probes, not from CI.

**Behaviour of a draft.** Each job has `if: github.event.pull_request.draft != true`. A draft run
shows all jobs and the aggregate (`All checks passed`) as skipped. A skipped required check counts
as passed, so it never stays pending; GitHub does not merge a draft. Marking the PR ready runs
CI. The test `!= true` (not `== false`) keeps the jobs on for `schedule`, `workflow_dispatch` and
`workflow_call`, where the draft flag is empty. Full already has a nightly `schedule`. The
concurrency group with `cancel-in-progress` stays.

**Separate groups.** A push to a draft and the ready click run in one PR at nearly the same time.
One concurrency group let the skipped draft run cancel the real run (seen on #945). The group
name ends in `draft` or `ready`, so a draft run never cancels a ready run; a new push to a ready PR
still cancels the older ready run.

**Ready-click window.** After the click and before the new run ends, GitHub can show the skipped
aggregate of the draft run, and a skipped required check counts as passed. `make merge-check`
fails when `All checks passed` is skipped. The lead merges only after the aggregate is green.

**Rejected.** An automatic trigger after every 3 merges: the lead counts and dispatches. A
bigger plan: it costs money and does not remove the extra runs.

**Limits.** Review at the end of the Rust corpus or after a second red `main` over 1 hour.
Red-main hours are not in the daily line.

**Checks.** `tests/test_ci_daily.py`, `tests/test_ci_budget.py`, `tests/test_make_gate.py`.
