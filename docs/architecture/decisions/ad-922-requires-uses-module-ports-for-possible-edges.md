# AD-922 Requires uses module ports for possible edges

**Status.** Accepted. This extends AD-890.

**Problem.** A possible edge holds `complete_requires` even when a module port permits it.
The same port permits a known import.

**Decision.** Use the same port assessment for known imports and possible edges.
A possible edge has no proven symbol. A matching module port permits every symbol.
Both ends must be observed and each must have one owner.
The pair remains open for the run and for other rules.

**Rejected.** Accept every port for the target component. A different module or a symbol port
does not permit every possible edge. Drop the pair from the run. Other rules can still read it.

**Limit.** A symbol port without a proven symbol, an unseen end, and an ambiguous owner remain
open. This decision does not prove the absence of a violation among the remaining pairs.

**Tests.** `native/eval/src/scoped_requires_tests.rs` checks matching and different module ports,
symbol ports, known imports, unseen ends, and ambiguous owners.
