# AD-39 An empty `selected_changes` declares that nothing architectural changed

`selected_changes: []` is a valid declaration that no architectural change occurred.
`parse_expectation` requires a list; `evaluate_expectation` rejects every semantic
change in any of the eight dimensions for an empty list, naming its dimension,
kind and fingerprint. A non-empty list retains selected-fingerprint checks and
the five guardrails: `violations`, `cycles`, `private_crossings`, `typing_signals`
and `unknowns`.

The evaluator separates provenance, counts, indexing, selected matching, guardrails
and undeclared changes into named phases ([AD-6](ad-06-a-function-has-one-responsibility.md)).
A pure uncalled function added to `ir/digest.py` had produced no semantic delta,
but the M → B → E → H protocol rejected its empty declaration.

A second `no_semantic_change` field would duplicate the claim and require a schema
bump. Guardrail-only checking would let an empty declaration exempt other dimensions.
Expectation 1.2.0 stays unchanged: no valid input becomes invalid, and old checkers
reject the empty list ([AD-8](ad-08-statement-constructs-are-class-a-rules.md)).

Limit: non-empty declarations still admitted unselected, non-guardrail changes.
[AD-44](ad-44-an-undeclared-added-dependency-edge-is-a-guardrail-failure.md) later closes
that gap specifically for `dependency_edges`.
Checks: `tests/test_expectation.py` covers empty deltas and changes in guardrail
and non-guardrail dimensions; `protocol-empty-declaration` uses a comment-only
overlay and passes every verdict.
