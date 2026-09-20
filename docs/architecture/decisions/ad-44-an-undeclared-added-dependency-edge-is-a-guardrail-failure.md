# AD-44 An undeclared added dependency edge is a guardrail failure, closing the AD-39 Limit

`GUARDRAIL_DIMENSIONS` gains `dependency_edges`, a sixth entry, but its regression rule
is not the other five's: an edge count grows with any ordinary new import, so
`_COUNT_REGRESSION_DIMENSIONS` (`GUARDRAIL_DIMENSIONS` minus `dependency_edges`) is what
`_guardrail_failures` checks for aggregate growth, leaving `dependency_edges` out of that count
check entirely. What still fires for it is the existing added-fingerprint check every guardrail
dimension already has, now given one more filter: `_guardrail_failures` takes a `declared` set of
`(dimension, change, fingerprint)` identities built from `expectation.selected_changes`, and an
`added` `dependency_edges` fingerprint already in that set is no failure, the same way an added
cycle already accounted for by a contraction is no failure. Only `added` is checked, the same
kind every other guardrail's fingerprint check already limits itself to: a `removed` edge can
only narrow what a component depends on, never cross a boundary a rule forbids, so there is
nothing for it to violate. Reason: [AD-39](ad-39-an-empty-selectedchanges-declares-that-nothing.md) recorded, as its own Limit, that a non-empty declaration
lets an undeclared change in a dimension that is neither selected nor a guardrail dimension pass
with no failure at all, naming `dependency_edges` as the example; that gap stayed open because
closing it the way the other five guardrails work would have made every declared new edge fail
too. Rejected: giving `dependency_edges` the same unconditional rule as the other five, so any
`added` fingerprint fails whether declared or not, was rejected because a new edge is not
inherently a regression the way a new violation, cycle, private crossing, typing signal or
unknown is; the M -> B -> E -> H protocol exists so an agent can name an intended new edge and
have it accepted, and an unconditional rule would foreclose that for the one dimension ordinary
declared growth touches most often. A ninth `GUARDRAIL_KEYS` boolean, `no_new_dependency_edges`,
mirroring `coverage_must_pass`, was rejected because `GUARDRAIL_KEYS` are fixed-true
acknowledgment flags with no fingerprint of their own, while this check has to compare each
added fingerprint against `selected_changes`, exactly the comparison the cycle-contraction filter
already performs; reusing that shape costs one clause, not a new required field, so
`EXPECTATION_SCHEMA_VERSION` stays 1.2.0. Limit: `dependency_edges` is the one guardrail
dimension whose `added` check a declaration can satisfy; every check-run row in the demo catalog
declares its whole observed delta, so none of them can show the undeclared case failing without a
scenario built to omit one, which no existing row does, so this Limit is documented instead of
demonstrated end to end. Check: `tests/test_expectation.py`'s
`test_undeclared_added_dependency_edge_fails_naming_it`,
`test_declared_added_dependency_edge_passes` and
`test_removed_dependency_edge_does_not_fail_undeclared`; the catalog's `class-b-guardrail-
dependency-edges` row and `fixtures/demo_catalog_check.py`/`demo_catalog_check_regressions.py`'s
updated `regressed_dimensions` show every protocol row still declares its own new edges and
still passes.

