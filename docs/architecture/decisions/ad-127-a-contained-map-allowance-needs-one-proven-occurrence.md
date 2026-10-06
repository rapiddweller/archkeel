# AD-127 A contained-map allowance needs one proven occurrence

An empty-path allowance selects one proven contained mapping when it matches
the full signature. Retain occurrences before deduplication: identical siblings
remain ambiguous.

Alias expansion on the route cannot pin shape; unrelated member aliases are
acceptable. Record map and depth. Direct-map and field selectors retain behavior.
Multiple contained maps remain unsupported; member violations and UNKNOWN stay
independent. New allowances require widening approval.

[Contained-map proof](../../../tests/test_boundary_types_contained_mapping.py).
