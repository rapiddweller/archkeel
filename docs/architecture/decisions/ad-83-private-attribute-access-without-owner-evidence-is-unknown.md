# AD-83: Private attribute access without owner evidence is UNKNOWN

Keep confirmed private-import crossings separate from private attribute expressions with unproven
parameter ownership. The latter record UNKNOWN and a separate scalar, naming the function, parameter
and attribute. Syntax proves access, not the runtime owner.

Do not infer a crossing from names or a guessed call graph.
[AD-91](ad-91-only-top-level-any-makes-private-owner-unknown.md) refines outer-owner resolution.
Proof: [test_private_crossings.py](../../../tests/test_private_crossings.py).
