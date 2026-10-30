# AD-143 Initial PR head proves scoped order

[AD-281](ad-281-retire-unused-tooling.md) retires the receipt producer. The ordering check in `src`
stays until issue #767 removes `InitialPRHeadEvidence`.

An authenticated original PR opened at E proves E precedes later H submissions
to that same PR. Bind repository/PR IDs, approved worker B, original run/attempt and
artifact digests. Missing, reopened or opened-at-H receipts remain UNKNOWN.

The collector executes no candidate code. Exactly one successful reviewed-source
worker must account for the complete job list; skipped jobs still count. The reader
runs from approved immutable source with its pinned checker. Worker provenance
cannot prove caller SHA. A real check still needs an approved accepted lock.

[Ordering proof](../../../tests/test_initial_pr_check.py).
