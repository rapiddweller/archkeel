# AD-1172 The re-export table follows renames to a fixpoint

**Status.** Accepted. Issue #2109. It extends [AD-1152](ad-1152-a-module-read-as-an-attribute-of-a-project-module-is-a-site.md).

**Reason.** AD-1152 followed a rename of a re-exported name over two passes. A rename of three or four hops (`cp -> q1 -> q2 -> q3`) gave no site, and CPython 3.12 imports `app.lib` through it.

**Decision.** The table repeats the pass until no name gets a new origin. Each pass reads a snapshot, and the origin sets only grow. The number of names and origins in the scan is finite, so the loop ends.

**Narrowing.** None. The change only adds names to the table, so it only adds sites.

**Limit (precision).** The table is keyed on names, as in AD-1094: a longer chain adds names to it, so an unrelated attribute with such a name is a site too.

**Tests.** `tests/test_collector_false_pass_python_rename_chain.py`: chains of 1, 2, 3, 4 and 6 hops (CPython 3.12 imports `app.lib`; the verdict must be UNKNOWN or FAIL) and two controls that rename a number. The mutation back to two passes fails the chains of 3, 4 and 6 hops.
