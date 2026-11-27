# AD-1251 Repository and CI policy pins are deleted, and the executed checks stay

**Status.** Accepted. Owner decision of 2026-11-27 (drift gates audit, step E). Amends AD-341, AD-674, AD-752, AD-1064.

**Reason.** A test that reads workflow text, a ledger of today's counts or a byte budget compares the repository
with itself. It passes when the workflow is wrong (#2134 passed every wiring test and blocked each PR) and fails
when a harmless edit moves a line. No such test caught a defect that a run of the real thing would not show.

**Decision.** Deleted:
1. Workflow and Make text pins, also the reviewed list of workflow files (CONTRIBUTING and `.github/AGENTS.md` now ask the owner's approval of a new workflow in its PR text) (`test_gallery_publication.py`, `test_native_ci_type_reach.py`, runner images, job
   order, cache keys, flags, triggers, Make step order) and the tests that copied them.
2. Hygiene checks: file allowlist of the root, local paths, license header, plans, conflict markers, run output,
   decision links and numbers (`test_doc_references_exist.py`, parts of `test_repository_hygiene.py`).
3. The decision index tests (duplicates, row floor). `tools/decision_index.py` stays and lists on demand.
4. Time limits: `tools/native_timing_budget.py` and its test, and the limits of `tools/ci_budget.py`. The raw timing
   JSON and the job table stay in the job summaries. Hang timeouts stay.
5. Page budgets (bytes, words) and the README copy pins (`test_readme_showcase.py`).
6. Copied command and wording lists of the shipped skills. The real parser still checks each command line.

**Kept.** Executed tests: routing and selection, the fail-closed aggregates, Make cleanup, mermaid, release and
install tests, the installed skill, archive integrity, the sdist content and the decision step of Pages.

**Protects -> still covered by.** A wrong workflow -> the run of the workflow. A slow job -> the hang timeout
and the job table. A stray file in the root, a conflict marker, a dead link -> review and `git diff --check`
(none, owner decision). A big page -> none. A command that a skill names and the shell refuses -> the parser test.

**Not done.** The CPU-ratio tests of the native collector scaling files stay: they found real quadratic code (#363)
and mix work counts with times. A change of them needs its own look. The size and ledger gates belong to step D.

**Tests.** The tests of the files above that remain.
