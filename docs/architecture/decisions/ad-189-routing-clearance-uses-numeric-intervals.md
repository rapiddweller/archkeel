# AD-189 Routing clearance uses numeric intervals

Cache routing clearance with numeric axis, coordinate and ordered interval keys.
Numeric keys avoid rebuilding a segment's text representation.
Reversed segments reuse one answer.

Limit the cache to one render so positions and obstacles cannot change underneath
it. Keep route search, ordering, arrows and hit geometry unchanged.
Readability and overlap checks remain separate.

[Route controls](../../../tests/test_own_uml_target.py).
