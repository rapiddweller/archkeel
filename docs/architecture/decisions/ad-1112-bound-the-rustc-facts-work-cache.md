# AD-1112 Bound the rustc facts work cache

**Status.** Accepted. Amends AD-1047.

**Decision.** Keep at most three work directories, ordered by their last use.
The producer removes the oldest directories when a scan needs another directory.
It logs a removal failure and continues the scan.
A cache lock protects facts until the Rust collector has read them.

**Reason.** Each scanned path makes a separate Cargo work directory.
One directory can use several GB. The reported cache used 268 GB.
Removing a directory requires a rebuild. The facts remain hash-bound and verified.
A successful rebuild does not create a different PASS. A failed rebuild keeps the gaps.

**Rejected.** An unbounded cache can exhaust the disk. A byte budget adds measurement and policy
without a known need. Three directories bound the count, not the bytes: a large project can use
more disk than a small one. Removal failures can temporarily exceed the count.

**Tests.** The cache bound test scans four paths with a fake toolchain.
The real-toolchain tests use guarded temporary directories and copy facts for the reader tests.
