# AD-39 An empty `selected_changes` declares that nothing architectural changed


`parse_expectation` no longer rejects `"selected_changes": []`; it only requires a list, so the
field still means exactly what it always meant, a set of semantic changes the agent selects, and
an empty set is simply the smallest legal one. `evaluate_expectation` reads that emptiness as a
positive claim rather than an omission: with a non-empty declaration it keeps checking exactly what
it checked before, the named fingerprints against the observed delta plus the five fixed guardrail
dimensions (`violations`, `cycles`, `private_crossings`, `typing_signals`, `unknowns`) for
regressions and new entries; with an empty declaration it instead fails on every entry in
`delta_model.semantic_changes`, in any of the eight delta dimensions, naming the dimension, the
change kind and the fingerprint. The function was decomposed into six named phases,
`_require_matching_provenance`, `_require_dimension_counts`, `_index_semantic_changes`,
`_match_selected_changes`, `_guardrail_failures` and `_undeclared_change_failures`, so the new
branch reads as one call rather than more inline logic on top of an already-long function ([AD-6](ad-06-a-function-has-one-responsibility.md)).
Reason: the M → B → E → H protocol has no other way to submit a change with an empty semantic
delta. A candidate that adds one pure function to `src/archkeel/ir/digest.py`, calling nothing and
called by nothing, observably changes no dimension at all, yet `parse_expectation` answered
`selected_changes must be a non-empty list`: an agent required to declare every submission had no
legal declaration for a refactor that changes nothing. Two cheaper ways were rejected. A dedicated
boolean field such as `no_semantic_change: true` says the same thing a second way, and doing so
changes the required key set, so it costs a schema bump for no reading `selected_changes` does not
already give for free. Reusing the existing guardrail-only comparison for an empty list, so an
empty declaration silently meant "no fixed-dimension regression" the way a non-empty one already
does for its unselected dimensions, was rejected because it would make `selected_changes: []` a
standing exemption for every non-guardrail dimension, available to any candidate regardless of
what it actually changed, rather than the narrow claim "nothing changed" it is meant to be. Contract
`EXPECTATION_SCHEMA_VERSION` stays 1.2.0: the required field set is unchanged and a JSON array was
always a legal `selected_changes` value, so no previously valid expectation becomes invalid, while
an older checker already fails closed on the empty list with `selected_changes must be a
non-empty list` ([AD-8](ad-08-statement-constructs-are-class-a-rules.md)) instead of silently accepting it under the old, narrower meaning. Limit: the
probe that motivated this decision also showed that a *non-empty* declaration still lets an
undeclared change in a dimension that is neither selected nor one of the five guardrail dimensions,
for example a new `dependency_edges` entry, pass with no failure at all; this decision closes the
equivalent question only for the empty-declaration case, where every dimension is now checked,
and [AD-44](ad-44-an-undeclared-added-dependency-edge-is-a-guardrail-failure.md) later closed the non-empty case for `dependency_edges` specifically. Check: `tests/test_expectation.py`'s
`test_empty_declaration_of_no_change_passes_against_an_empty_delta`,
`test_empty_declaration_fails_on_a_guardrail_dimension_change` and
`test_empty_declaration_fails_on_a_non_guardrail_dimension_change`, and the catalogued
`protocol-empty-declaration` row in `fixtures/demo_catalog_check.py`, whose comment-only overlay
produces a genuinely empty delta and passes every verdict.

