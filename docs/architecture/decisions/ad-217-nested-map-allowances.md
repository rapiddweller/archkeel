# AD-217 Nested maps need an exact owner coordinate

For [issue #432](https://github.com/rapiddweller/archkeel/issues/432), add optional
`mapping_depth` to an exact `boundary_types.allowed_positions` selector. A
complete, alias-free map → list → map → object signature has three independent
decisions: outer map, inner map at depth 2, and its native value at depth 3.
`mapping_depth: 2` selects the inner map; combining it with
`container_depth: 3` selects only that value. Only the native decision accepts
opacity.

The evaluator reuses proven type shapes and pre-deduplication mapping
occurrences. It rejects wrappers, sibling maps, aliases, shadowed bindings,
unknown nodes, DTO fields and unions. Existing selectors, fact IDs and widening
meaning are unchanged when `mapping_depth` is absent. No CE source or baseline
change is needed. [Proof](../../../tests/test_boundary_type_nested_mapping.py).
