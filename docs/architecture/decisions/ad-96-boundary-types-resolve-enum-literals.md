# AD-96: Boundary types resolve proven enum members in Literal

Accept an enum member inside `Literal` only when its owner resolves to one statically recognized
enum and the member has one literal assignment. Missing, repeated, dynamic or non-enum attributes
remain UNKNOWN.

This proves a Literal value; it does not make the member expression a type annotation. Proof:
[test_boundary_type_enum_literals.py](../../../tests/test_boundary_type_enum_literals.py).
