# AD-1190: Parallel area jobs run every selected area

The PR base job runs self-check before the selected tests. A tools change ran
those tests in the base job and exceeded its 15-minute timeout. Its parallel
area jobs skipped the tests, because their selector only ran for native and
CLI changes.

The parallel area jobs now run every area selected by the changed paths. They
use the main-tier selection, which includes the PR-tier tests. When the
parallel jobs run, the base job does not run the same tests again. The PR gate
requires both the base job and the area jobs. A local gate still runs its
selected tests.

This adds work to the parallel jobs for tools, documentation and test changes.
It removes no test and does not change a timeout.
