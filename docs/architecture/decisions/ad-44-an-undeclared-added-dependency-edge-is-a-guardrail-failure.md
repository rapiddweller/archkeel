# AD-44 An undeclared added dependency edge is a guardrail failure, closing the AD-39 Limit

`dependency_edges` becomes the sixth guardrail dimension. It checks undeclared
added fingerprints, not aggregate count growth. A declared
`(dimension, change, fingerprint)` satisfies this check; removed edges do not fail.
The other five guardrails retain their count and added-fingerprint checks.

This closes [AD-39](ad-39-an-empty-selectedchanges-declares-that-nothing.md)'s gap for
non-empty declarations. A declared new dependency need not be a regression;
rejecting every addition would prevent the protocol from accepting intended growth.
Reuse selected-change identity matching rather than adding `no_new_dependency_edges`,
a fixed-true flag that could not identify an edge. Expectation schema stays 1.2.0.

Only this guardrail accepts an added fingerprint by declaration. Existing demo rows
declare the whole delta, so they cannot demonstrate the undeclared failure end to end.
Checks: `tests/test_expectation.py` tests undeclared additions failing with identity,
declared additions passing and undeclared removals passing. The
`class-b-guardrail-dependency-edges` catalog row and updated regression dimensions
preserve passing protocol rows.
