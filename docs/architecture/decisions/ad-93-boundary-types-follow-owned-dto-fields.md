# AD-93 `boundary_types` follows owned declared DTO fields

Recursively check fields of owned declared DTOs through supported collections and unions. Track
origins on the active path to stop cycles; sibling paths remain independently checked. Preserve the
signature annotation, field path and actual nested annotation on findings.

Unsupported, unresolved and ambiguous shapes stay UNKNOWN. This extends
[AD-84](ad-84-boundary-types-follow-declared-facade-reexports.md) without runtime reflection. Proof:
[test_boundary_types_facades.py](../../../tests/test_boundary_types_facades.py).
