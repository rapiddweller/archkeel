# AD-164 Dependency permissions keep one owner

Keep `requires` as import permission owned by Core dependency rules.
It asserts neither import nor call. Independent and canonical producers derive
permission relationships with selectors, rationale, provenance and effective
decider. Distinct declarations retain identity through reordering.

Core authenticates permissions against the contract tree. UML references component
records rather than copying policy. Explicit UML cannot redeclare permissions or
close their inventory; its comparator skips them. This prevents a second verdict owner.

[Comparison proof](../../../tests/test_uml_comparison.py).
