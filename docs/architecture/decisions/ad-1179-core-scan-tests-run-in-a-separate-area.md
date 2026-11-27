# AD-1179: Core scan tests run in a separate area

The Full verification job for CLI and core took 18.9 minutes on 2026-11-26.
Its job budget is 15 minutes. Core scan and native self-check tests account for much
of the test time. They run in a separate area in the PR, main and Full tiers.
The existing tier markers continue to select the tests.

Both areas run when a source change could reach them. Each workflow installs the
compiler components needed by the native self-check tests. The empty-area check
and the matrix tests check the selection.

We did not move tests to a slower tier. That would reduce the tests run before a
merge and would not reduce the Full job time. A second job adds runner setup and
build time. Its measured time must remain below the budget.
