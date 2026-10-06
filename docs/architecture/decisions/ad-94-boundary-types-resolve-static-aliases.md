# AD-94: Boundary types resolve static aliases

Resolve statically recognized top-level type aliases, unwrap `Annotated` and check `Literal`
constants. Dynamic and ambiguous bindings remain UNKNOWN; a name's spelling is not proof of its type
or value.

This reduces avoidable uncertainty without guessing runtime state. Proof:
[test_boundary_type_literals_aliases.py](../../../tests/test_boundary_type_literals_aliases.py).
